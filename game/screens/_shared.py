"""Shared constants and helpers used across all screen modules."""

from game.config import *  # IS_MAC, ACCENT_*, TEXT_*, BG_*, etc.


# Platform-aware reveal labels
# On Mac: player presses Mac keys → show keys_mac prominently
# On Windows: player presses AZERTY → show keys_win prominently
if IS_MAC:
    _LABEL_SMALL = "Reference Windows"
    _LABEL_BIG   = "Ton clavier (Mac)"
    _KEYS_SMALL  = 'keys_win'
    _KEYS_BIG    = 'keys_mac'
    _COLOR_BIG   = ACCENT_GREEN
else:
    _LABEL_SMALL = "Examen (QWERTY Mac)"
    _LABEL_BIG   = "Ton clavier (AZERTY)"
    _KEYS_SMALL  = 'keys_mac'
    _KEYS_BIG    = 'keys_win'
    _COLOR_BIG   = ACCENT_BLUE
_DBLCLICK_THRESHOLD = 0.4  # seconds max between two clicks for a double-click

# QWERTY position name → AZERTY character displayed at the same physical key.
# Used only for DISPLAY on the "Ton clavier (AZERTY)" side. Detection still
# uses QWERTY positional names everywhere (scan-code based).
_QWERTY_TO_AZERTY_DISPLAY = {
    'Q': 'A', 'W': 'Z', 'A': 'Q', 'Z': 'W', 'M': ',',
    ';': 'M', "'": 'ù', ',': ';', '.': ':', '/': '!',
    '[': '^', ']': '$', '\\': '*', '`': '²',
    '-': ')', '=': '=',
}


def _to_azerty_display(keys):
    """Translate a flat list of key names from QWERTY-positional to AZERTY
    characters (display only). Preserves modifiers, function keys, numpad,
    arrows, digits unchanged. On Mac, this is a no-op at call sites because
    _KEYS_BIG is 'keys_mac' there."""
    if not keys:
        return keys
    return [_QWERTY_TO_AZERTY_DISPLAY.get(k, k) for k in keys]


def _to_azerty_display_seq(steps):
    """Same as _to_azerty_display but for key_sequence (list of lists)."""
    if not steps:
        return steps
    return [_to_azerty_display(step) for step in steps]


def _lc(c1, c2, t):
    """Linearly interpolate between two RGB colors."""
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def _lf(k, dt):
    """Frame-rate independent lerp factor. k is the per-frame factor at 60 fps."""
    return 1.0 - (1.0 - k) ** (dt * 60.0)


# Certification display order
CERT_ORDER = ['101', '110', '130', '201', '210M', '210P', '205D', '210D']

# Certifications not yet playable
COMING_SOON = {'210P', '205D', '210D'}

# Difficulty levels
DIFFICULTY_LABELS = {
    1: ('Facile', ACCENT_GREEN),
    2: ('Intermediaire', ACCENT_ORANGE),
    3: ('Difficile', ACCENT_RED),
}
