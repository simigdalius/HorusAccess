"""Canonical key names and per-backend translations.

The application stores logical key names (the vocabulary that
``pydirectinput``/``pyautogui`` accept, plus the mouse pseudo-keys
``left_click``/``right_click``/``middle_click``). Backends disagree about the
spelling of special keys, so every synthetic input event is translated here
before it reaches a driver.

This module deliberately imports nothing from the backends: it has to stay
importable in a headless environment (no X display and no optional
dependencies), which is what makes the tables unit-testable.
"""

# Logical spelling -> canonical spelling. Aliases are accepted from the UI, the
# LLM and older database rows.
_CANONICAL_ALIASES = {
    "return": "enter",
    "escape": "esc",
    "page_up": "pageup",
    "page up": "pageup",
    "page_down": "pagedown",
    "page down": "pagedown",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "print_screen": "printscreen",
    "print screen": "printscreen",
    "prntscrn": "printscreen",
    "prtsc": "printscreen",
    "prtscr": "printscreen",
    "num_lock": "numlock",
    "num lock": "numlock",
    "scroll_lock": "scrolllock",
    "scroll lock": "scrolllock",
    "caps_lock": "capslock",
    "caps lock": "capslock",
    "del": "delete",
    "ins": "insert",
    "shift_l": "shiftleft",
    "shift_r": "shiftright",
    "ctrl_l": "ctrlleft",
    "ctrl_r": "ctrlright",
    "alt_l": "altleft",
    "alt_r": "altright",
    "control": "ctrl",
    "lctrl": "ctrlleft",
    "rctrl": "ctrlright",
    "lshift": "shiftleft",
    "rshift": "shiftright",
    "lalt": "altleft",
    "ralt": "altright",
    "super": "win",
    "meta": "win",
}

# The Horus AI may answer with a human-readable mouse action instead of the
# internal pseudo-key, so the variants are canonicalised before comparison.
_MOUSE_ALIASES = {
    "leftclick": "left_click",
    "left click": "left_click",
    "l. click": "left_click",
    "l click": "left_click",
    "lclick": "left_click",
    "rightclick": "right_click",
    "right click": "right_click",
    "r. click": "right_click",
    "r click": "right_click",
    "rclick": "right_click",
    "middleclick": "middle_click",
    "middle click": "middle_click",
    "m. click": "middle_click",
    "m click": "middle_click",
    "mclick": "middle_click",
}

# Canonical key -> name expected by each backend. ``pydirectinput`` is the
# reference vocabulary, so its table only rewrites the Windows modifier names.
KEY_ALIASES = {
    "pydirectinput": {
        "cmd": "win",
        "cmd_r": "winright",
    },
    "pynput": {
        "shiftleft": "shift",
        "ctrlleft": "ctrl",
        "altleft": "alt",
        "shiftright": "shift_r",
        "ctrlright": "ctrl_r",
        "altright": "alt_r",
        "cmd": "cmd",
        "win": "cmd",
        "winright": "cmd_r",
        "printscreen": "print_screen",
        "numlock": "num_lock",
        "scrolllock": "scroll_lock",
        "capslock": "caps_lock",
        "pageup": "page_up",
        "pagedown": "page_down",
    },
    "pyautogui": {
        "cmd": "win",
        "cmd_r": "winright",
        "alt": "altleft",
    },
    # pyautogui uses completely different modifier names on macOS.
    "pyautogui-darwin": {
        "cmd": "command",
        "win": "command",
        "cmd_r": "command",
        "winright": "command",
        "alt": "option",
        "altleft": "optionleft",
        "altright": "optionright",
        "shiftleft": "shift",
        "ctrlleft": "ctrl",
    },
}

# Mouse pseudo-keys. Profiles store these alongside real keyboard keys, so they
# have to be routed to the mouse buttons instead of the keyboard.
BUTTON_ALIASES = {
    "left_click": "left",
    "right_click": "right",
    "middle_click": "middle",
}


def canonical_key(key):
    """Returns the canonical spelling of a logical key, or ``None``."""
    if key is None:
        return None

    # Collapse the whitespace the LLM sometimes inserts ("LEFT  CLICK").
    name = " ".join(str(key).strip().lower().split())
    if not name:
        return None

    if name in _MOUSE_ALIASES:
        return _MOUSE_ALIASES[name]

    return _CANONICAL_ALIASES.get(name, name)


def normalize_key(key, backend):
    """Returns the backend-specific name for a logical HorusAccess key."""
    name = canonical_key(key)
    if not name:
        return None
    return KEY_ALIASES.get(backend, {}).get(name, name)
