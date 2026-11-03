from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify, session, make_response, abort
import requests
import datetime
import time
import sqlite3
import json
import glob
from io import BytesIO
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import re
import html
import os
import secrets
from dotenv import load_dotenv
from uuid import uuid4
import json as _json
import logging
import sys

# -----------------------------
# Structured logging (JSON-lines, matches the FastAPI backend's format so
# both services' logs can be aggregated/queried the same way)
# -----------------------------
class _JsonFormatter(logging.Formatter):
    _RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in self._RESERVED:
                try:
                    _json.dumps(value)
                    payload[key] = value
                except TypeError:
                    payload[key] = str(value)
        return _json.dumps(payload, default=str)


_log_handler = logging.StreamHandler(stream=sys.stdout)
_log_handler.setFormatter(_JsonFormatter())
log = logging.getLogger("ai_trip_planner.flask")
log.handlers = [_log_handler]
log.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
log.propagate = False

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

# -----------------------------
# Word document design tokens
# -----------------------------
# Centralized so the whole document reads as one consistent, designed
# document rather than default python-docx output.
DOC_ACCENT = RGBColor(0x0F, 0x4C, 0x81)       # deep travel-blue (titles, accents)
DOC_ACCENT_LIGHT = "D9E8F5"                    # light blue table/heading shading (hex, no '#')
DOC_TEXT_MUTED = RGBColor(0x5A, 0x63, 0x70)    # muted slate for captions/footers
DOC_SUCCESS = RGBColor(0x1E, 0x7E, 0x34)       # green - good scores
DOC_WARNING = RGBColor(0xB8, 0x86, 0x0B)       # amber - middling scores
DOC_DANGER = RGBColor(0xB0, 0x2A, 0x2A)        # red - low scores
DOC_BODY_FONT = "Calibri"
DOC_HEADING_FONT = "Calibri Light"

# -----------------------------
# Flask app setup
# -----------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY is not set. Add it to your .env file "
        "(generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\")"
    )
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL")
if not FASTAPI_BASE_URL:
    raise RuntimeError("FASTAPI_BASE_URL is not set. Add it to your .env file.")

# How long a generated plan is kept before it's eligible for cleanup (seconds)
PLAN_TTL_SECONDS = int(os.getenv("PLAN_TTL_SECONDS", str(24 * 60 * 60)))
# How long a generated translation audio file is kept before cleanup (seconds)
AUDIO_TTL_SECONDS = int(os.getenv("AUDIO_TTL_SECONDS", str(60 * 60)))

# -----------------------------
# Persistent plan storage (SQLite)
# -----------------------------
# A plain in-memory dict doesn't survive a restart and isn't shared across
# multiple worker processes (common on cPanel/Passenger), so plans are kept
# in a small local SQLite database instead.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans.db")
RESET_PLANS_ON_START = os.getenv("RESET_PLANS_ON_START", "true").lower() in ("1", "true", "yes")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plans (
            plan_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    return conn


def reset_all_plans():
    """Delete all stored plans (used when forcing a clean app startup)."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM plans")
        conn.commit()
    finally:
        conn.close()


def cleanup_expired_plans(conn):
    cutoff = time.time() - PLAN_TTL_SECONDS
    conn.execute("DELETE FROM plans WHERE created_at < ?", (cutoff,))
    conn.commit()


def save_plan(plan_id, data):
    conn = get_db()
    try:
        cleanup_expired_plans(conn)
        conn.execute(
            "INSERT INTO plans (plan_id, data, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(plan_id) DO UPDATE SET data=excluded.data",
            (plan_id, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def load_plan(plan_id):
    conn = get_db()
    try:
        cleanup_expired_plans(conn)
        row = conn.execute(
            "SELECT data FROM plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def cleanup_old_audio_files(static_dir, max_age_seconds=AUDIO_TTL_SECONDS):
    """Delete generated translation audio files older than max_age_seconds."""
    cutoff = time.time() - max_age_seconds
    for path in glob.glob(os.path.join(static_dir, "audio_*.mp3")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


if RESET_PLANS_ON_START:
    reset_all_plans()


# How long to wait for the AI backend to generate/refine an itinerary.
# Refinement prompts include the whole existing plan plus instructions, so
# they can take noticeably longer than the initial generation — and on
# Render's free tier the service can also need 30-60s just to "wake up"
# from an idle/sleeping state before it starts working on the request at all.
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "240"))


def call_ai_backend(question, chat_history="", retries=1):
    """
    POST a question to the FastAPI backend's /query endpoint.

    Returns (answer, error_message, meta). error_message is None on
    success. `meta` is a dict with `agents_used` (list of agent names that
    ran) and `agent_status` (list of {agent, status, duration_ms/detail}
    dicts) so the UI can show which specialists contributed and flag any
    that degraded — empty on error.

    Retries once on timeout/connection errors, since the very first request
    after the Render instance has been idle is the one most likely to be
    slow (cold start) or to drop the connection.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                f"{FASTAPI_BASE_URL}/query",
                json={"question": question, "chat_history": chat_history},
                timeout=QUERY_TIMEOUT_SECONDS
            )
            if resp.status_code == 200:
                payload = resp.json()
                answer = payload.get("answer")
                if isinstance(answer, str) and answer.strip():
                    meta = {
                        "agents_used": payload.get("agents_used", []),
                        "agent_status": payload.get("agent_status", []),
                    }
                    return answer, None, meta

                # Treat empty answer as a transient backend failure and retry once.
                last_error = (
                    "The AI backend returned an empty itinerary. "
                    "Please try again in a few seconds."
                )
                continue
            else:
                last_error = f"Backend returned an error (status {resp.status_code})."
                # Don't retry on a real server-side error response, only on
                # network-level failures below.
                break
        except requests.exceptions.Timeout:
            last_error = (
                f"The AI backend didn't respond within {QUERY_TIMEOUT_SECONDS} seconds. "
                "This usually means it's still generating a long itinerary, or the "
                "free Render instance needed to wake up from sleep. Please try again — "
                "it's often much faster on the next attempt."
            )
        except requests.exceptions.ConnectionError:
            last_error = (
                "Couldn't connect to the AI backend. It may be waking up from "
                "sleep (common on Render's free tier) — please wait a few seconds "
                "and try again."
            )
        except Exception as e:
            last_error = f"Failed to reach backend: {e}"
            break  # unexpected error, don't retry blindly

    return None, last_error, {"agents_used": [], "agent_status": []}

