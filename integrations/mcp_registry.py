import asyncio
import json
import os
import threading
from typing import Dict, List

from utils.logger import get_logger

log = get_logger(__name__)

_TOOL_CACHE: dict[str, List] = {}
_TOOL_CACHE_LOCK = threading.Lock()


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _parse_server_names(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _run_async_in_thread(coro):
    result = {}
    error = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - defensive bridge code
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


class MCPToolRegistry:
    """Loads MCP-backed LangChain tools from env-configured servers.

    The registry is optional by design: if MCP is disabled, unconfigured, or
    the adapter dependencies are missing, the application continues to run with
    its native Python tools only.
    """

    def __init__(self):
        self.enabled = _env_flag("ENABLE_MCP_TOOLS")

    def get_tools_for_role(self, role: str) -> List:
        if not self.enabled:
            return []

        server_config = self._load_server_config()
        if not server_config:
            return []

        filtered_config = self._filter_config_for_role(role, server_config)
        if not filtered_config:
            log.info("mcp_no_servers_for_role", extra={"role": role})
            return []

        cache_key = json.dumps(filtered_config, sort_keys=True)
        with _TOOL_CACHE_LOCK:
            cached = _TOOL_CACHE.get(cache_key)
        if cached is not None:
            return cached

        try:
            tools = self._load_tools(filtered_config)
        except ImportError:
            log.warning(
                "mcp_dependencies_missing",
                extra={
                    "role": role,
                    "hint": "Install 'langchain-mcp-adapters' and 'mcp' to enable MCP-backed tools.",
                },
            )
            return []
        except Exception as exc:
            log.warning("mcp_tool_load_failed", extra={"role": role, "error": str(exc)})
            return []

        with _TOOL_CACHE_LOCK:
            _TOOL_CACHE[cache_key] = tools
        log.info(
            "mcp_tools_loaded",
            extra={
                "role": role,
                "server_names": list(filtered_config.keys()),
                "tool_count": len(tools),
            },
        )
        return tools

    def _load_server_config(self) -> Dict[str, dict]:
        raw = os.getenv("MCP_SERVER_CONFIG_JSON", "").strip()
        if not raw:
            log.info("mcp_not_configured")
            return {}

        try:
            config = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("mcp_bad_config_json", extra={"error": str(exc)})
            return {}

        if not isinstance(config, dict):
            log.warning("mcp_bad_config_shape", extra={"detail": "Expected a JSON object keyed by server name."})
            return {}
        return config

    def _filter_config_for_role(self, role: str, server_config: Dict[str, dict]) -> Dict[str, dict]:
        names = _parse_server_names(os.getenv(f"MCP_{role.upper()}_SERVER_NAMES", ""))
        if not names:
            return dict(server_config)
        return {name: server_config[name] for name in names if name in server_config}

    def _load_tools(self, server_config: Dict[str, dict]) -> List:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        async def get_tools() -> List:
            client = MultiServerMCPClient(server_config)
            return await client.get_tools()

        return _run_async_in_thread(get_tools()) or []