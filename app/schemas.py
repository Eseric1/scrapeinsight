"""Curated live targets + the product extraction preset.

Free-URL analysis was removed deliberately: a public demo scraping arbitrary
attacker-chosen pages is a liability. Targets below are well-known brand
category pages, each verified live to be server-rendered with JSON-LD
product data (probed 2026-07-19; bot-walled brands were rejected).
"""

DISPLAY_CAP = 16


TARGETS: dict[str, dict] = {
    "lego": {
        "label": "LEGO — all sets",
        "brand": "LEGO",
        "category": "LEGO sets",
        "mode": "jsonld",
        "url": "https://www.lego.com/en-us/categories/all-sets",
    },
    "ikea": {
        "label": "IKEA — furniture",
        "brand": "IKEA",
        "category": "Furniture",
        "mode": "jsonld",
        "url": "https://www.ikea.com/us/en/cat/furniture-fu001/",
    },
    "keychron": {
        "label": "Keychron — mechanical keyboards",
        "brand": "Keychron",
        "category": "Keyboards",
        "mode": "shopify",
        "url": "https://www.keychron.com/collections/keyboard/products.json?limit=30",
        "base": "https://www.keychron.com",
    },
    "8bitdo": {
        "label": "8BitDo — game controllers",
        "brand": "8BitDo",
        "category": "Game controllers",
        "mode": "shopify",
        "url": "https://shop.8bitdo.com/collections/all/products.json?limit=30",
        "base": "https://shop.8bitdo.com",
    },
    "spigen": {
        "label": "Spigen — cases & chargers",
        "brand": "Spigen",
        "category": "Phone accessories",
        "mode": "shopify",
        "url": "https://www.spigen.com/collections/all/products.json?limit=30",
        "base": "https://www.spigen.com",
    },
    "wyze": {
        "label": "Wyze — smart home",
        "brand": "Wyze",
        "category": "Smart home",
        "mode": "shopify",
        "url": "https://www.wyze.com/collections/all/products.json?limit=30",
        "base": "https://www.wyze.com",
    },
    "satechi": {
        "label": "Satechi — Mac & USB-C accessories",
        "brand": "Satechi",
        "category": "Tech accessories",
        "mode": "shopify",
        "url": "https://satechi.net/collections/all/products.json?limit=30",
        "base": "https://satechi.net",
    },
    "twelvesouth": {
        "label": "Twelve South — Apple accessories",
        "brand": "Twelve South",
        "category": "Apple accessories",
        "mode": "shopify",
        "url": "https://www.twelvesouth.com/collections/all/products.json?limit=30",
        "base": "https://www.twelvesouth.com",
    },
    "moft": {
        "label": "MOFT — stands & wallets",
        "brand": "MOFT",
        "category": "Stands & wallets",
        "mode": "shopify",
        "url": "https://www.moft.us/collections/all-products/products.json?limit=30",
        "base": "https://www.moft.us",
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
