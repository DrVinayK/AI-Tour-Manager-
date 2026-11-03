"""
Multi-agent travel planning workflow (parallel fan-out design).

Architecture
------------
    START --> weather_agent  --\\
    START --> places_agent    ---> writer_agent --> END
    START --> budget_agent    --/

The three specialist agents (weather, places, budget) are completely
independent of one another: none of them needs another specialist's output
to do its own research. LangGraph recognizes this from the edges above and
runs all three concurrently in the same super-step (backed by a thread
pool), then waits for all three to finish before invoking the Writer agent
exactly once with everything gathered — a standard "fan-out / join" graph,
not three sequential calls.

Reliability
-----------
Two layers of defense against a flaky LLM/tool call ruining the whole
request:

1. **Retries.** Every direct LLM call (`_invoke_llm`) is wrapped with a
   short exponential-backoff retry via `tenacity`, since transient
   rate-limit/network errors are common and usually resolve themselves in
   a second or two. Tool calls already have their own try/except in
   `_run_specialist` — a broken tool degrades that one piece of research
   rather than the whole loop.
2. **Graceful degradation.** If a specialist still fails after retries are
   exhausted, its node catches the exception, logs it, and returns a
   plain-language "unavailable" note instead of letting the exception
   propagate and take down the whole graph. The Writer agent is told
   explicitly which sections are missing and works around the gap. Even
   the Writer itself has a last-resort fallback: if the synthesis call
   fails, the user still gets the raw specialist research concatenated
   together instead of a hard error.

`agent_status` (a list of small dicts, one per node) records what actually
happened for each agent this run — ok / degraded / failed, plus timing —
so the API response and UI can be honest about partial results instead of
silently pretending everything succeeded.

    START -> {weather_agent, places_agent, budget_agent} (concurrent) -> writer_agent -> END
"""

from typing import Annotated, List, Optional, TypedDict
import operator
import os

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from tenacity import retry, stop_after_attempt, wait_exponential

from prompt_library.prompt import (
    BUDGET_AGENT_PROMPT,
    PLACES_AGENT_PROMPT,
    WEATHER_AGENT_PROMPT,
    WRITER_AGENT_PROMPT,
    build_system_prompt,
)
from integrations.mcp_registry import MCPToolRegistry
from tools.currency_conversion_tool import CurrencyConverterTool
from tools.expense_calculator_tool import CalculatorTool
from tools.place_search_tool import PlaceSearchTool
from tools.weather_info_tool import WeatherInfoTool
from utils.logger import get_logger, timed_block
from utils.model_loader import ModelLoader

log = get_logger(__name__)

# Per-specialist cap on internal tool-call <-> LLM round trips. This is a
# safety net, not a tuning knob for normal operation: it exists so a
# specialist that keeps requesting tools (e.g. a confused model retrying a
# failing tool) can't loop forever within one request. Set too low, a
# specialist runs out of steps mid-research and answers from memory instead.
try:
    MAX_TOOL_STEPS_PER_AGENT = max(1, int(os.getenv("AGENT_MAX_TOOL_STEPS", "5")))
except ValueError:
    MAX_TOOL_STEPS_PER_AGENT = 5
    log.warning(
        "invalid_agent_max_tool_steps",
        extra={
            "value": os.getenv("AGENT_MAX_TOOL_STEPS"),
            "fallback": MAX_TOOL_STEPS_PER_AGENT,
        },
    )

try:
    AGENT_LLM_RETRY_ATTEMPTS = max(1, int(os.getenv("AGENT_LLM_RETRY_ATTEMPTS", "3")))
except ValueError:
    AGENT_LLM_RETRY_ATTEMPTS = 3
    log.warning(
        "invalid_agent_llm_retry_attempts",
        extra={
            "value": os.getenv("AGENT_LLM_RETRY_ATTEMPTS"),
            "fallback": AGENT_LLM_RETRY_ATTEMPTS,
        },
    )


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        log.warning("invalid_int_env", extra={"name": name, "value": os.getenv(name), "fallback": default})
        return default