# Make sessions permanent
@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = __import__('datetime').timedelta(hours=24)

# -----------------------------
# Suggestions and languages
# -----------------------------
suggestion_map = {
    "🏔 More Adventure": "Make the itinerary more adventurous with hiking, trekking, and outdoor activities.",
    "🍽 More Food Spots": "Add more food recommendations, street foods, restaurants, and local cuisine.",
    "💸 Budget-Friendly": "Modify the trip to be more budget-friendly with cheaper stays and low-cost activities.",
    "🧘 Slow & Relaxed": "Make the trip more relaxed with slow travel and less hectic days.",
    "👨‍👩‍👧 Family-Friendly": "Modify the trip to be family-friendly with kid-safe attractions."
}

languages = {
    "Hindi": "hi",
    "Marathi": "mr",
    "Tamil": "ta",
    "Telugu": "te",
    "Kannada": "kn",
    "Gujarati": "gu",
    "Bengali": "bn",
    "Punjabi": "pa",
    "Malayalam": "ml",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Chinese": "zh",
    "Japanese": "ja",
}

# -----------------------------
# Helpers
# -----------------------------
_stopwords = {
    "the","and","for","with","that","this","from","will","your","you","are",
    "a","an","to","in","on","of","it","is","as","by","at","or","be","we","but","not","have","has","if","all","our","more","about"
}

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = s.lower()
    s = re.sub(r"[^\w\s\-\/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokenize(text: str):
    text = normalize_text(text)
    tokens = [t for t in text.split() if len(t) > 1 and t not in _stopwords]
    return tokens

def extract_keywords_from_query(query: str, max_keywords: int = 40):
    tokens = tokenize(query)
    tokens = sorted(set(tokens), key=lambda t: (-len(t), t))
    return tokens[:max_keywords]

def compute_evaluation(user_query: str, answer_text: str, departure_city: str, destination_city: str,
                       departure_date: datetime.date, return_date: datetime.date):
    """
    Heuristic, keyword-based evaluation of a generated itinerary.

    IMPORTANT: this is NOT a real quality judgment. It only checks surface
    signals (keyword overlap, whether the city/date strings appear, word
    count, presence of budget/structure-related words). It does not verify
    that the itinerary is factually correct, safe, or actually good — it
    can't tell if the AI made up a restaurant or hallucinated a hotel.
    Treat the scores as a rough content-coverage check, not a guarantee of
    quality. For a real quality signal, have a separate model/service grade
    the answer (e.g. an LLM-as-judge call to your FastAPI backend) instead
    of relying on this string-matching heuristic.

    Returns: (relevance, accuracy, location_accuracy, date_accuracy, completeness, budget_realism, structure_quality, overall_score)
    """
    q = normalize_text(user_query)
    a = normalize_text(answer_text)
    answer_word_count = len(a.split())

    # RELEVANCE - fraction of distinct query keywords that show up in the answer
    q_tokens = extract_keywords_from_query(q, max_keywords=80)
    a_tokens = set(tokenize(a))
    matched_tokens = [t for t in q_tokens if t in a_tokens]
    relevance = float(len(matched_tokens) / len(q_tokens)) if q_tokens else 0.0

    # LOCATION ACCURACY - fraction of supplied cities that appear in the answer
    location_checks = 0
    location_total = 0
    if departure_city:
        location_total += 1
        dept_norm = normalize_text(departure_city)
        if dept_norm and (dept_norm in a or any(word in a for word in dept_norm.split())):
            location_checks += 1
    if destination_city:
        location_total += 1
        dest_norm = normalize_text(destination_city)
        if dest_norm and (dest_norm in a or any(word in a for word in dest_norm.split())):
            location_checks += 1
    location_accuracy = float(location_checks / location_total) if location_total else 0.0

    # DATE ACCURACY - fraction of supplied dates that appear in some recognizable form
    def date_mentioned(d):
        variants = [
            d.strftime("%Y-%m-%d"),
            d.strftime("%d-%b-%Y"),
            d.strftime("%B %d, %Y"),
            d.strftime("%b %d"),
            d.strftime("%d %B"),
        ]
        return any(v.lower() in a for v in variants)

    date_checks = 0
    date_total = 0
    if departure_date:
        date_total += 1
        if date_mentioned(departure_date):
            date_checks += 1
    if return_date:
        date_total += 1
        if date_mentioned(return_date):
            date_checks += 1
    date_accuracy = float(date_checks / date_total) if date_total else 0.0

    # COMPLETENESS - word count relative to a "full itinerary" target of ~600 words
    completeness = float(min(1.0, answer_word_count / 600.0))

    # BUDGET REALISM - presence of cost/price-related vocabulary
    budget_keywords = {"price", "cost", "budget", "usd", "dollar", "per", "fee", "rate", "night", "hour", "expense", "rupees", "inr"}
    budget_mentions = sum(1 for kw in budget_keywords if kw in a)
    budget_realism = float(min(1.0, budget_mentions / len(budget_keywords)))

    # STRUCTURE QUALITY - presence of day-by-day / itinerary organizing vocabulary
    structure_keywords = {"day", "morning", "afternoon", "evening", "activity", "accommodation", "restaurant", "visit", "explore", "itinerary", "stay", "meal"}
    structure_mentions = sum(1 for kw in structure_keywords if kw in a)
    structure_quality = float(min(1.0, structure_mentions / len(structure_keywords)))

    # ACCURACY - fraction of the specific fields (cities + dates) that are actually present
    field_count = 0
    field_found = 0
    if departure_city:
        field_count += 1
        dept_norm = normalize_text(departure_city).split()
        if any(part in a for part in dept_norm if len(part) > 2):
            field_found += 1
    if destination_city:
        field_count += 1
        dest_norm = normalize_text(destination_city).split()
        if any(part in a for part in dest_norm if len(part) > 2):
            field_found += 1
    if departure_date:
        field_count += 1
        if date_mentioned(departure_date) or str(departure_date.year) in a:
            field_found += 1
    if return_date:
        field_count += 1
        if date_mentioned(return_date) or str(return_date.year) in a:
            field_found += 1
    accuracy = float(field_found / field_count) if field_count else 0.0

    # OVERALL SCORE - weighted combination, no artificial floor
    overall_score = (
        relevance * 0.25 +
        accuracy * 0.25 +
        location_accuracy * 0.15 +
        date_accuracy * 0.10 +
        completeness * 0.15 +
        structure_quality * 0.10
    )
    overall_score = float(min(1.0, overall_score))

    return relevance, accuracy, location_accuracy, date_accuracy, completeness, budget_realism, structure_quality, overall_score


_link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")
_url_pattern = re.compile(r"(https?://[^\s<>)]+)")
_bold_pattern = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_italic_pattern = re.compile(r"\*(.+?)\*|_(.+?)_")
_code_pattern = re.compile(r"`([^`]+)`")


def normalize_markdown_text(markdown_text: str) -> str:
    """Normalize markdown text emitted by LLMs to improve DOCX parsing."""
    if not markdown_text:
        return ""

    text = (
        markdown_text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
    )

    # Keep markdown line semantics stable.
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("\u2013", "-").replace("\u2014", "-")

    normalized_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        # Remove markdown hard-break trailing spaces from model output.
        line = re.sub(r"\s{2,}$", "", line)
        normalized_lines.append(line)

    return "\n".join(normalized_lines)


def add_hyperlink(paragraph, text, url):
    """Insert a clickable hyperlink into a python-docx paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    r_pr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(underline)

    run.append(r_pr)
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_text_with_urls(paragraph, text):
    """Append text to a paragraph and convert plain URLs into hyperlinks."""
    cursor = 0
    for match in _url_pattern.finditer(text):
        if match.start() > cursor:
            paragraph.add_run(text[cursor:match.start()])
        url = match.group(1)
        add_hyperlink(paragraph, url, url)
        cursor = match.end()
    if cursor < len(text):
        paragraph.add_run(text[cursor:])


def add_inline_markdown(paragraph, text):
    """Render basic inline markdown (links, bold, italics, code) into runs."""
    cursor = 0
    link_matches = list(_link_pattern.finditer(text))
    segments = []

    for match in link_matches:
        if match.start() > cursor:
            segments.append(("text", text[cursor:match.start()]))
        segments.append(("link", (match.group(1), match.group(2))))
        cursor = match.end()

    if cursor < len(text):
        segments.append(("text", text[cursor:]))

    for seg_type, value in segments:
        if seg_type == "link":
            link_text, link_url = value
            add_hyperlink(paragraph, link_text, link_url)
            continue

        remaining = value
        pos = 0
        while pos < len(remaining):
            token_match = None
            token_kind = None
            for kind, pattern in (("bold", _bold_pattern), ("italic", _italic_pattern), ("code", _code_pattern)):
                m = pattern.search(remaining, pos)
                if m and (token_match is None or m.start() < token_match.start()):
                    token_match = m
                    token_kind = kind

            if token_match is None:
                if pos < len(remaining):
                    add_text_with_urls(paragraph, remaining[pos:])
                break

            if token_match.start() > pos:
                add_text_with_urls(paragraph, remaining[pos:token_match.start()])

            content = next((g for g in token_match.groups() if g is not None), "")
            run = paragraph.add_run(content)
            if token_kind == "bold":
                run.bold = True
            elif token_kind == "italic":
                run.italic = True
            elif token_kind == "code":
                run.font.name = "Consolas"
                run.font.size = Pt(10)

            pos = token_match.end()


def _parse_table_row(line: str):
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_table_separator(line: str):
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cleaned = stripped.replace("|", "").replace(":", "").replace("-", "")
    return cleaned == ""


def add_markdown_block_to_doc(doc, markdown_text: str):
    """Render markdown-like itinerary text into a structured DOCX layout."""
    markdown_text = normalize_markdown_text(markdown_text)
    lines = markdown_text.splitlines()
    i = 0
    paragraph_buffer = []

    def flush_paragraph():
        nonlocal paragraph_buffer
        if paragraph_buffer:
            paragraph_text = " ".join(s.strip() for s in paragraph_buffer if s.strip())
            if paragraph_text:
                p = doc.add_paragraph()
                add_inline_markdown(p, paragraph_text)
            paragraph_buffer = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        # ATX headings (#, ##, ###...)
        heading_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if heading_match:
            flush_paragraph()
            level = min(len(stripped) - len(stripped.lstrip("#")), 4)
            heading = doc.add_heading(level=level)
            add_inline_markdown(heading, heading_match.group(1).strip())
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            flush_paragraph()
            doc.add_paragraph("")
            i += 1
            continue

        # Table block
        if "|" in stripped and (i + 1) < len(lines) and _is_table_separator(lines[i + 1]):
            flush_paragraph()
            header_cells = _parse_table_row(lines[i])
            table_rows = []
            i += 2  # skip header and separator
            while i < len(lines):
                row_line = lines[i].strip()
                if not row_line or "|" not in row_line:
                    break
                if _is_table_separator(row_line):
                    i += 1
                    continue
                table_rows.append(_parse_table_row(row_line))
                i += 1

            col_count = max(1, len(header_cells))
            table = doc.add_table(rows=1, cols=col_count)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True

            for col_idx in range(col_count):
                hdr_text = header_cells[col_idx] if col_idx < len(header_cells) else ""
                cell = table.rows[0].cells[col_idx]
                _set_cell_background(cell, DOC_ACCENT_LIGHT)
                cell_par = cell.paragraphs[0]
                add_inline_markdown(cell_par, hdr_text)
                for run in cell_par.runs:
                    run.bold = True
                    run.font.color.rgb = DOC_ACCENT
                _set_cell_margins(cell)

            for row_idx, row_cells in enumerate(table_rows):
                row = table.add_row()
                for col_idx in range(col_count):
                    val = row_cells[col_idx] if col_idx < len(row_cells) else ""
                    cell = row.cells[col_idx]
                    if row_idx % 2 == 1:
                        _set_cell_background(cell, "F4F7FB")  # subtle zebra striping
                    cell_par = cell.paragraphs[0]
                    add_inline_markdown(cell_par, val)
                    _set_cell_margins(cell)
            doc.add_paragraph("")  # breathing room after a table
            continue

        # Bulleted list
        bullet_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if bullet_match:
            flush_paragraph()
            indent_spaces = len(bullet_match.group(1).replace("\t", "    "))
            style_name = "List Bullet 2" if indent_spaces >= 2 else "List Bullet"
            try:
                p = doc.add_paragraph(style=style_name)
            except KeyError:
                p = doc.add_paragraph(style="List Bullet")
            add_inline_markdown(p, bullet_match.group(2).strip())
            i += 1
            continue

        # Numbered list
        numbered_match = re.match(r"^(\s*)\d+[\.)]\s+(.+)$", line)
        if numbered_match:
            flush_paragraph()
            indent_spaces = len(numbered_match.group(1).replace("\t", "    "))
            style_name = "List Number 2" if indent_spaces >= 2 else "List Number"
            try:
                p = doc.add_paragraph(style=style_name)
            except KeyError:
                p = doc.add_paragraph(style="List Number")
            add_inline_markdown(p, numbered_match.group(2).strip())
            i += 1
            continue

        # Block quote
        quote_match = re.match(r"^>\s?(.+)$", stripped)
        if quote_match:
            flush_paragraph()
            p = doc.add_paragraph()
            run = p.add_run(quote_match.group(1).strip())
            run.italic = True
            i += 1
            continue

        paragraph_buffer.append(line)
        i += 1

    flush_paragraph()

def _set_cell_background(cell, hex_color: str):
    """Set a table cell's background shading (hex string, no '#')."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shd)


def _set_cell_margins(cell, top=60, bottom=60, left=100, right=100):
    """Give table cells breathing room (values in twentieths of a point)."""
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for tag, val in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tcPr.append(mar)


def _add_bottom_border(paragraph, color="0F4C81", size=12):
    """Add a colored horizontal rule under a paragraph (used as section dividers)."""
    p_pr = paragraph._p.get_or_add_pPr()
    p_borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    p_borders.append(bottom)
    p_pr.append(p_borders)


def _add_page_number_field(paragraph, prefix="Page ", middle=" of ", suffix=""):
    """Insert a live 'Page X of Y' field into a header/footer paragraph."""
    run = paragraph.add_run(prefix)
    run.font.size = Pt(9)
    run.font.color.rgb = DOC_TEXT_MUTED

    def _field(instr_text):
        r = paragraph.add_run()
        r.font.size = Pt(9)
        r.font.color.rgb = DOC_TEXT_MUTED
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = instr_text
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        r._r.append(fld_begin)
        r._r.append(instr)
        r._r.append(fld_sep)
        r._r.append(fld_end)

    _field("PAGE")
    mid_run = paragraph.add_run(middle)
    mid_run.font.size = Pt(9)
    mid_run.font.color.rgb = DOC_TEXT_MUTED
    _field("NUMPAGES")
    if suffix:
        end_run = paragraph.add_run(suffix)
        end_run.font.size = Pt(9)
        end_run.font.color.rgb = DOC_TEXT_MUTED


def _apply_base_styles(doc):
    """Set up document-wide typography and margins so every page looks
    consistent, instead of relying on python-docx's plain defaults."""
    normal = doc.styles["Normal"]
    normal.font.name = DOC_BODY_FONT
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0x2B, 0x2B, 0x2B)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15

    heading_sizes = {1: 22, 2: 16, 3: 13, 4: 11}
    for level, size in heading_sizes.items():
        style = doc.styles[f"Heading {level}"]
        style.font.name = DOC_HEADING_FONT
        style.font.color.rgb = DOC_ACCENT
        style.font.size = Pt(size)
        style.font.bold = level <= 2
        style.paragraph_format.space_before = Pt(18 if level == 1 else 12)
        style.paragraph_format.space_after = Pt(8)

    section = doc.sections[0]
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)


