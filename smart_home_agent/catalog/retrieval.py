"""Retrieval: filter on hard constraints first, then BM25-rank the survivors.

Filtering before ranking keeps compatibility / category / price from ever being
ranked away. BM25 rather than embeddings because the catalogue is small and queries
are keyword-ish; a dense reranker would be the next step if recall needed it.
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from .loader import all_products


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß0-9]+", (text or "").lower())


def _doc_text(p: dict) -> str:
    return " ".join([p["title"], p["subtitle"], p["category"], p["description"]])


def filter_products(
    ecosystem: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """Apply the hard constraints (compatibility, category, price cap)."""
    results = all_products()
    if ecosystem:
        results = [p for p in results if ecosystem in p["voice_assistants"]]
    if category:
        results = [p for p in results if p["category"] == category]
    if max_price is not None:
        results = [p for p in results if p["price_eur"] is not None and p["price_eur"] <= max_price]
    return results


def rank_by_query(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """BM25-rank candidates by free-text query. No query -> cheapest first."""
    if not candidates:
        return []
    if not query or not query.strip():
        return sorted(candidates, key=lambda p: (p["price_eur"] is None, p["price_eur"] or 0))[:top_k]
    corpus = [_tokens(_doc_text(p)) for p in candidates]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokens(query))
    ranked = sorted(zip(candidates, scores), key=lambda cs: cs[1], reverse=True)
    return [p for p, _ in ranked[:top_k]]


def search(query="", ecosystem=None, category=None, max_price=None, top_k=5) -> list[dict]:
    return rank_by_query(query, filter_products(ecosystem, category, max_price), top_k)
