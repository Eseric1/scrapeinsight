"""Curated live targets + the product extraction preset.

Free-URL analysis was removed deliberately: a public demo scraping arbitrary
attacker-chosen pages is a liability. Targets below are well-known brand
category pages, each verified live to be server-rendered with JSON-LD
product data (probed 2026-07-19; bot-walled brands were rejected).
"""

DISPLAY_CAP = 16


TARGETS: dict[str, dict] = {
    "lego-star-wars": {
        "label": "LEGO — Star Wars sets",
        "brand": "LEGO",
        "category": "Star Wars sets",
        "url": "https://www.lego.com/en-us/themes/star-wars",
    },
    "lego-technic": {
        "label": "LEGO — Technic sets",
        "brand": "LEGO",
        "category": "Technic sets",
        "url": "https://www.lego.com/en-us/themes/technic",
    },
    "lego-city": {
        "label": "LEGO — City sets",
        "brand": "LEGO",
        "category": "City sets",
        "url": "https://www.lego.com/en-us/themes/city",
    },
    "ikea-desks": {
        "label": "IKEA — Desks",
        "brand": "IKEA",
        "category": "Desks",
        "url": "https://www.ikea.com/us/en/cat/desks-20649/",
    },
    "ikea-chairs": {
        "label": "IKEA — Office chairs",
        "brand": "IKEA",
        "category": "Office chairs",
        "url": "https://www.ikea.com/us/en/cat/office-chairs-20652/",
    },
    "ikea-sofas": {
        "label": "IKEA — Sofas",
        "brand": "IKEA",
        "category": "Sofas",
        "url": "https://www.ikea.com/us/en/cat/sofas-fu003/",
    },
}


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


# LLM fallback extraction schema — used only when a page has no JSON-LD
PRODUCTS_PRESET: dict = {
    "label": "Products — name, price, rating",
    "schema": _record_schema(
        {
            "name": {"type": "string"},
            "price": {"type": ["number", "null"]},
            "rating": {"type": ["number", "null"]},
        },
        ["name"],
    ),
    "numeric": ["price", "rating"],
    "categorical": ["category"],
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
