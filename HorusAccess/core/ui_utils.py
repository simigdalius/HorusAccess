"""Small OS-aware helpers for building the CustomTkinter interface.

The UI was originally hardcoded to "Segoe UI", which only ships with Windows.
On Linux and macOS Tk silently substitutes a fallback font, so the labels end up
with a different (usually wider) metric and the Greek text overflows. This module
picks the first family that actually exists on the running system.
"""

import sys

_PREFERRED_FAMILIES = {
    "win32": ["Segoe UI", "Tahoma", "Arial"],
    "darwin": ["SF Pro Display", "Helvetica Neue", "Helvetica", "Arial"],
    "linux": ["Ubuntu", "Cantarell", "DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial"],
}

_FALLBACK_FAMILY = "Arial"

_cache = {}


def available_font_families():
    """Returns the font families the running Tk build can render."""
    try:
        import tkinter
        import tkinter.font as tkfont

        root = getattr(tkinter, "_default_root", None)
        if root is None:
            return set()
        return set(tkfont.families(root))
    except Exception:
        return set()


def default_font_family():
    """Best UI font family for the current OS. Requires a live Tk root."""
    cached = _cache.get(sys.platform)
    if cached:
        return cached

    available = available_font_families()
    candidates = _PREFERRED_FAMILIES.get(sys.platform, [_FALLBACK_FAMILY])

    family = None
    for candidate in candidates:
        if not available or candidate in available:
            family = candidate
            break

    if family is None:
        family = sorted(available)[0] if available else _FALLBACK_FAMILY

    _cache[sys.platform] = family
    return family