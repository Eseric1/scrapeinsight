import json

from app.scraper import jsonld_products


def _page(payload) -> str:
    return f'<script type="application/ld+json">{json.dumps(payload)}</script>'


def test_itemlist_wrapped_products_lego_shape():
    page = _page(
        {
            "@type": "ItemList",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "item": {
                        "@type": "Product",
                        "name": "X-Wing",
                        "url": "https://lego.com/p/1",
                        "image": "https://lego.com/i/1.png",
                        "offers": {"@type": "Offer", "price": "49.99"},
                    },
                }
            ],
        }
    )
    [rec] = jsonld_products(page, category="Star Wars sets")
    assert rec["name"] == "X-Wing"
    assert rec["price"] == 49.99
    assert rec["category"] == "Star Wars sets"
    assert rec["url"] == "https://lego.com/p/1"
    assert rec["image"] == "https://lego.com/i/1.png"


def test_standalone_product_ikea_shape():
    page = _page(
        {
            "@type": "Product",
            "@id": "https://ikea.com/p/micke#product",
            "name": "MICKE Desk",
            "url": "https://ikea.com/p/micke",
            "offers": {
                "@type": "Offer",
                "priceSpecification": [{"@type": "UnitPriceSpecification", "price": 99.99}],
            },
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.5},
        }
    )
    [rec] = jsonld_products(page)
    assert rec["price"] == 99.99
    assert rec["rating"] == 4.5


def test_dedupes_and_tolerates_junk():
    good = {"@type": "Product", "name": "A", "offers": {"price": "5"}}
    page = (
        _page([good, good, {"@type": "Product", "name": ""}])
        + '<script type="application/ld+json">not json</script>'
    )
    recs = jsonld_products(page)
    assert len(recs) == 1


def test_image_list_and_non_http_urls_dropped():
    page = _page(
        {
            "@type": "Product",
            "name": "B",
            "url": "javascript:alert(1)",
            "image": ["https://x.com/a.png", "https://x.com/b.png"],
        }
    )
    [rec] = jsonld_products(page)
    assert rec["url"] is None
    assert rec["image"] == "https://x.com/a.png"
