import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core.ai_mappings import (
    AVAILABLE_MOTIONS,
    build_request,
    ensure_left_click,
    fallback_mappings,
    is_2d_platformer,
    validate_mappings,
)


class PlatformerDetectionTests(unittest.TestCase):
    def test_known_platformer_titles_are_recognised(self):
        for title in ("Sonic Mania", "Super MARIO", "Celeste", "Hollow Knight", "Cuphead"):
            with self.subTest(title=title):
                self.assertTrue(is_2d_platformer(title))

    def test_other_games_are_mouse_driven(self):
        for title in ("Elden Ring", "Minecraft", "", None):
            with self.subTest(title=title):
                self.assertFalse(is_2d_platformer(title))


class BuildRequestTests(unittest.TestCase):
    def test_platformer_request_forbids_clicks(self):
        prompt, allowed_keys, fallback = build_request("Sonic Mania")

        self.assertNotIn("left_click", allowed_keys)
        self.assertIn("2D PLATFORMER", prompt)
        self.assertIn("Do NOT use mouse clicks", prompt)
        self.assertFalse(any(item["key"] == "left_click" for item in fallback))

    def test_generic_request_requires_exactly_one_click(self):
        prompt, allowed_keys, fallback = build_request("Elden Ring")

        self.assertIn("left_click", allowed_keys)
        self.assertIn("ALWAYS include exactly one motion mapped to left_click", prompt)
        self.assertIn('"motion": "smile", "key": "left_click"', prompt)
        self.assertEqual(
            sum(item["key"] == "left_click" for item in fallback), 1
        )

    def test_fallback_matches_the_game_category(self):
        self.assertFalse(
            any(item["key"] == "left_click" for item in fallback_mappings("Celeste"))
        )
        self.assertTrue(
            any(item["key"] == "left_click" for item in fallback_mappings("Doom"))
        )


class ValidateMappingsTests(unittest.TestCase):
    def test_keeps_only_known_motions_and_allowed_keys(self):
        items = [
            {"motion": "head_left", "key": "A", "description": "left"},
            {"motion": "mouth_open", "key": "space", "description": ""},
            {"motion": "not_a_gesture", "key": "a", "description": ""},
            {"motion": "smile", "key": "f13", "description": ""},
            {"motion": "head_right"},
            "not a mapping",
        ]

        validated = validate_mappings(items, ["a", "space"])

        self.assertEqual(
            [(item["motion"], item["key"]) for item in validated],
            [("head_left", "a"), ("mouth_open", "space")],
        )

    def test_accepts_key_aliases_and_keeps_the_first_motion(self):
        items = [
            {"motion": "smile", "key": "L. Click", "description": "first"},
            {"motion": "smile", "key": "right_click", "description": "duplicate"},
        ]

        validated = validate_mappings(items, ["left_click"])

        self.assertEqual(validated[0]["key"], "left_click")
        self.assertEqual(validated[0]["description"], "first")
        self.assertEqual(len(validated), 1)


class EnsureLeftClickTests(unittest.TestCase):
    def test_adds_the_first_free_motion(self):
        mappings = [
            {"motion": "head_up", "key": "w"},
            {"motion": "head_down", "key": "s"},
        ]

        result = ensure_left_click(mappings)

        self.assertEqual(len(result), len(mappings) + 1)
        self.assertEqual(result[-1]["motion"], "smile")
        self.assertEqual(result[-1]["key"], "left_click")

    def test_keeps_an_existing_click_binding(self):
        mappings = [{"motion": "smile", "key": "L. Click"}]
        self.assertIs(ensure_left_click(mappings), mappings)

    def test_leaves_an_exhausted_click_free_mapping_untouched(self):
        mappings = [
            {"motion": motion, "key": "a"} for motion in AVAILABLE_MOTIONS
        ]

        self.assertIs(ensure_left_click(mappings), mappings)
        self.assertFalse(any(item["key"] == "left_click" for item in mappings))


if __name__ == "__main__":
    unittest.main()
