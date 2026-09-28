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

_GERMAN_WORDS = {
    "ich", "du", "sie", "wir", "mir", "mich", "mein", "meine", "ihr", "ihnen",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "und", "oder", "aber", "für", "mit", "von", "zu", "zum", "zur", "auf", "im", "in",
    "ist", "sind", "hat", "habe", "haben", "kann", "können", "möchte", "brauche",
    "suche", "nutze", "welche", "welcher", "welches", "wie", "was", "wen", "wer",
    "gibt", "es", "nicht", "kein", "keine", "bitte", "maximal", "unter", "zwei",
    "empfehle", "empfiehl", "vergleiche", "funktioniert", "smarte", "smartes",
}
_EN_WORDS = {"i", "the", "a", "an", "and", "or", "for", "with", "my", "is", "are",
             "what", "which", "how", "do", "does", "can", "please", "that", "to"}


def detect_language(text: str) -> str:
    """'de' or 'en' for a user message. Stopword vote, umlauts as a tie-breaker."""
    tokens = _WORD_RE.findall((text or "").lower())
    de = sum(t in _GERMAN_WORDS for t in tokens)
    en = sum(t in _EN_WORDS for t in tokens)
    if de == en:
        return "de" if re.search(r"[äöüß]", text.lower()) else "en"
    return "de" if de > en else "en"


def _last_user_text(req: LlmRequest) -> str:
    """Latest user-typed text. Skips function responses, which also carry role 'user'."""
    for content in reversed(req.contents or []):
        if content.role != "user":
            continue
        text = " ".join((part.text or "") for part in (content.parts or [])).strip()
        if text:
            return text.lower()
    return ""


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
    """Pin the reply language, then block electrical wiring/installation requests.

    Runs before every model call in a turn, including the calls after tool results.
    Tool output (titles, prices) is German catalogue data, which used to pull English
    conversations into German, so the user's language is detected in code and pinned
    in the system instruction instead of being left to the model.
    """
    text = _last_user_text(llm_request)
    if text:
        callback_context.state["user_language"] = detect_language(text)
    lang = callback_context.state.get("user_language", "en")
    if _is_wiring(text):
        callback_context.state["guardrail_triggered"] = "safety_wiring"
        message = REFUSAL_DE if lang == "de" else REFUSAL_EN
        return LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=message)])
        )
    name = "German" if lang == "de" else "English"
    llm_request.append_instructions([
        f"REPLY LANGUAGE: {name}. The customer wrote in {name}, so write your whole reply in "
        f"{name}. Tool results and product titles are German catalogue data: keep titles "
        f"verbatim, but never switch the reply language because of them."
    ])
    return None
