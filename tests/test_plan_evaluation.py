import datetime
import importlib.util
import sys
from pathlib import Path

import pytest
from docx import Document

from frontend_render_client.plan_evaluation import compute_evaluation


START = datetime.date(2026, 11, 6)
END = datetime.date(2026, 11, 7)


def evaluate(text, query="Plan sightseeing, food, hotel and transport with a budget"):
    return compute_evaluation(query, text, "New Delhi", "Goa", START, END)


def test_year_alone_does_not_count_as_dates():
    scores = evaluate("New Delhi to Goa in 2026")
    assert scores[2] == 1
    assert scores[3] == 0
    assert scores[1] == 0.5


def test_common_date_formats_and_ordinals():
    for dates in ("2026-11-06 to 2026-11-07", "6th November 2026 to November 7, 2026", "06/11/2026 to 07/11/2026"):
        assert evaluate("New Delhi to Goa " + dates)[3] == 1


def test_wrong_year_and_partial_city_are_not_accepted():
    scores = evaluate("Delhi to Goa, November 6, 2025 to November 7, 2025")
    assert scores[2] == 0.5
    assert scores[3] == 0


def test_filler_cannot_earn_completeness_or_structure():
    scores = evaluate("holiday " * 1000)
    assert scores[4] == 0
    assert scores[6] == 0


def test_budget_words_without_amounts_are_not_full_credit():
    assert evaluate("budget price cost per night hotel food transport activities")[5] == 0


def test_complete_plan_outscores_incomplete_plan():
    plan = """New Delhi to Goa, 6 November 2026 to 7 November 2026
Day 1: Arrival
Morning: flight transfer to hotel, visit a museum.
Afternoon: lunch at a restaurant. Check weather and reserve tickets.
Day 2: Return
Morning: explore a park. Afternoon: taxi and return flight.
Estimated budget per person for the entire trip:
Hotel: INR 2000
Food: INR 1000
Transport: INR 3000
Activities: INR 500
Grand total: INR 6500
"""
    scores = evaluate(plan)
    assert scores[1:4] == (1, 1, 1)
    assert scores[4] == 1
    assert scores[5] == 1
    assert scores[6] == 1
    assert scores[-1] > evaluate("Goa holiday in 2026")[-1]


def test_missing_or_duplicate_days_reduce_structure():
    day = "Day 1\nMorning: visit a museum. Afternoon: explore a park.\n"
    assert evaluate(day)[6] < 1
    assert evaluate(day + day)[6] < evaluate(day)[6]


def test_inconsistent_explicit_subtotals_reduce_budget_score():
    budget = """Estimated budget per person:
Hotel subtotal: INR 2000
Food subtotal: INR 1000
Transport subtotal: INR 3000
Activities subtotal: INR 500
Grand total: INR 6500
"""
    assert evaluate(budget)[5] > evaluate(budget.replace("INR 6500", "INR 9999"))[5]


def test_empty_answer_has_zero_scores():
    assert evaluate("") == (0,) * 8


def test_markdown_budget_amounts_are_recognized():
    assert evaluate("Estimated hotel: **INR** **2,000** per night")[5] == evaluate(
        "Estimated hotel: INR 2,000 per night"
    )[5]


def test_repeated_time_label_is_not_multiple_time_slots():
    one_slot = "Day 1\nMorning: visit a museum. Morning: explore a park."
    two_slots = one_slot.replace("Morning: explore", "Afternoon: explore")
    assert evaluate(one_slot)[6] < evaluate(two_slots)[6]


@pytest.mark.parametrize("module_name", ["app", "frontend_render_client.app"])
def test_frontend_and_word_report_use_new_metrics(module_name, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "metrics-test-only")
    monkeypatch.setenv("FASTAPI_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("RESET_PLANS_ON_START", "false")
    root = Path(__file__).resolve().parents[1]
    path = root / ("app.py" if module_name == "app" else "frontend_render_client/app.py")
    test_name = "_metrics_root_app" if module_name == "app" else "frontend_render_client._metrics_test_app"
    spec = importlib.util.spec_from_file_location(test_name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, test_name, module)
    spec.loader.exec_module(module)
    assert module.compute_evaluation is compute_evaluation
    trip = {
        "departure_city": "New Delhi", "destination_city": "Goa",
        "departure_date": "2026-11-06", "return_date": "2026-11-07",
    }
    scores = evaluate("New Delhi to Goa in 2026")
    names = ("relevance", "accuracy", "location_accuracy", "date_accuracy", "completeness",
             "budget_realism", "structure_quality", "overall_score")
    stored = {"plans": [("Original Plan", "Sample itinerary")], **dict(zip(names, scores))}
    monkeypatch.setattr(module, "load_plan", lambda plan_id: stored)
    client = module.app.test_client()
    with client.session_transaction() as browser_session:
        browser_session["plan_id"] = "test-plan"
        browser_session["trip_details"] = trip
    response = client.get("/")
    assert response.status_code == 200
    rendered = response.get_data(as_text=True)
    for label in ("Trip Alignment", "Date Coverage", "Budget Detail", "Overall Coverage Score"):
        assert label in rendered
    assert "Budget Realism" not in rendered
    document = Document(module.generate_word_doc(stored["plans"], trip, *scores))
    report = "\n".join(paragraph.text for paragraph in document.paragraphs)
    cells = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
    assert "Overall Coverage Score" in report
    assert "Budget Detail" in cells
    assert "not verify factual accuracy" in report