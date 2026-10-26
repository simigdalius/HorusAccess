import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# input_backend imports pyautogui/pynput at module level. Keep this test
# headless and independent of the host's display setup.
_SAVED_MODULES = {
    name: sys.modules.get(name) for name in ("pyautogui", "pynput")
}
_SAVED_ENV = {
    name: os.environ.pop(name, None) for name in ("WAYLAND_DISPLAY", "SWAYSOCK")
}
_fake_pyautogui = types.ModuleType("pyautogui")
_fake_pyautogui.FAILSAFE = True
_fake_pyautogui.position = lambda: (0, 0)
_fake_pyautogui.size = lambda: (1920, 1080)
sys.modules["pyautogui"] = _fake_pyautogui
sys.modules["pynput"] = None

try:
    from HorusAccess.core import input_backend as ib
finally:
    for _name, _value in _SAVED_ENV.items():
        if _value is not None:
            os.environ[_name] = _value
    for _name, _value in _SAVED_MODULES.items():
        if _value is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _value


class FakeMetrics:
    def __init__(self, position=(0, 0), size=(1920, 1080)):
        self.current_position = position
        self.current_size = size

    def position(self):
        return self.current_position

    def size(self):
        return self.current_size


class FakeDriver:
    def __init__(self):
        self.moves = []

    def moveTo(self, x, y):
        self.moves.append((x, y))


class PointerPollingTests(unittest.TestCase):
    def setUp(self):
        ib._sway = None
        ib._sway_error_logged = False
        ib._linux_driver = "pyautogui"
        ib._metrics = FakeMetrics()
        ib._driver = FakeDriver()
        ib._mouse_ctrl = None
        ib._mouse_activity = 0
        ib._mouse_observed = None
        ib._mouse_last_seen = None
        ib._RECENT_WARPS.clear()

    def test_pointer_position_is_available_without_sway(self):
        ib._metrics = FakeMetrics(position=(100, 50), size=(1000, 800))
        self.assertEqual(ib._pointer_app_position(), (100, 50))

    def test_pointer_position_is_clamped_to_the_screen(self):
        ib._metrics = FakeMetrics(position=(1200, 900), size=(1000, 800))
        self.assertEqual(ib._pointer_app_position(), (999, 799))

    def test_first_poll_only_seeds_the_previous_position(self):
        ib._metrics = FakeMetrics(position=(100, 100))
        ib._poll_pointer()
        self.assertEqual(ib.mouse_activity_count(), 0)
        self.assertEqual(ib._mouse_last_seen, (100, 100))

    def test_poll_counts_a_physical_movement(self):
        ib._metrics = FakeMetrics(position=(100, 100))
        ib._poll_pointer()
        ib._metrics.current_position = (160, 150)
        ib._poll_pointer()
        self.assertEqual(ib.mouse_activity_count(), 1)
        self.assertEqual(ib._mouse_observed, (160, 150))

    def test_poll_ignores_a_position_we_just_warped_to(self):
        ib._metrics = FakeMetrics(position=(100, 100))
        ib._poll_pointer()
        ib._remember_warp(150, 150)
        ib._metrics.current_position = (150, 150)
        ib._poll_pointer()
        self.assertEqual(ib.mouse_activity_count(), 0)

    def test_mouse_move_polls_and_records_its_own_warp(self):
        ib._metrics = FakeMetrics(position=(100, 100))
        ib._poll_pointer()
        ib._metrics.current_position = (160, 150)
        ib.mouse_move(300, 200)
        self.assertEqual(ib.mouse_activity_count(), 1)
        self.assertEqual(ib._driver.moves, [(300, 200)])
        self.assertEqual(ib._RECENT_WARPS[-1], (300, 200))

    def test_mouse_position_returns_the_native_position_without_sway(self):
        ib._metrics = FakeMetrics(position=(5, 6))
        self.assertEqual(ib.mouse_position(), (5, 6))


if __name__ == "__main__":
    unittest.main()