def _add_header_footer(doc, trip_details):
    """Slim running header (route) and footer (brand + live page numbers)
    on every page after the title page."""
    section = doc.sections[0]

    header_p = section.header.paragraphs[0]
    header_p.text = ""
    route = f"{trip_details.get('departure_city', '')} → {trip_details.get('destination_city', '')}"
    header_run = header_p.add_run(route.strip(" →") or "AI Trip Plan")
    header_run.font.size = Pt(9)
    header_run.font.color.rgb = DOC_TEXT_MUTED
    header_run.bold = True
    header_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _add_bottom_border(header_p, color="D9E8F5", size=6)

    footer_p = section.footer.paragraphs[0]
    footer_p.text = ""
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_page_number_field(footer_p)


def _add_title_page(doc, trip_details):
    """A clean cover page: brand mark, trip title, route, and dates —
    the first thing a reader sees instead of a plain 'Heading 1'."""
    # Vertical spacer to push the title block toward the page's center.
    for _ in range(4):
        doc.add_paragraph("")

    eyebrow = doc.add_paragraph()
    eyebrow.alignment = WD_ALIGN_PARAGRAPH.CENTER
    eyebrow_run = eyebrow.add_run("AI TRIP PLANNER  •  MULTI-AGENT ITINERARY")
    eyebrow_run.font.size = Pt(10)
    eyebrow_run.font.color.rgb = DOC_TEXT_MUTED
    eyebrow_run.bold = True

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.add_run(
        f"{trip_details.get('departure_city', '')} → {trip_details.get('destination_city', '')}"
    )
    title_run.font.name = DOC_HEADING_FONT
    title_run.font.size = Pt(32)
    title_run.font.bold = True
    title_run.font.color.rgb = DOC_ACCENT
    _add_bottom_border(title, color="0F4C81", size=16)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_before = Pt(14)
    subtitle_run = subtitle.add_run(
        f"{trip_details.get('departure_date', '')}  to  {trip_details.get('return_date', '')}"
    )
    subtitle_run.font.size = Pt(14)
    subtitle_run.font.color.rgb = RGBColor(0x44, 0x4B, 0x57)

    generated = doc.add_paragraph()
    generated.alignment = WD_ALIGN_PARAGRAPH.CENTER
    generated.paragraph_format.space_before = Pt(40)
    generated_run = generated.add_run(
        f"Generated on {datetime.date.today().strftime('%d %B %Y')}"
    )
    generated_run.font.size = Pt(10)
    generated_run.font.color.rgb = DOC_TEXT_MUTED
    generated_run.italic = True

    doc.add_page_break()


