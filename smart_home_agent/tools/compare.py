"""Product comparison tool. Computes the comparison in Python so the model phrases
an accurate result rather than inventing specs."""
from __future__ import annotations

from ..catalog.loader import get_product


def compare_products(product_ids: list[str]) -> dict:
    """Compare two or more products from the catalog side by side.

    Args:
        product_ids: A list of at least two catalog product ids to compare.

    Returns:
        dict with "status" and a "table" of each product's title, price, category,
        supported voice assistants and systems, so the assistant can present an
        accurate comparison.
    """
    if not product_ids or len(product_ids) < 2:
        return {"status": "error", "message": "Provide at least two product ids to compare."}
    rows = []
    for pid in product_ids:
        p = get_product(pid)
        if not p:
            return {"status": "error", "message": f"No product with id '{pid}'."}
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "price_eur": p["price_eur"],
            "category": p["category"],
            "voice_assistants": p["voice_assistants"],
            "systems": p["systems"],
        })
    return {"status": "success", "table": rows}
