"""Load and normalise the raw Bauhaus product export into clean records.

The raw JSON is messy: German price strings ("43,99 €"), no category field, and
compatibility buried in a free-text blob. This module produces one clean, typed
record per product so every downstream tool works with predictable data. It calls
the verified attributes parser for compatibility and derives a coarse category
from title keywords (there is no category field in the source).
"""
from __future__ import annotations

import glob
import json
import os
import re
from functools import lru_cache

from .attributes import parse_systems, parse_voice_assistants

DATA_GLOB = "data/products/info/*.json"

# Category keywords in PRIORITY order (first match wins). Built from a scan of the
# real catalog's title vocabulary, which is lighting-heavy.
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("camera", ("überwachungskamera", "kamera", "camera")),
    ("motion_sensor", ("bewegungsmelder", "melder", "sensor")),
    ("thermostat", ("thermostat", "heizkörper", "heizung")),
    ("lock", ("türschloss", "türöffner", "schloss")),
    ("shutter", ("rollladen", "markise", "jalousie", "funk-empfangsmodul")),
    ("plug_adapter", ("steckdose", "zwischenstecker", "adapter", "stecker")),
    ("speaker", ("lautsprecher", "speaker", "echo")),
    ("lighting", ("lampe", "leuchte", "licht", "deckenleuchte", "deckenstrahler",
                  "strahler", "wandleuchte", "spot", "panel", "ambiance", "hue",
                  "tint", "leuchtmittel", "glühbirne", "birne", "led", "lighting")),
]


def _parse_price(raw: str) -> float | None:
    """'43,99 €' -> 43.99. German format: dot thousands, comma decimals."""
    if not raw:
        return None
    cleaned = raw.replace("€", "").replace(".", "").replace(",", ".").strip()
    m = re.search(r"\d+(\.\d+)?", cleaned)
    return float(m.group()) if m else None


def _derive_category(title: str) -> str:
    t = (title or "").lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(k in t for k in keywords):
            return category
    return "other"


def _normalise(raw: dict) -> dict:
    attrs = raw.get("attributes", "")
    return {
        "id": str(raw.get("id", "")).strip(),
        "title": raw.get("title", "").strip(),
        "subtitle": raw.get("subtitle", "").strip(),
        "price_eur": _parse_price(raw.get("price", "")),
        "voice_assistants": parse_voice_assistants(attrs),
        "systems": parse_systems(attrs),
        "category": _derive_category(raw.get("title", "")),
        "description": raw.get("description", "").strip(),
        "url": raw.get("url", "").strip(),
    }


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict]:
    """Load every product once, keyed by id. Skips macOS '._' junk files."""
    files = [f for f in glob.glob(DATA_GLOB)
             if not os.path.basename(f).startswith("._")]
    if not files:
        raise FileNotFoundError(
            f"No product files at {DATA_GLOB}. Unzip products.zip into data/products/."
        )
    catalog: dict[str, dict] = {}
    for path in files:
        with open(path, encoding="utf-8") as fh:
            product = _normalise(json.load(fh))
        if not product["id"]:
            product["id"] = os.path.splitext(os.path.basename(path))[0]
        catalog[product["id"]] = product
    return catalog


def get_product(product_id: str) -> dict | None:
    return load_catalog().get(product_id)


def all_products() -> list[dict]:
    return list(load_catalog().values())
