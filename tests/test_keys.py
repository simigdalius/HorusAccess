import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core.keys import BUTTON_ALIASES, canonical_key, normalize_key


class CanonicalKeyTests(unittest.TestCase):
    def test_aliases_collapse_to_one_spelling(self):
        self.assertEqual(canonical_key("Return"), "enter")
        self.assertEqual(canonical_key("Escape"), "esc")
        self.assertEqual(canonical_key("Page_Up"), "pageup")
        self.assertEqual(canonical_key("PAGE_DOWN"), "pagedown")
        self.assertEqual(canonical_key("Print Screen"), "printscreen")
        self.assertEqual(canonical_key("Shift_L"), "shiftleft")
        self.assertEqual(canonical_key("ctrl_r"), "ctrlright")

    def test_mouse_variants_are_canonicalised(self):
        for key in ("left_click", "LEFT_CLICK", "L. Click", "left click"):
            self.assertEqual(canonical_key(key), "left_click")
        self.assertEqual(canonical_key("R. CLICK"), "right_click")
        self.assertEqual(canonical_key("Middle Click"), "middle_click")

    def test_empty_values(self):
        self.assertIsNone(canonical_key(None))
        self.assertIsNone(canonical_key("   "))

    def test_unknown_key_is_preserved_lowercased(self):
        self.assertEqual(canonical_key("Whatever"), "whatever")


class NormalizeKeyTests(unittest.TestCase):
    def test_pynput_spellings(self):
        self.assertEqual(normalize_key("page_up", "pynput"), "page_up")
        self.assertEqual(normalize_key("page_down", "pynput"), "page_down")
        self.assertEqual(normalize_key("shift_l", "pynput"), "shift")
        self.assertEqual(normalize_key("ctrl_r", "pynput"), "ctrl_r")
        self.assertEqual(normalize_key("f5", "pynput"), "f5")
        self.assertEqual(normalize_key("left_click", "pynput"), "left_click")

    def test_pyautogui_spellings(self):
        self.assertEqual(normalize_key("page_up", "pyautogui"), "pageup")
        self.assertEqual(normalize_key("page_down", "pyautogui"), "pagedown")
        self.assertEqual(normalize_key("print_screen", "pyautogui"), "printscreen")
        self.assertEqual(normalize_key("shift_l", "pyautogui"), "shiftleft")

    def test_pyautogui_darwin_spellings(self):
        self.assertEqual(normalize_key("cmd", "pyautogui-darwin"), "command")
        self.assertEqual(normalize_key("alt", "pyautogui-darwin"), "option")
        self.assertEqual(normalize_key("enter", "pyautogui-darwin"), "enter")

    def test_pydirectinput_keeps_reference_names(self):
        self.assertEqual(normalize_key("enter", "pydirectinput"), "enter")
        self.assertEqual(normalize_key("page_up", "pydirectinput"), "pageup")
        self.assertEqual(normalize_key("cmd", "pydirectinput"), "win")

    def test_none_and_unknown(self):
        self.assertIsNone(normalize_key(None, "pynput"))
        self.assertEqual(normalize_key("whatever", "pyautogui"), "whatever")
        self.assertEqual(normalize_key("whatever", "does-not-exist"), "whatever")

    def test_button_alias_table(self):
        self.assertEqual(BUTTON_ALIASES["left_click"], "left")
        self.assertEqual(BUTTON_ALIASES["right_click"], "right")
        self.assertEqual(BUTTON_ALIASES["middle_click"], "middle")


if __name__ == "__main__":
    unittest.main()