def _score_color(score: float):
    if score >= 0.75:
        return DOC_SUCCESS
    if score >= 0.5:
        return DOC_WARNING
    return DOC_DANGER


def _add_metrics_table(doc, metrics):
    """Render the quality-evaluation numbers as a color-coded table instead
    of a stack of plain bullet paragraphs."""
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    for idx, text in enumerate(("Metric", "Score (out of 1.00)")):
        _set_cell_background(header_cells[idx], DOC_ACCENT_LIGHT)
        _set_cell_margins(header_cells[idx])
        run = header_cells[idx].paragraphs[0].add_run(text)
        run.bold = True
        run.font.color.rgb = DOC_ACCENT

    for row_idx, (label, value) in enumerate(metrics):
        row = table.add_row()
        label_cell, score_cell = row.cells
        _set_cell_margins(label_cell)
        _set_cell_margins(score_cell)
        if row_idx % 2 == 1:
            _set_cell_background(label_cell, "F4F7FB")
            _set_cell_background(score_cell, "F4F7FB")

        label_cell.paragraphs[0].add_run(label)

        score_run = score_cell.paragraphs[0].add_run(f"{value:.2f}")
        score_run.bold = True
        score_run.font.color.rgb = _score_color(value)

    return table


def generate_word_doc(plans, trip_details, relevance, accuracy, location_accuracy=0.0,
                      date_accuracy=0.0, completeness=0.0, budget_realism=0.0,
                      structure_quality=0.0, overall_score=0.0):
    doc = Document()

    # Document properties (shows up in Word's File > Info panel).
    core_props = doc.core_properties
    core_props.title = (
        f"Trip Plan: {trip_details.get('departure_city', '')} to "
        f"{trip_details.get('destination_city', '')}"
    )
    core_props.author = "AI Trip Planner"
    core_props.subject = "AI-generated travel itinerary"

    _apply_base_styles(doc)
    _add_header_footer(doc, trip_details)
    _add_title_page(doc, trip_details)

    # ---- Trip summary as a clean label/value table instead of bare text ----
    doc.add_heading("Trip Summary", level=1)
    summary_rows = [
        ("From", trip_details.get("departure_city", "")),
        ("To", trip_details.get("destination_city", "")),
        ("Departure Date", trip_details.get("departure_date", "")),
        ("Return Date", trip_details.get("return_date", "")),
        ("Plan Generated", datetime.date.today().strftime("%d %B %Y")),
    ]
    summary_table = doc.add_table(rows=0, cols=2)
    summary_table.style = "Table Grid"
    for row_idx, (label, value) in enumerate(summary_rows):
        row = summary_table.add_row()
        label_cell, value_cell = row.cells
        _set_cell_margins(label_cell)
        _set_cell_margins(value_cell)
        _set_cell_background(label_cell, DOC_ACCENT_LIGHT)
        if row_idx % 2 == 1:
            _set_cell_background(value_cell, "F4F7FB")
        label_run = label_cell.paragraphs[0].add_run(label)
        label_run.bold = True
        label_run.font.color.rgb = DOC_ACCENT
        value_cell.paragraphs[0].add_run(str(value))
    doc.add_paragraph("")

    # ---- Itinerary section(s) ----
    for title, plan in plans:
        doc.add_heading(title, level=1)
        add_markdown_block_to_doc(doc, plan)
        doc.add_page_break()

    # ---- Plan quality evaluation ----
    doc.add_heading("Plan Quality Evaluation", level=1)

    overall_p = doc.add_paragraph()
    overall_label = overall_p.add_run("Overall Quality Score: ")
    overall_label.bold = True
    overall_value = overall_p.add_run(f"{overall_score:.2f} / 1.00")
    overall_value.bold = True
    overall_value.font.size = Pt(14)
    overall_value.font.color.rgb = _score_color(overall_score)

    note = doc.add_paragraph()
    note_run = note.add_run(
        "This is a heuristic, keyword-based coverage check (relevance, "
        "location/date mentions, structure, and length), not a verified "
        "judgment of factual accuracy — always double-check prices, hours, "
        "and travel requirements before you go."
    )
    note_run.italic = True
    note_run.font.size = Pt(9)
    note_run.font.color.rgb = DOC_TEXT_MUTED

    doc.add_paragraph("")
    _add_metrics_table(doc, [
        ("Relevance — keywords matched to plan content", relevance),
        ("Accuracy — location/date fields present", accuracy),
        ("Location Accuracy", location_accuracy),
        ("Date Accuracy", date_accuracy),
        ("Completeness — length vs. a full itinerary", completeness),
        ("Budget Realism — cost/price vocabulary present", budget_realism),
        ("Structure Quality — day-by-day organization", structure_quality),
    ])

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    plans = []
    trip_details = session.get("trip_details", {})
    relevance = session.get("relevance", 0.0)
    accuracy = session.get("accuracy", 0.0)
    location_accuracy = session.get("location_accuracy", 0.0)
    date_accuracy = session.get("date_accuracy", 0.0)
    completeness = session.get("completeness", 0.0)
    budget_realism = session.get("budget_realism", 0.0)
    structure_quality = session.get("structure_quality", 0.0)
    overall_score = session.get("overall_score", 0.0)
    agent_status = []

    # Retrieve plans from server-side storage if plan_id exists
    plan_id = session.get("plan_id")
    stored = load_plan(plan_id) if plan_id else None
    if stored:
        plans = stored["plans"]
        relevance = stored.get("relevance", 0.0)
        accuracy = stored.get("accuracy", 0.0)
        location_accuracy = stored.get("location_accuracy", 0.0)
        date_accuracy = stored.get("date_accuracy", 0.0)
        completeness = stored.get("completeness", 0.0)
        budget_realism = stored.get("budget_realism", 0.0)
        structure_quality = stored.get("structure_quality", 0.0)
        overall_score = stored.get("overall_score", 0.0)
        agent_status = stored.get("agent_status", [])

    if request.method == "POST":
        departure_city = request.form.get("departure_city")
        destination_city = request.form.get("destination_city")
        departure_date = request.form.get("departure_date")
        return_date = request.form.get("return_date")

        if not departure_city or not destination_city:
            flash("Please fill in both departure and destination cities.", "warning")
        elif return_date < departure_date:
            flash("Return date cannot be before departure date.", "warning")
        else:
            # Store new trip details (don't clear, just update)
            trip_details = {
                "departure_city": departure_city,
                "destination_city": destination_city,
                "departure_date": departure_date,
                "return_date": return_date
            }

            session["trip_details"] = trip_details

            auto_query = (
                f"Create a complete travel itinerary for a trip from "
                f"{departure_city} to {destination_city}, departing on {departure_date} and returning on {return_date}. "
                f"Include sightseeing, food, restaurants, budgeting, travel tips, day-wise break-up, airport/railway shops, useful apps with links."
            )

            call_start = time.time()
            backend_answer, error_message, agent_meta = call_ai_backend(auto_query, chat_history="")
            log.info("plan_generated" if error_message is None else "plan_generation_failed", extra={
                "duration_ms": round((time.time() - call_start) * 1000, 1),
                "agents_used": agent_meta.get("agents_used", []),
                "error": error_message,
            })

            if error_message is None:
                # Store as single Original Plan
                plans = [("Original Plan", backend_answer)]

                metrics = compute_evaluation(
                    auto_query,
                    backend_answer,
                    departure_city,
                    destination_city,
                    datetime.datetime.strptime(departure_date, "%Y-%m-%d").date(),
                    datetime.datetime.strptime(return_date, "%Y-%m-%d").date()
                )
                relevance, accuracy, location_accuracy, date_accuracy, completeness, budget_realism, structure_quality, overall_score = metrics

                # Store plans on server side, keep only ID in session
                plan_id = str(uuid4())
                save_plan(plan_id, {
                    "plans": plans,
                    "relevance": relevance,
                    "accuracy": accuracy,
                    "location_accuracy": location_accuracy,
                    "date_accuracy": date_accuracy,
                    "completeness": completeness,
                    "budget_realism": budget_realism,
                    "structure_quality": structure_quality,
                    "overall_score": overall_score,
                    "agent_status": agent_meta.get("agent_status", []),
                })
                session["plan_id"] = plan_id
                session["relevance"] = relevance
                session["accuracy"] = accuracy
                session["location_accuracy"] = location_accuracy
                session["date_accuracy"] = date_accuracy
                session["completeness"] = completeness
                session["budget_realism"] = budget_realism
                session["structure_quality"] = structure_quality
                session["overall_score"] = overall_score
                session.modified = True
            else:
                flash(error_message, "danger")


    return render_template(
        "index.html",
        plans=plans,
        trip_details=trip_details,
        relevance=relevance,
        accuracy=accuracy,
        location_accuracy=location_accuracy,
        date_accuracy=date_accuracy,
        completeness=completeness,
        budget_realism=budget_realism,
        structure_quality=structure_quality,
        overall_score=overall_score,
        agent_status=agent_status,
        suggestion_map=suggestion_map,
        languages=languages
    )


