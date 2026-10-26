"""Horus AI prompt construction and mapping rules.

This module is deliberately free of GUI imports so the mapping policy can be
unit-tested and reused without a display. The caller (the game selector window)
only has to run the request and show the result.
"""

import json

from .gestures import GESTURES
from .keys import canonical_key

# Single source of truth for the gestures advertised to the LLM.
AVAILABLE_MOTIONS = list(GESTURES)

# Titles used by the prompt/fallback to recognise click-free 2D platformers.
# Everything else is treated as a mouse-driven PC game.
_PLATFORMER_TITLE_HINTS = (
    "sonic", "mario", "celeste", "hollow knight", "limbo", "cuphead",
)

# Preference order for the motion that gets the automatic left-click binding
# when the LLM omits one for a mouse-driven game.
_LEFT_CLICK_FALLBACK_ORDER = (
    "head_down", "smile", "eyebrows_up", "left_eye_blink", "right_eye_blink",
    "nose_scrunch", "cheek_puff", "jaw_left", "jaw_right", "head_roll",
    "lips_pucker", "eyebrows_frown", "mouth_open", "head_up", "head_left",
    "head_right",
)

_PLATFORMER_ALLOWED_KEYS = [
    "w", "a", "s", "d", "space", "left", "right", "up", "down",
]
_GENERIC_ALLOWED_KEYS = [
    "w", "a", "s", "d", "space", "left_click", "right_click", "enter",
]


def is_2d_platformer(title):
    """Whether ``title`` names a game that must not use mouse clicks."""
    title = (title or "").lower()
    return any(hint in title for hint in _PLATFORMER_TITLE_HINTS)


def validate_mappings(items, allowed_keys):
    """Κρατά μόνο τις προτάσεις του LLM που δείχνουν σε γνωστή κίνηση/πλήκτρο."""
    valid_motions = set(AVAILABLE_MOTIONS)
    valid_keys = {canonical_key(key) for key in allowed_keys}
    validated = []
    seen_motions = set()

    for item in items or []:
        if not isinstance(item, dict):
            print(f"⚠️ Παραλείπεται μη έγκυρη πρόταση Horus AI: {item!r}")
            continue

        motion = item.get("motion")
        key = canonical_key(item.get("key"))

        if not motion or not key:
            print(f"⚠️ Παράλειψη πρότασης χωρίς motion/key: {item!r}")
            continue
        if motion not in valid_motions:
            print(f"⚠️ Παράλειψη άγνωστης κίνησης: {motion}")
            continue
        if key not in valid_keys:
            print(f"⚠️ Παράλειψη μη επιτρεπτού πλήκτρου: {item.get('key')}")
            continue
        if motion in seen_motions:
            continue

        seen_motions.add(motion)
        validated.append(
            {
                "motion": motion,
                "key": key,
                "description": str(item.get("description", "")),
            }
        )

    return validated


def ensure_left_click(mappings):
    """Adds a left-click binding when a mouse-driven game has none.

    The manual editors only protect the *last* click binding, so a profile
    without one is valid (2D platformers never need it). Generic PC games do
    need a click, and the LLM sometimes follows the schema example too closely
    and omits it, so a spare motion is assigned automatically.
    """
    if any(canonical_key(item.get("key")) == "left_click" for item in mappings):
        return mappings

    used = {item.get("motion") for item in mappings}
    candidates = list(_LEFT_CLICK_FALLBACK_ORDER) + [
        motion for motion in AVAILABLE_MOTIONS
        if motion not in _LEFT_CLICK_FALLBACK_ORDER
    ]
    for motion in candidates:
        if motion in used or motion not in AVAILABLE_MOTIONS:
            continue
        print(f"🖱️ Το Horus AI δεν όρισε αριστερό κλικ· προστέθηκε {motion} -> left_click.")
        return [
            *mappings,
            {
                "motion": motion,
                "key": "left_click",
                "description": "Αριστερό κλικ",
            },
        ]
    print("⚠️ Δεν υπάρχει ελεύθερη κίνηση για αυτόματο αριστερό κλικ.")
    return mappings