# Completion budgets. The writer needs room for a whole itinerary plus its
# sources section; the specialists only file short research notes, so keeping
# them tight leaves headroom under Groq's free-tier per-minute token cap.
WRITER_MAX_TOKENS = _int_env("WRITER_MAX_TOKENS", 6000)
SPECIALIST_MAX_TOKENS = _int_env("SPECIALIST_MAX_TOKENS", 1500)

# Retry policy for direct LLM calls: 3 attempts total, short exponential
# backoff. Kept deliberately small — an LLM call is already the slow part
# of a request, so we don't want retries to turn a 5s failure into a 30s one.
_retry_llm_call = retry(
    stop=stop_after_attempt(AGENT_LLM_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)


class TravelPlannerState(TypedDict):
    """Shared state passed between every node in the graph.

    `visited` and `agent_status` both use `operator.add` as their reducer
    because multiple parallel nodes (the three specialists) write to them
    in the same super-step — LangGraph needs to know to concatenate those
    deltas rather than have one overwrite another. `weather_report` /
    `places_report` / `budget_report` don't need a reducer: each is written
    by exactly one node, so there's never a concurrent-write conflict on
    those keys.
    """

    messages: Annotated[List[BaseMessage], add_messages]
    user_question: str
    weather_report: Optional[str]
    places_report: Optional[str]
    budget_report: Optional[str]
    visited: Annotated[List[str], operator.add]
    agent_status: Annotated[List[dict], operator.add]
    final_answer: Optional[str]


@_retry_llm_call
def _invoke_llm(llm, messages: List[BaseMessage]):
    """Thin wrapper around `llm.invoke(...)` so retry policy lives in one
    place instead of being copy-pasted at every call site."""
    return llm.invoke(messages)


def _run_specialist(llm_with_tools, tools_by_name: dict, system_prompt: str, user_question: str,
                     max_steps: int = MAX_TOOL_STEPS_PER_AGENT) -> str:
    """
    Minimal ReAct-style loop for a single specialist agent: ask the LLM,
    and if it requested tool calls, run them locally and feed the results
    back in, repeating until it responds with plain text or we hit
    max_steps (whichever comes first).

    Individual tool failures are caught and fed back to the model as a
    ToolMessage (so it can route around them); LLM call failures are
    retried by `_invoke_llm` and, if still failing after retries, propagate
    up to the caller (the specialist node), which handles graceful
    degradation for the whole agent.
    """
    convo: List[BaseMessage] = [
        SystemMessage(content=build_system_prompt(system_prompt)),
        HumanMessage(content=user_question),
    ]

    for _ in range(max_steps):
        response = _invoke_llm(llm_with_tools, convo)
        convo.append(response)

        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return response.content or "No information could be gathered."

        for call in tool_calls:
            tool_fn = tools_by_name.get(call["name"])
            if tool_fn is None:
                result = f"Unknown tool requested: {call['name']}"
            else:
                try:
                    result = tool_fn.invoke(call["args"])
                except Exception as exc:  # keep the graph alive even if a tool blows up
                    log.warning("tool_call_failed", extra={"tool": call["name"], "error": str(exc)})
                    result = f"Tool '{call['name']}' failed: {exc}"
            convo.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    # Ran out of steps without a final text answer — fall back to the last
    # bit of AI-authored text we have, so the specialist still contributes
    # something rather than nothing.
    for msg in reversed(convo):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "No information could be gathered in time."


def _run_specialist_node(agent_name: str, llm_with_tools, tools_by_name: dict,
                          system_prompt: str, state: "TravelPlannerState",
                          report_key: str, fallback_text: str) -> dict:
    """
    Shared node body for all three specialists: run the ReAct loop, time
    it, and turn any exception that survives retries into a graceful
    "unavailable" report instead of crashing the whole graph run.
    """
    try:
        with timed_block(log, "specialist_run", agent=agent_name) as t:
            report = _run_specialist(llm_with_tools, tools_by_name, system_prompt, state["user_question"])
        return {
            report_key: report,
            "visited": [agent_name],
            "agent_status": [{"agent": agent_name, "status": "ok", "duration_ms": t.duration_ms}],
        }
    except Exception as exc:
        log.error("specialist_failed", extra={"agent": agent_name, "error": str(exc)}, exc_info=True)
        return {
            report_key: fallback_text,
            "visited": [agent_name],
            "agent_status": [{"agent": agent_name, "status": "failed", "detail": str(exc)}],
        }


class GraphBuilder:
    """Builds the compiled multi-agent graph. Same external interface as
    before (`GraphBuilder(model_provider=...)()` returns a runnable graph),
    so callers like Backend_main_new.py only need to seed the right initial
    state, not change how they call this class."""

    def __init__(self, model_provider: str = "groq"):
        self.model_loader = ModelLoader(model_provider=model_provider)
        self.llm = self.model_loader.load_llm(max_tokens=SPECIALIST_MAX_TOKENS)
        # The writer emits the entire itinerary in one completion, so it needs a
        # far bigger budget than a specialist's research note.
        self.writer_llm = self.model_loader.load_llm(max_tokens=WRITER_MAX_TOKENS)
        self.mcp_registry = MCPToolRegistry()

        # --- Specialist toolsets: each agent only ever sees the tools it needs ---
        place_search = PlaceSearchTool()
        # The budget agent otherwise has no source of live figures at all — only
        # a calculator and an FX rate — so it prices trips from model memory.
        live_price_tools = [
            t for t in place_search.place_search_tool_list if t.name == "search_live_price"
        ]

        weather_tools = self._merge_tools(
            "weather",
            WeatherInfoTool().weather_tool_list,
            self.mcp_registry.get_tools_for_role("weather"),
        )
        places_tools = self._merge_tools(
            "places",
            place_search.place_search_tool_list,
            self.mcp_registry.get_tools_for_role("places"),
        )
        budget_tools = self._merge_tools(
            "budget",
            CalculatorTool().calculator_tool_list
            + CurrencyConverterTool().currency_converter_tool_list
            + live_price_tools,
            self.mcp_registry.get_tools_for_role("budget"),
        )

        self._weather_tools_by_name = {t.name: t for t in weather_tools}
        self._places_tools_by_name = {t.name: t for t in places_tools}
        self._budget_tools_by_name = {t.name: t for t in budget_tools}

        self.weather_llm = self.llm.bind_tools(weather_tools)
        self.places_llm = self.llm.bind_tools(places_tools)
        self.budget_llm = self.llm.bind_tools(budget_tools)

        self.graph = None

    def _merge_tools(self, role: str, native_tools: List, mcp_tools: List) -> List:
        if not mcp_tools:
            return native_tools

        merged_tools = list(native_tools)
        seen_names = {tool.name for tool in native_tools}
        added_count = 0
        skipped_names = []

        for tool in mcp_tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name or tool_name in seen_names:
                if tool_name:
                    skipped_names.append(tool_name)
                continue
            merged_tools.append(tool)
            seen_names.add(tool_name)
            added_count += 1

        log.info(
            "toolset_composed",
            extra={
                "role": role,
                "native_tool_count": len(native_tools),
                "mcp_tool_count": len(mcp_tools),
                "mcp_added_count": added_count,
                "skipped_tool_names": skipped_names,
            },
        )
        return merged_tools

    # ------------------------------ Nodes ------------------------------

    def weather_node(self, state: TravelPlannerState):
        return _run_specialist_node(
            "weather_agent", self.weather_llm, self._weather_tools_by_name, WEATHER_AGENT_PROMPT,
            state, "weather_report",
            fallback_text="Weather information is temporarily unavailable — plan for seasonal norms and check a forecast closer to your travel dates.",
        )

    def places_node(self, state: TravelPlannerState):
        return _run_specialist_node(
            "places_agent", self.places_llm, self._places_tools_by_name, PLACES_AGENT_PROMPT,
            state, "places_report",
            fallback_text="Place research is temporarily unavailable — the itinerary below relies on general knowledge for attractions/restaurants/activities.",
        )

    def budget_node(self, state: TravelPlannerState):
        return _run_specialist_node(
            "budget_agent", self.budget_llm, self._budget_tools_by_name, BUDGET_AGENT_PROMPT,
            state, "budget_report",
            fallback_text="Budget research is temporarily unavailable — costs below are rough general estimates only.",
        )

    def writer_node(self, state: TravelPlannerState):
        context = (
            f"WEATHER RESEARCH:\n{state.get('weather_report') or 'Not gathered — use general knowledge sparingly.'}\n\n"
            f"PLACES RESEARCH (attractions / restaurants / activities / transportation):\n"
            f"{state.get('places_report') or 'Not gathered — use general knowledge sparingly.'}\n\n"
            f"BUDGET & CURRENCY RESEARCH:\n{state.get('budget_report') or 'Not gathered — use general knowledge sparingly.'}"
        )

        try:
            with timed_block(log, "writer_run", agent="writer_agent") as t:
                response = _invoke_llm(
                    self.writer_llm,
                    [
                        SystemMessage(content=build_system_prompt(WRITER_AGENT_PROMPT)),
                        HumanMessage(
                            content=f"Traveler's request:\n{state['user_question']}\n\nSpecialist research to weave in:\n{context}"
                        ),
                    ],
                )
            final_text = response.content or "[No response generated]"
            status = {"agent": "writer_agent", "status": "ok", "duration_ms": t.duration_ms}
        except Exception as exc:
            # Last-resort fallback: even if the synthesis call itself fails
            # after retries, hand back the raw specialist research rather
            # than a hard error — a rough answer beats no answer.
            log.error("writer_failed", extra={"error": str(exc)}, exc_info=True)
            final_text = (
                "# Trip Notes (auto-generated fallback)\n\n"
                "Our itinerary writer hit an error, so here is the raw research "
                "our specialists gathered instead of a polished plan:\n\n"
                f"## Weather\n{state.get('weather_report') or 'Not available.'}\n\n"
                f"## Places, Food & Activities\n{state.get('places_report') or 'Not available.'}\n\n"
                f"## Budget\n{state.get('budget_report') or 'Not available.'}\n"
            )
            status = {"agent": "writer_agent", "status": "degraded", "detail": str(exc)}

        return {
            "final_answer": final_text,
            "messages": [AIMessage(content=final_text)],
            "visited": ["writer_agent"],
            "agent_status": [status],
        }

    # --------------------------- Graph assembly ---------------------------

    def build_graph(self):
        graph_builder = StateGraph(TravelPlannerState)

        graph_builder.add_node("weather_agent", self.weather_node)
        graph_builder.add_node("places_agent", self.places_node)
        graph_builder.add_node("budget_agent", self.budget_node)
        graph_builder.add_node("writer_agent", self.writer_node)

        # Fan-out: all three specialists start from the same super-step and
        # run concurrently — there's no dependency between them.
        graph_builder.add_edge(START, "weather_agent")
        graph_builder.add_edge(START, "places_agent")
        graph_builder.add_edge(START, "budget_agent")

        # Join: writer_agent only fires once, after ALL three specialists
        # have completed (LangGraph's Pregel-style super-step scheduling
        # guarantees this — it's not three separate invocations).
        graph_builder.add_edge("weather_agent", "writer_agent")
        graph_builder.add_edge("places_agent", "writer_agent")
        graph_builder.add_edge("budget_agent", "writer_agent")

        graph_builder.add_edge("writer_agent", END)

        self.graph = graph_builder.compile()
        return self.graph

    def __call__(self):
        return self.build_graph()
