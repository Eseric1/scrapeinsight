from app.analyze import analyze
from app.schemas import PRESETS


RECORDS = [
    {"name": "A", "price": 100, "rating": 4.0, "category": "Budget"},
    {"name": "B", "price": 200, "rating": 4.5, "category": "Gaming"},
    {"name": "C", "price": 300, "rating": 3.5, "category": "Gaming"},
    {"name": "D", "price": 400, "rating": 5.0, "category": "Budget"},
    {"name": "E", "price": 500, "rating": 4.2, "category": "Gaming"},
]


def test_numeric_stats():
    stats = analyze(RECORDS, PRESETS["products"])
    assert stats["row_count"] == 5
    price = stats["numeric"]["price"]
    assert price == {"count": 5, "mean": 300.0, "median": 300.0, "min": 100.0, "max": 500.0}


def test_charts_present():
    stats = analyze(RECORDS, PRESETS["products"])
    ids = {c["id"] for c in stats["charts"]}
    assert "hist-price" in ids
    assert "top-category" in ids
    assert "scatter-price-rating" in ids


def test_category_counts():
    stats = analyze(RECORDS, PRESETS["products"])
    assert stats["categories"]["category"] == {"Gaming": 3, "Budget": 2}


def test_handles_missing_and_dirty_values():
    dirty = [
        {"name": "A", "price": "not-a-number", "rating": None},
        {"name": "B"},
        {"name": "C", "price": 50},
    ]
    stats = analyze(dirty, PRESETS["products"])
    assert stats["row_count"] == 3
    assert stats["numeric"]["price"]["count"] == 1


def test_empty_records():
    stats = analyze([], PRESETS["products"])
    assert stats["row_count"] == 0
    assert stats["charts"] == []
