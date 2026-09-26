"""Recommendation tools exposed to the agent.

Tool docstrings double as the schema Gemini reads to decide when/how to call them,
so they're written for the model. Each returns a dict with a "status" field. The
business logic (compatibility, upsell selection) lives here in code, not the prompt.
"""
from __future__ import annotations

from ..catalog.attributes import resolve_ecosystem
from ..catalog.loader import get_product
from ..catalog.retrieval import search


def _summarise(p: dict) -> dict:
    return {
        "id": p["id"],
        "title": p["title"],
        "price_eur": p["price_eur"],
        "category": p["category"],
        "voice_assistants": p["voice_assistants"],
        "systems": p["systems"][:3],
    }


def search_products(query: str = "", ecosystem: str = "", category: str = "", max_price: float = 0.0) -> dict:
    """Search the smart-home catalog for products matching the user's needs.

    Pass the user's ecosystem whenever they state one, so only compatible products
    are returned. Compatibility is checked against real product data.

    Args:
        query: Free-text description, e.g. "colour smart bulb for the living room".
        ecosystem: User's ecosystem if known: "Amazon Alexa", "Google Assistant"/"Google Home", or "Apple Siri"/"HomeKit". Empty if unknown.
        category: Optional category filter: lighting, camera, motion_sensor, plug_adapter, thermostat, lock, shutter, speaker.
        max_price: Optional max price in EUR. Use 0.0 for no limit.

    Returns:
        dict with "status", "count", and a "results" list of matching products.
    """
    eco = resolve_ecosystem(ecosystem) if ecosystem else None
    limit = max_price if max_price and max_price > 0 else None
    hits = search(query=query, ecosystem=eco, category=(category or None), max_price=limit, top_k=5)
    return {
        "status": "success",
        "ecosystem_applied": eco,
        "count": len(hits),
        "results": [_summarise(p) for p in hits],
    }


def check_compatibility(product_id: str, ecosystem: str) -> dict:
    """Check whether a specific product supports a given voice assistant / ecosystem.

    Call this before confirming a recommendation when the user has stated an ecosystem.
    Compatibility is read from product data, never guessed.

    Args:
        product_id: The catalog id of the product to check.
        ecosystem: The user's ecosystem: "Amazon Alexa", "Google Assistant"/"Google Home", or "Apple Siri"/"HomeKit".

    Returns:
        dict with "status", "compatible" (bool) and "details".
    """
    product = get_product(product_id)
    if not product:
        return {"status": "error", "message": f"No product with id '{product_id}'."}
    eco = resolve_ecosystem(ecosystem)
    if not eco:
        return {"status": "error", "message": f"Unrecognised ecosystem '{ecosystem}'."}
    compatible = eco in product["voice_assistants"]
    return {
        "status": "success",
        "product": product["title"],
        "ecosystem": eco,
        "compatible": compatible,
        "details": (
            f"{product['title']} supports {product['voice_assistants']}."
            if compatible
            else f"{product['title']} does NOT support {eco}. It supports {product['voice_assistants']}."
        ),
    }


def get_upsell_suggestions(product_id: str, max_suggestions: int = 3) -> dict:
    """Suggest higher-value upgrades and complementary add-ons for a product.

    Call this after finding a suitable product to offer a better option and useful
    extras. Upgrades are only ever products compatible with at least the same
    ecosystems as the base, so we never upsell into an incompatible product.

    Args:
        product_id: The catalog id of the base product the customer is considering.
        max_suggestions: Max number of upgrades/add-ons to return each.

    Returns:
        dict with "status", "upgrades" (pricier, same category) and "add_ons" (cheaper, same category).
    """
    base = get_product(product_id)
    if not base:
        return {"status": "error", "message": f"No product with id '{product_id}'."}

    base_price = base["price_eur"] or 0
    base_ecos = set(base["voice_assistants"])
    from ..catalog.loader import all_products

    upgrades, add_ons = [], []
    for p in all_products():
        if p["id"] == base["id"] or p["price_eur"] is None:
            continue
        # only suggest something at least as compatible as the base
        if not base_ecos.issubset(set(p["voice_assistants"])):
            continue
        if p["category"] != base["category"]:
            continue  # keep upgrades and add-ons within the base category
        if p["price_eur"] > base_price:
            upgrades.append(p)
        elif p["price_eur"] < base_price:
            add_ons.append(p)

    upgrades.sort(key=lambda p: p["price_eur"])   # nearest step up first
    add_ons.sort(key=lambda p: -p["price_eur"])   # best add-on first
    return {
        "status": "success",
        "base_product": base["title"],
        "upgrades": [_summarise(p) for p in upgrades[:max_suggestions]],
        "add_ons": [_summarise(p) for p in add_ons[:max_suggestions]],
    }
