"""Deterministic itinerary coverage checks, not factual or live-data verification."""

import calendar
import datetime
import html
import re
from decimal import Decimal


def _text(value):
    value = html.unescape(value or "").lower()
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value)
    return re.sub(r"[ \t]+", " ", value)


def _contains(text, phrase):
    words = re.findall(r"\w+", _text(phrase))
    return bool(words and re.search(r"\b" + r"[\W_]+".join(map(re.escape, words)) + r"\b", text))


def _date_present(text, value):
    if not value:
        return False
    month = rf"(?:{calendar.month_name[value.month].lower()}|{calendar.month_abbr[value.month].lower()}\.?)"
    day = rf"0?{value.day}"
    year = str(value.year)
    numeric = [
        rf"{year}[-/]{value.month:02d}[-/]{value.day:02d}",
        rf"{day}[-/]0?{value.month}[-/]{year}",
    ]
    named = [rf"{day}[\s-]+{month}[\s,-]+{year}", rf"{month}[\s-]+{day}[\s,-]+{year}"]
    return bool(re.search(r"(?<!\d)(?:" + "|".join(numeric + named) + r")(?!\d)", text))


def _day_sections(text):
    matches = list(re.finditer(r"(?im)^\s*(?:#{1,6}\s*|\|\s*|\*{1,2})?day\s+(\d+)\b[^\n]*", text))
    return [
        (int(match.group(1)), text[match.start():matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        for index, match in enumerate(matches)
    ]


_CURRENCY = r"(?:inr|usd|eur|gbp|rs\.?|rupees?|dollars?|\$|\u20b9|\u20ac|\u00a3)"
_NUMBER = r"\d+(?:,\d{2,3})*(?:\.\d{1,2})?"


def _amounts(line):
    matches = re.findall(rf"{_CURRENCY}\s*({_NUMBER})(?![\d.])", line)
    matches += re.findall(rf"(?<![\w.])({_NUMBER})\s*{_CURRENCY}\b", line)
    return [Decimal(value.replace(",", "")) for value in matches]


def _budget_score(text):
    categories = {
        "lodging": r"\b(?:hotel|accommodation|lodging|hostel|stay)\b",
        "food": r"\b(?:food|meals?|dining)\b",
        "transport": r"\b(?:transport|flights?|trains?|taxis?|transit)\b",
        "activities": r"\b(?:activities|attractions?|tickets?|entry|admission)\b",
    }
    lines = text.splitlines()
    if not any(_amounts(line) for line in lines):
        return 0.0
    priced = [any(re.search(pattern, line) and _amounts(line) for line in lines) for pattern in categories.values()]
    total_lines = [line for line in lines if re.search(r"\b(?:grand total|trip total|total budget|estimated total|total cost)\b", line)]
    has_total = any(_amounts(line) for line in total_lines)
    has_basis = bool(re.search(r"\b(?:per person|per traveler|per night|per day|for \d+ (?:people|travelers|persons)|entire trip)\b", text))
    has_uncertainty = bool(re.search(r"\b(?:estimat\w*|approx\w*|indicative|subject to|prices vary)\b", text))
    score = 0.5 * sum(priced) / len(priced) + 0.2 * has_total + 0.15 * has_basis + 0.15 * has_uncertainty
    subtotal_lines = [line for line in lines if re.search(r"\bsubtotal\b", line)]
    if len(subtotal_lines) >= 2 and len(total_lines) == 1:
        subtotals = [_amounts(line) for line in subtotal_lines]
        totals = _amounts(total_lines[0])
        currencies = set(re.findall(_CURRENCY, "\n".join(subtotal_lines + total_lines)))
        if all(len(values) == 1 for values in subtotals) and len(totals) == 1 and len(currencies) == 1:
            expected = sum(values[0] for values in subtotals)
            if abs(expected - totals[0]) > max(Decimal("1"), expected * Decimal("0.01")):
                score *= 0.5
    return score


def compute_evaluation(user_query, answer_text, departure_city, destination_city,
                       departure_date: datetime.date, return_date: datetime.date):
    """Return eight 0..1 coverage scores using the legacy caller tuple order.

    Dates require day, month and year. Prices, places, source links and prose
    are not independently verified; budget scoring measures detail only.
    """
    text = _text(answer_text)
    locations = [_contains(text, city) for city in (departure_city, destination_city) if city]
    dates = [_date_present(text, value) for value in (departure_date, return_date) if value]
    location_score = sum(locations) / len(locations) if locations else 0.0
    date_score = sum(dates) / len(dates) if dates else 0.0
    fields = locations + dates
    alignment = sum(fields) / len(fields) if fields else 0.0

    expected_days = max(1, (return_date - departure_date).days + 1) if departure_date and return_date else 1
    sections = _day_sections(text)
    valid_days = {number for number, content in sections if 1 <= number <= expected_days}
    day_coverage = len(valid_days) / expected_days
    activities = r"\b(?:visit|explore|walk|tour|museum|beach|park|hike|sightseeing|activity|activities)\b"
    meals = r"\b(?:breakfast|lunch|dinner|restaurant|food|meal)\b"
    transport = r"\b(?:transport|train|flight|bus|taxi|metro|transfer|ferry|walk)\b"
    lodging = r"\b(?:hotel|hostel|accommodation|lodging|check.in|stay)\b"
    practical = r"\b(?:safety|emergency|visa|weather|forecast|insurance|booking|reserve)\b"
    checks = [bool(re.search(pattern, text)) for pattern in (activities, meals, transport, lodging, practical)]
    budget = _budget_score(text)
    completeness = 0.5 * day_coverage + 0.5 * (sum(checks) + bool(budget)) / 6
    timed_days = sum(
        1 for number, content in sections if 1 <= number <= expected_days
        and len(set(re.findall(r"\b(?:morning|afternoon|evening)\b|\b\d{1,2}:\d{2}\b", content))) >= 2
        and re.search(activities, content)
    )
    structure = 0.6 * day_coverage + 0.4 * min(timed_days, len(valid_days)) / expected_days
    if sections:
        structure *= len(valid_days) / len(sections)

    requested = []
    query = _text(user_query)
    for pattern in (activities, meals, transport, lodging, practical, r"\b(?:budget|cost|price|expense)\w*\b"):
        if re.search(pattern, query):
            requested.append(bool(re.search(pattern, text)))
    for preference in ("vegetarian", "vegan", "wheelchair", "family", "luxury", "relaxed", "adventure"):
        if _contains(query, preference):
            requested.append(_contains(text, preference))
    request_coverage = sum(requested) / len(requested) if requested else day_coverage
    relevance = 0.5 * alignment + 0.25 * day_coverage + 0.25 * request_coverage
    overall = 0.2 * relevance + 0.2 * alignment + 0.2 * completeness + 0.2 * budget + 0.2 * structure
    return tuple(round(max(0.0, min(1.0, value)), 4) for value in (
        relevance, alignment, location_score, date_score, completeness, budget, structure, overall
    ))