@app.route("/refine", methods=["POST"])
def refine():
    refine_option = request.form.get("refine_option", "").strip()
    custom_refine = request.form.get("custom_refine", "").strip()

    plan_id = session.get("plan_id")
    trip_details = session.get("trip_details", {})

    # Get plans from server storage
    stored = load_plan(plan_id) if plan_id else None
    if not stored:
        flash("No plan available to refine.", "warning")
        return redirect(url_for("index"))

    plans = stored["plans"]

    # Refinement is optional – user submitted without input
    if not refine_option and not custom_refine:
        flash("No refinement applied. You can continue with the current plan.", "info")
        return redirect(url_for("index"))
    
    # Take the first plan text (Original Plan)
    plan_text = plans[0][1]

    instructions = []

    if refine_option:
        instructions.append(refine_option)

    if custom_refine:
        instructions.append(
            f"User's explicit custom instructions (high priority): {custom_refine}"
        )

    combined_instructions = " ".join(instructions)

    refine_query = (
        f"You are refining an existing travel plan.\n\n"
        f"EXISTING PLAN:\n{plan_text}\n\n"
        f"REFINEMENT INSTRUCTIONS:\n{combined_instructions}\n\n"
        f"Provide a complete, newly refined itinerary. "
        f"Do not summarize. Do not reference the old plan explicitly."
    )

    call_start = time.time()
    refined_answer, error_message, agent_meta = call_ai_backend(refine_query, chat_history="")
    log.info("plan_refined" if error_message is None else "plan_refine_failed", extra={
        "duration_ms": round((time.time() - call_start) * 1000, 1),
        "agents_used": agent_meta.get("agents_used", []),
        "error": error_message,
    })

    if error_message is None:
        # Append the refined plan instead of replacing
        plans.append((f"Refined Plan ({len(plans)})", refined_answer))

        # Update server storage
        if trip_details:
            departure_date = datetime.datetime.strptime(trip_details['departure_date'], "%Y-%m-%d").date()
            return_date = datetime.datetime.strptime(trip_details['return_date'], "%Y-%m-%d").date()
            metrics = compute_evaluation(
                refine_query,
                refined_answer,
                trip_details['departure_city'],
                trip_details['destination_city'],
                departure_date,
                return_date
            )
            relevance, accuracy, location_accuracy, date_accuracy, completeness, budget_realism, structure_quality, overall_score = metrics
        else:
            relevance = stored.get("relevance", 0.0)
            accuracy = stored.get("accuracy", 0.0)
            location_accuracy = stored.get("location_accuracy", 0.0)
            date_accuracy = stored.get("date_accuracy", 0.0)
            completeness = stored.get("completeness", 0.0)
            budget_realism = stored.get("budget_realism", 0.0)
            structure_quality = stored.get("structure_quality", 0.0)
            overall_score = stored.get("overall_score", 0.0)

        save_plan(plan_id, {
            "plans": plans,
            "relevance": relevance,
            "accuracy": accuracy,
            "location_accuracy": location_accuracy,
            "date_accuracy": date_accuracy,
            "completeness": completeness,
            "budget_realism": budget_realism,
            "structure_quality": structure_quality,
            "overall_score": overall_score,
            "agent_status": agent_meta.get("agent_status", []),
        })
        session["relevance"] = relevance
        session["accuracy"] = accuracy
        session["overall_score"] = overall_score
        session.modified = True

        flash("Plan refined successfully. Original plan is preserved.", "success")
    else:
        flash(error_message, "danger")

    return redirect(url_for("index"))


