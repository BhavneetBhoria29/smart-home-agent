"""Unit tests for the deterministic layer.

The LLM is non-deterministic, but everything it depends on — compatibility parsing,
filtering, upsell selection, guardrails — is deterministic and therefore testable.
These lock down the properties that must never regress, above all: never affirm an
incompatible product.
"""
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from smart_home_agent.catalog.attributes import parse_voice_assistants, resolve_ecosystem
from smart_home_agent.catalog.loader import all_products, get_product
from smart_home_agent.catalog.retrieval import filter_products
from smart_home_agent.guardrails.callbacks import safety_guardrail
from smart_home_agent.tools.compare import compare_products
from smart_home_agent.tools.recommend import (
    check_compatibility,
    get_upsell_suggestions,
    search_products,
)


class _Ctx:
    def __init__(self):
        self.state = {}


def _req(text: str) -> LlmRequest:
    return LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text=text)])])


def _alexa_product():
    return next(p for p in all_products() if "Amazon Alexa" in p["voice_assistants"])


def _non_alexa_product():
    return next(p for p in all_products()
                if p["voice_assistants"] and "Amazon Alexa" not in p["voice_assistants"])


# --- Parser -------------------------------------------------------------------

def test_parser_only_returns_known_assistants():
    for p in all_products():
        for a in p["voice_assistants"]:
            assert a in {"Amazon Alexa", "Google Assistant", "Apple Siri"}


def test_ecosystem_alias_resolves():
    assert resolve_ecosystem("Google Home") == "Google Assistant"
    assert resolve_ecosystem("alexa") == "Amazon Alexa"
    assert resolve_ecosystem("HomeKit") == "Apple Siri"


# --- Compatibility (highest-stakes correctness) -------------------------------

def test_compatible_product_accepted():
    p = _alexa_product()
    assert check_compatibility(p["id"], "Alexa")["compatible"] is True


def test_incompatible_product_rejected():
    p = _non_alexa_product()
    assert check_compatibility(p["id"], "Alexa")["compatible"] is False


def test_unknown_product_errors():
    assert check_compatibility("nonexistent-id", "Alexa")["status"] == "error"


# --- Filtering / search -------------------------------------------------------

def test_filter_never_returns_incompatible():
    for p in filter_products(ecosystem="Apple Siri"):
        assert "Apple Siri" in p["voice_assistants"]


def test_search_tool_respects_ecosystem():
    res = search_products(query="lampe", ecosystem="Google")
    for p in res["results"]:
        assert "Google Assistant" in p["voice_assistants"]


def test_price_cap_applied():
    for p in filter_products(max_price=20.0):
        assert p["price_eur"] is not None and p["price_eur"] <= 20.0


# --- Upsell (primary KPI) -----------------------------------------------------

def test_upsell_returns_same_category_upgrades():
    p = _alexa_product()
    up = get_upsell_suggestions(p["id"])
    for u in up["upgrades"]:
        assert u["category"] == p["category"]


def test_upsell_never_downgrades_compatibility():
    p = _alexa_product()
    base_ecos = set(p["voice_assistants"])
    result = get_upsell_suggestions(p["id"])
    for u in result["upgrades"] + result["add_ons"]:
        assert base_ecos.issubset(set(get_product(u["id"])["voice_assistants"]))


# --- Comparison ---------------------------------------------------------------

def test_compare_requires_two():
    assert compare_products(["only-one"])["status"] == "error"


def test_compare_builds_table():
    ids = [p["id"] for p in all_products()[:2]]
    cmp = compare_products(ids)
    assert cmp["status"] == "success" and len(cmp["table"]) == 2


# --- Guardrail ----------------------------------------------------------------

def test_guardrail_blocks_english_wiring():
    assert safety_guardrail(_Ctx(), _req("how do I wire this to the mains")) is not None


def test_guardrail_blocks_german_wiring():
    assert safety_guardrail(_Ctx(), _req("Stromkabel an die Steckdose anschließen")) is not None


def test_guardrail_allows_normal_question():
    assert safety_guardrail(_Ctx(), _req("recommend a colour bulb for alexa")) is None


def test_guardrail_blocks_german_separable_verb():
    # "anschließen" splits as "schließe ... an" in natural German; substring match misses it
    assert safety_guardrail(
        _Ctx(), _req("Wie schließe ich das Kabel an die Steckdose an?")) is not None
    assert safety_guardrail(
        _Ctx(),
        _req("Ich will die Steckdose selbst anschließen, welches Kabel nehme ich?")) is not None


def test_guardrail_blocks_german_conjugated_verb():
    # infinitive "verkabeln" conjugates to "verkabele"
    assert safety_guardrail(_Ctx(), _req("Wie verkabele ich das Thermostat?")) is not None


def test_guardrail_blocks_english_electrical_connection():
    assert safety_guardrail(
        _Ctx(), _req("Is it safe if I do the electrical connection myself?")) is not None


def test_guardrail_allows_wireless_not_wire():
    # "wire" must not false-match inside "wireless" / "kabellos"
    assert safety_guardrail(_Ctx(), _req("recommend a wireless camera")) is None
    assert safety_guardrail(_Ctx(), _req("Ich möchte eine kabellose Kamera")) is None


def test_guardrail_allows_smart_plug_query():
    # asking which smart plug (Steckdose) works with Alexa is a normal shopping query
    assert safety_guardrail(_Ctx(), _req("Welche Steckdose funktioniert mit Alexa?")) is None