def fallback_mappings(game_title):
    """Mappings used when the LLM returns nothing usable."""
    if is_2d_platformer(game_title):
        return [
            {"motion": "head_left", "key": "a", "description": "Κίνηση Αριστερά"},
            {"motion": "head_right", "key": "d", "description": "Κίνηση Δεξιά"},
            {"motion": "mouth_open", "key": "space", "description": "Άλμα (Jump)"},
            {"motion": "head_down", "key": "s", "description": "Σκύψιμο (Crouch)"},
        ]
    return [
        {"motion": "mouth_open", "key": "space", "description": "Jump / Action"},
        {"motion": "head_up", "key": "w", "description": "Move Forward"},
        {"motion": "head_left", "key": "a", "description": "Move Left"},
        {"motion": "head_right", "key": "d", "description": "Move Right"},
        {"motion": "head_down", "key": "left_click", "description": "Αριστερό κλικ"},
    ]


def build_request(game_title):
    """Returns ``(prompt, allowed_keys, fallback)`` for one Horus AI request."""
    platformer = is_2d_platformer(game_title)

    if platformer:
        context_instruction = (
            "Η εφαρμογή είναι 2D PLATFORMER GAME (π.χ. Sonic). "
            "ΑΠΑΓΟΡΕΥΟΝΤΑΙ ΑΥΣΤΗΡΑ ΤΑ MOUSE CLICKS! "
            "Χρησιμοποίησε ΜΟΝΟ keys πληκτρολογίου: w, a, s, d, space, left, right, up, down."
        )
        allowed_keys = list(_PLATFORMER_ALLOWED_KEYS)
        click_rule = "6. Do NOT use mouse clicks if the game is a 2D Platformer or Arcade game."
        schema_click = ""
    else:
        context_instruction = "Η εφαρμογή είναι GENERIC PC GAME. Χρησιμοποίησε GAMING KEYS: w, a, s, d, space, left_click."
        allowed_keys = list(_GENERIC_ALLOWED_KEYS)
        click_rule = "6. ALWAYS include exactly one motion mapped to left_click (click / attack)."
        schema_click = ',\n    {"motion": "smile", "key": "left_click", "description": "Left Click"}'

    prompt = f"""You are an AI Accessibility Assistant for HorusAccess.
Task: Create optimal face-motion and head-tracking to key mappings for the game '{game_title}'.

CRITICAL GAME CONTEXT:
{context_instruction}

STRICT RULES & CONSTRAINTS:
1. KEY ANALYSIS: Inspect '{game_title}' controls. Map ONLY keys that are ACTUALLY used by this specific game (e.g. if WASD/Space/Enter are used, restrict choices strictly to those).
2. HEAD MOVEMENTS PRIORITY: ALWAYS prioritize head motions (head_left, head_right, head_up, head_down) for character movement keys (e.g. W, A, S, D or Arrow Keys).
3. FACIAL GESTURES FOR ACTIONS: Use secondary facial gestures (mouth_open, eyebrows_up, smile, left_eye_blink, right_eye_blink) ONLY for action buttons (e.g. Jump, Spin Dash, Attack).
4. ALLOWED MOTIONS: {json.dumps(AVAILABLE_MOTIONS)}
5. ALLOWED KEYS ONLY FROM THIS LIST: {json.dumps(allowed_keys)}
{click_rule}

Respond STRICTLY with a valid JSON object matching this schema:
{{
  "mappings": [
    {{"motion": "head_left", "key": "a", "description": "Move Left"}},
    {{"motion": "head_right", "key": "d", "description": "Move Right"}},
    {{"motion": "head_up", "key": "w", "description": "Move Forward / Jump"}},
    {{"motion": "head_down", "key": "s", "description": "Crouch / Move Down"}},
    {{"motion": "mouth_open", "key": "space", "description": "Action / Spin Dash"}}{schema_click}
  ]
}}"""

    return prompt, allowed_keys, fallback_mappings(game_title)