@app.route("/clear", methods=["GET"])
def clear():
    """Clear the session to start fresh"""
    session.clear()
    flash("Session cleared. Ready for a new trip!", "info")
    return redirect(url_for("index"))


@app.route("/translate", methods=["POST"])
def translate():
    data = request.get_json()
    text_to_translate = data.get("text")
    language_code = data.get("language")

    if not text_to_translate or not language_code:
        return jsonify({"error": "Text or language not provided"}), 400

    translated_text = None
    audio_url = None

    try:
        payload = {"text": text_to_translate, "target_language": language_code}
        resp = requests.post(f"{FASTAPI_BASE_URL}/translate", json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            translated_text = result.get("translated_text")
            audio_list = result.get("audio_bytes")
            if audio_list and isinstance(audio_list, list):
                static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
                os.makedirs(static_dir, exist_ok=True)
                cleanup_old_audio_files(static_dir)
                audio_bytes = bytes(audio_list)
                filename = f"audio_{int(datetime.datetime.now().timestamp())}_{secrets.token_hex(4)}.mp3"
                audio_path = os.path.join(static_dir, filename)
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                audio_url = f"/static/{filename}"
        else:
            return jsonify({"error": resp.text}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"translated_text": translated_text, "audio_url": audio_url})

@app.route("/insurance", methods=["POST"])
def insurance():
    age = request.form.get("age")
    coverage_type = request.form.get("coverage_type")

    try:
        age = int(age)
        if age <= 0 or age > 120:
            raise ValueError("age out of range")
    except (TypeError, ValueError):
        return jsonify({"error": "Please provide a valid age between 1 and 120."}), 400

    if not coverage_type:
        return jsonify({"error": "Please select a coverage type."}), 400

    insurance_quotes = []
    try:
        payload = {
            "destination": request.form.get("destination_city", ""),
            "trip_start": request.form.get("departure_date", ""),
            "trip_end": request.form.get("return_date", ""),
            "age": age,
            "travelers": 1,
            "coverage_type": coverage_type
        }
        resp = requests.post(f"{FASTAPI_BASE_URL}/insurance/squaremouth", json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            insurance_quotes = data.get("insurance_quotes", {}).get("plans", [])
        else:
            return jsonify({"error": resp.text}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(insurance_quotes)

@app.route("/download", methods=["POST"])
def download():
    # Prefer server-side state to avoid browser/form encoding or stale-page issues.
    plan_id = session.get("plan_id")
    stored = load_plan(plan_id) if plan_id else None

    if stored and stored.get("plans"):
        plans = stored.get("plans", [])
        trip_details = session.get("trip_details", {})
        relevance = float(stored.get("relevance", 0.0))
        accuracy = float(stored.get("accuracy", 0.0))
        location_accuracy = float(stored.get("location_accuracy", 0.0))
        date_accuracy = float(stored.get("date_accuracy", 0.0))
        completeness = float(stored.get("completeness", 0.0))
        budget_realism = float(stored.get("budget_realism", 0.0))
        structure_quality = float(stored.get("structure_quality", 0.0))
        overall_score = float(stored.get("overall_score", 0.0))
    else:
        # Fallback path (kept for compatibility): use posted form fields.
        plan_texts = request.form.getlist("plan_text")
        plan_titles = request.form.getlist("plan_title")
        plans = []
        for i, text in enumerate(plan_texts):
            title = plan_titles[i].strip() if i < len(plan_titles) and plan_titles[i].strip() else f"Plan {i+1}"
            plans.append((title, text))

        trip_details = {
            "departure_city": request.form.get("departure_city"),
            "destination_city": request.form.get("destination_city"),
            "departure_date": request.form.get("departure_date"),
            "return_date": request.form.get("return_date")
        }
        relevance = float(request.form.get("relevance", 0.0))
        accuracy = float(request.form.get("accuracy", 0.0))
        location_accuracy = float(request.form.get("location_accuracy", 0.0))
        date_accuracy = float(request.form.get("date_accuracy", 0.0))
        completeness = float(request.form.get("completeness", 0.0))
        budget_realism = float(request.form.get("budget_realism", 0.0))
        structure_quality = float(request.form.get("structure_quality", 0.0))
        overall_score = float(request.form.get("overall_score", 0.0))

    if not plans:
        flash("No plan found to download. Please generate a trip plan first.", "warning")
        return redirect(url_for("index"))

    trip_details = {
        "departure_city": trip_details.get("departure_city", ""),
        "destination_city": trip_details.get("destination_city", ""),
        "departure_date": trip_details.get("departure_date", ""),
        "return_date": trip_details.get("return_date", ""),
    }

    buffer = generate_word_doc(plans, trip_details, relevance, accuracy, 
                              location_accuracy, date_accuracy, completeness, 
                              budget_realism, structure_quality, overall_score)
    return send_file(
        buffer,
        download_name=f"Trip_Plan_Formatted_v2_{datetime.date.today().isoformat()}.docx",
        as_attachment=True
    )

if __name__ == "__main__":
    # Debug mode (interactive debugger + auto-reload) is opt-in only.
    # NEVER run with debug=True on a server reachable from the internet —
    # the Werkzeug debugger allows arbitrary code execution.
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(debug=debug_mode)
