"""Parser for the German `attributes` blob in each product JSON.

The raw export stores specs as a flat newline-delimited string of alternating
key/value lines:  "Farbe\nAnthrazit\nLänge\n45 mm\n...".  The two fields we care
about most supported voice assistants and supported systems are buried in
there as free text, not as structured JSON.  This module extracts and NORMALISES
them once, at load time, so every downstream tool works with clean typed data
and the compatibility check is exact rather than a guess.
"""
from __future__ import annotations

# The catalog only ever uses these three voice assistants (confirmed by scanning
# all 943 products). We normalise every mention to this canonical set, and we use
# the set to VALIDATE captured values so a key with no value (which would
# otherwise grab the next line) is rejected instead of polluting the data.
KNOWN_ASSISTANTS = {
    "amazon alexa": "Amazon Alexa",
    "google assistant": "Google Assistant",
    "apple siri": "Apple Siri",
}

# User-facing ecosystem words map onto the assistant that represents them, so a
# customer saying "Google Home" or "Alexa" resolves to the right catalog value.
ECOSYSTEM_ALIASES = {
    "alexa": "Amazon Alexa", "amazon": "Amazon Alexa", "amazon alexa": "Amazon Alexa",
    "echo": "Amazon Alexa",
    "google": "Google Assistant", "google home": "Google Assistant",
    "google assistant": "Google Assistant", "nest": "Google Assistant",
    "apple": "Apple Siri", "siri": "Apple Siri", "homekit": "Apple Siri",
    "apple homekit": "Apple Siri",
}

VOICE_KEY = "Unterstützte Sprachsteuerung"
SYSTEMS_KEY = "Unterstützte Systeme"
SMARTHOME_KEY = "Smart Home-fähig"


def _attribute_pairs(blob: str) -> dict[str, str]:
    """Turn the flat key/value line list into a dict {key: value}.

    We treat every other line as a value for the preceding line. This is naive by
    design the export is genuinely this flat but it's why we validate the
    fields we actually use rather than trusting every captured value.
    """
    lines = [ln.strip() for ln in (blob or "").split("\n") if ln.strip()]
    pairs: dict[str, str] = {}
    for i in range(0, len(lines) - 1):
        key, value = lines[i], lines[i + 1]
        # Only set a key once (first occurrence wins) to avoid a later stray
        # match overwriting a real value.
        pairs.setdefault(key, value)
    return pairs


def parse_voice_assistants(blob: str) -> list[str]:
    """Extract and normalise the supported voice assistants for one product.

    Returns e.g. ["Amazon Alexa", "Google Assistant"]. Returns [] when the product
    has no valid voice-assistant data which is correct, not an error.
    """
    pairs = _attribute_pairs(blob)
    raw = pairs.get(VOICE_KEY, "")
    found: list[str] = []
    for token in raw.split(","):
        canon = KNOWN_ASSISTANTS.get(token.strip().lower())
        # The validation step: only keep tokens that are real assistant names.
        # This is what discards the ~19 "no value" cases you saw in the scan.
        if canon and canon not in found:
            found.append(canon)
    return found


def parse_systems(blob: str) -> list[str]:
    """Extract the supported smart-home systems (secondary compatibility signal)."""
    pairs = _attribute_pairs(blob)
    raw = pairs.get(SYSTEMS_KEY, "")
    systems = [s.strip() for s in raw.split(",") if s.strip()]
    # Guard: if this field was empty, we might have grabbed an unrelated next line.
    # Systems always contain the word "System" (or a couple known exceptions), so
    # filter to those to stay clean.
    return [s for s in systems if "System" in s or "HomeKit" in s or "Nuki" in s]


def is_smart_home(blob: str) -> bool:
    """Whether the product is flagged smart-home capable at all."""
    return _attribute_pairs(blob).get(SMARTHOME_KEY, "").strip().lower() in {"ja", "yes"}


def resolve_ecosystem(user_text: str) -> str | None:
    """Map a user's ecosystem phrase ('Alexa', 'Google Home') to a canonical assistant."""
    return ECOSYSTEM_ALIASES.get((user_text or "").strip().lower())