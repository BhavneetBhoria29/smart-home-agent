"""Safety guardrail via ADK's before_model_callback.

Runs before the request reaches Gemini. Returning an LlmResponse short-circuits the
turn (the model is never called); returning None lets it proceed. Used to hard-block
electrical wiring / installation questions in the user's language before spending a
token. Matched on word-stems and token boundaries (not contiguous phrases), so
natural German separable verbs ("schließe ... an") and conjugations ("verkabele")
are caught and "wire" no longer false-matches inside "wireless"; the agent
instruction handles the softer, semantic domain-deflection.
"""
from __future__ import annotations

import re
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

# Electrical / installation risk vocabulary, EN + DE.
# Matched on stems + token boundaries (see _is_wiring) so natural German separable
# verbs ("schließe ... an") and conjugations ("verkabele") are caught, and "wire"
# does not false-match inside "wireless".
_WHOLE_WORD_STRONG = {
    "wire", "wires", "wiring", "rewire", "hardwire", "volt", "volts", "voltage",
    "mains", "electrocute", "230v", "240v",
}
_SUBSTR_STRONG = (
    "hard-wire", "fuse box", "circuit breaker", "terminal block", "live wire",
    "neutral wire", "earth wire", "high voltage", "electrocut",
    "verkabel", "verdraht", "stromkabel", "nullleiter", "sicherungskasten",
    "stromanschluss", "netzspannung", "hochspannung", "stromschlag", "anklemm",
)
# An electrical noun co-occurring with an install/connect action (anywhere in the
# sentence) blocks — this is what catches separable verbs split across the clause.
_ELEC_NOUN = {
    "wire", "wires", "cable", "cables", "outlet", "outlets", "socket", "sockets",
    "circuit", "electrical", "electric", "terminal", "fuse", "fusebox",
    "kabel", "kabels", "steckdose", "steckdosen", "strom", "leitung", "leitungen",
    "phase", "phasen", "sicherung", "spannung", "netz",
}
_ACTION = {
    "connect", "connection", "connecting", "connected", "install", "installation",
    "installing", "attach", "attaching", "hook", "hookup", "wire", "wiring",
    "anschließen", "anschliessen", "anschluss", "installieren", "verbinden",
    "verbinde", "verdrahten", "anklemmen", "anzuklemmen", "verkabeln",
}
_ACTION_STEM = ("anschließ", "anschliess", "installier", "verbind", "verkabel",
                "verdraht", "klemm")
_WORD_RE = re.compile(r"[a-zäöüß0-9]+")

REFUSAL_EN = (
    "For your safety, I can't advise on electrical wiring or installation. "
    "Please have a certified electrician handle that. I'm glad to help you choose "
    "the right smart-home product, though — would you like a recommendation?"
)
REFUSAL_DE = (
    "Aus Sicherheitsgründen kann ich keine Ratschläge zur elektrischen Verkabelung "
    "oder Installation geben. Bitte lassen Sie das von einer Elektrofachkraft erledigen. "
    "Gerne helfe ich Ihnen aber bei der Auswahl des passenden Smart-Home-Produkts – "
    "möchten Sie eine Empfehlung?"
)

_GERMAN_HINTS = {"ich", "wie", "die", "der", "das", "und", "für", "kann", "sie",
                 "kabel", "anschließen", "steckdose", "installieren"}


def _last_user_text(req: LlmRequest) -> str:
    for content in reversed(req.contents or []):
        if content.role == "user":
            return " ".join((part.text or "") for part in (content.parts or [])).lower()
    return ""


def _looks_german(text: str) -> bool:
    return len(set(text.split()) & _GERMAN_HINTS) >= 2


def _is_wiring(text: str) -> bool:
    """True if the (lower-cased) text is an electrical wiring / installation request.

    Stem- and token-based rather than contiguous-substring: it catches German
    separable verbs split across the sentence ("schließe ... das Kabel ... an") and
    conjugated forms ("verkabele"), without false-matching "wire" inside "wireless".
    """
    tokens = _WORD_RE.findall(text)
    tset = set(tokens)
    if tset & _WHOLE_WORD_STRONG:
        return True
    if any(term in text for term in _SUBSTR_STRONG):
        return True
    has_noun = bool(tset & _ELEC_NOUN)
    has_action = bool(tset & _ACTION) or any(t.startswith(_ACTION_STEM) for t in tokens)
    separable = "an" in tset and any(t.startswith(("schließ", "schliess")) for t in tokens)
    return has_noun and (has_action or separable)


def safety_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Block electrical wiring/installation requests before they reach the model."""
    text = _last_user_text(llm_request)
    if _is_wiring(text):
        callback_context.state["guardrail_triggered"] = "safety_wiring"
        message = REFUSAL_DE if _looks_german(text) else REFUSAL_EN
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=message)])
        )
    return None
