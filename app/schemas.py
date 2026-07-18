"""Extraction presets: what to pull out of a page and how to analyze it."""


def _record_schema(props: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": props, "required": required},
            }
        },
        "required": ["items"],
    }


PRESETS: dict[str, dict] = {
    "products": {
        "label": "Products — name, price, rating, category",
        "hint": "product listings, shop pages, catalogs",
        "schema": _record_schema(
            {
                "name": {"type": "string"},
                "price": {"type": ["number", "null"]},
                "rating": {"type": ["number", "null"]},
                "category": {"type": ["string", "null"]},
            },
            ["name"],
        ),
        "numeric": ["price", "rating"],
        "categorical": ["category"],
        "sample": "laptops",
    },
    "posts": {
        "label": "Posts — title, score, comments, author",
        "hint": "forums, news aggregators, discussion boards",
        "schema": _record_schema(
            {
                "title": {"type": "string"},
                "score": {"type": ["number", "null"]},
                "comments": {"type": ["number", "null"]},
                "author": {"type": ["string", "null"]},
            },
            ["title"],
        ),
        "numeric": ["score", "comments"],
        "categorical": ["author"],
        "sample": "forum",
    },
}

SAMPLES: dict[str, dict] = {
    "laptops": {"file": "laptops.html", "label": "Sample: laptop store listing", "preset": "products"},
    "forum": {"file": "forum.html", "label": "Sample: dev forum front page", "preset": "posts"},
}

INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        }
    },
    "required": ["insights"],
}
