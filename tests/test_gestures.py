import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core.gestures import (
    GESTURES,
    HeadPoseTracker,
    canonical_motion,
    compute_facial_metrics,
    default_threshold,
    default_thresholds,
    display_name,
    head_metrics,
    head_signals,
    is_gesture_active,
)


class Landmark:
    __slots__ = ("x", "y")

    def __init__(self, x=0.5, y=0.5):
        self.x = x
        self.y = y


def make_landmarks():
    return [Landmark() for _ in range(468)]


def set_points(landmarks, points):
    for index, (x, y) in points.items():
        landmarks[index] = Landmark(x, y)


def facial_landmarks():
    landmarks = make_landmarks()
    set_points(landmarks, {
        0: (0.50, 0.48),
        1: (0.50, 0.45),
        13: (0.50, 0.50),
        14: (0.50, 0.54),
        17: (0.50, 0.50),
        50: (0.40, 0.50),
        61: (0.40, 0.50),
        105: (0.45, 0.30),
        132: (0.45, 0.60),
        145: (0.45, 0.34),
        152: (0.50, 0.60),
        159: (0.45, 0.33),
        280: (0.60, 0.50),
        291: (0.50, 0.50),
        336: (0.55, 0.30),
        361: (0.55, 0.60),
        374: (0.55, 0.34),
        386: (0.55, 0.33),
    })
    return landmarks


def head_landmarks(nose=(0.5, 0.5), left=(0.3, 0.5), right=(0.7, 0.5),
                   top=(0.5, 0.2), bottom=(0.5, 0.8)):
    landmarks = make_landmarks()
    set_points(landmarks, {
        1: nose,
        234: left,
        454: right,
        10: top,
        152: bottom,
    })
    return landmarks


class RegistryTests(unittest.TestCase):
    def test_every_ui_action_has_a_metric_and_a_default(self):
        names = {
            "mouth_open", "smile", "left_eye_blink", "right_eye_blink",
            "eyebrows_up", "eyebrows_frown", "jaw_left", "jaw_right",
            "lips_pucker", "nose_scrunch", "cheek_puff", "head_up",
            "head_down", "head_left", "head_right", "head_roll",
        }
        self.assertEqual(set(GESTURES), names)
        for name, spec in GESTURES.items():
            self.assertIn(spec.direction, ("above", "below"))
            self.assertGreater(spec.default_threshold, 0.0)
            self.assertEqual(default_threshold(name), spec.default_threshold)

    def test_legacy_kiss_is_the_pucker(self):
        self.assertEqual(canonical_motion("kiss"), "lips_pucker")
        self.assertEqual(default_threshold("kiss"), default_threshold("lips_pucker"))
        self.assertIn("kiss", default_thresholds())
        self.assertEqual(display_name("kiss"), GESTURES["lips_pucker"].label)

    def test_unknown_motion_is_not_accepted(self):
        self.assertIsNone(canonical_motion("teleport"))
        self.assertIsNone(default_threshold("teleport"))
        self.assertFalse(is_gesture_active("teleport", 1.0))

    def test_direction_of_each_gesture(self):
        self.assertTrue(is_gesture_active("mouth_open", 0.06, 0.05))
        self.assertFalse(is_gesture_active("mouth_open", 0.04, 0.05))
        self.assertTrue(is_gesture_active("left_eye_blink", 0.005, 0.012))
        self.assertFalse(is_gesture_active("left_eye_blink", 0.02, 0.012))
        self.assertTrue(is_gesture_active("head_right", 0.10, 0.06))
        self.assertFalse(is_gesture_active("head_right", -0.10, 0.06))

    def test_handles_missing_values(self):
        self.assertFalse(is_gesture_active("smile", None))
        self.assertFalse(is_gesture_active("smile", "not-a-number"))
        self.assertFalse(is_gesture_active(None, 1.0))


class FacialMetricTests(unittest.TestCase):
    def test_metric_values(self):
        metrics = compute_facial_metrics(facial_landmarks())

        self.assertAlmostEqual(metrics["mouth_open"], 0.04)
        self.assertAlmostEqual(metrics["smile"], 0.10)
        self.assertAlmostEqual(metrics["left_eye_blink"], 0.01)
        self.assertAlmostEqual(metrics["right_eye_blink"], 0.01)
        self.assertAlmostEqual(metrics["eyebrows_up"], 0.03)
        self.assertAlmostEqual(metrics["eyebrows_frown"], 0.03)
        self.assertAlmostEqual(metrics["jaw_left"], 0.05)
        self.assertAlmostEqual(metrics["jaw_right"], 0.05)
        self.assertAlmostEqual(metrics["lips_pucker"], 0.20)
        self.assertAlmostEqual(metrics["nose_scrunch"], 0.05)
        self.assertAlmostEqual(metrics["cheek_puff"], 0.20)

    def test_pucker_is_not_a_copy_of_the_smile(self):
        metrics = compute_facial_metrics(facial_landmarks())
        self.assertNotAlmostEqual(metrics["lips_pucker"], metrics["smile"])
        self.assertFalse(is_gesture_active("lips_pucker", metrics["lips_pucker"]))

        landmarks = facial_landmarks()
        set_points(landmarks, {0: (0.50, 0.47), 17: (0.50, 0.51)})
        puckered = compute_facial_metrics(landmarks)
        self.assertGreater(puckered["lips_pucker"], metrics["lips_pucker"])
        self.assertTrue(is_gesture_active("lips_pucker", puckered["lips_pucker"]))

    def test_smile_and_pucker_can_be_told_apart(self):
        landmarks = facial_landmarks()
        set_points(landmarks, {61: (0.35, 0.50), 291: (0.55, 0.50)})
        smiling = compute_facial_metrics(landmarks)
        self.assertTrue(is_gesture_active("smile", smiling["smile"]))


class HeadPoseTests(unittest.TestCase):
    def test_signals_are_relative_to_the_face_box(self):
        signals = head_signals(head_landmarks(nose=(0.6, 0.5)))
        self.assertGreater(signals["yaw"], 0.0)
        self.assertAlmostEqual(signals["pitch"], 0.0)
        self.assertAlmostEqual(signals["roll"], 0.0)

        up = head_signals(head_landmarks(nose=(0.5, 0.2)))
        self.assertLess(up["pitch"], 0.0)

    def test_metrics_are_zero_until_calibration_finishes(self):
        tracker = HeadPoseTracker(calibration_frames=2)
        self.assertFalse(tracker.is_calibrated)
        metrics = tracker.update(head_landmarks())
        self.assertEqual(set(metrics), set(tracker.HEAD_METRICS))
        self.assertEqual(set(metrics.values()), {0.0})
        self.assertFalse(tracker.is_calibrated)

        tracker.update(head_landmarks())
        self.assertTrue(tracker.is_calibrated)

    def test_deviation_from_neutral_drives_the_four_head_directions(self):
        tracker = HeadPoseTracker(calibration_frames=1)
        tracker.update(head_landmarks())

        right = tracker.update(head_landmarks(nose=(0.6, 0.5)))
        self.assertGreater(right["head_right"], right["head_left"])
        self.assertTrue(is_gesture_active("head_right", right["head_right"]))
        self.assertFalse(is_gesture_active("head_left", right["head_left"]))

        left = tracker.update(head_landmarks(nose=(0.4, 0.5)))
        self.assertTrue(is_gesture_active("head_left", left["head_left"]))
        self.assertFalse(is_gesture_active("head_right", left["head_right"]))

        up = tracker.update(head_landmarks(nose=(0.5, 0.2)))
        self.assertTrue(is_gesture_active("head_up", up["head_up"]))
        self.assertFalse(is_gesture_active("head_down", up["head_down"]))

        down = tracker.update(head_landmarks(nose=(0.5, 0.8)))
        self.assertTrue(is_gesture_active("head_down", down["head_down"]))
        self.assertFalse(is_gesture_active("head_up", down["head_up"]))

    def test_roll_uses_the_absolute_tilt(self):
        tracker = HeadPoseTracker(calibration_frames=1)
        tracker.update(head_landmarks())

        tilted = tracker.update(head_landmarks(left=(0.3, 0.3), right=(0.7, 0.6)))
        self.assertGreater(tilted["head_roll"], 0.0)
        self.assertTrue(is_gesture_active("head_roll", tilted["head_roll"]))

    def test_reset_starts_a_new_capture(self):
        tracker = HeadPoseTracker(calibration_frames=1)
        tracker.update(head_landmarks())
        self.assertTrue(tracker.is_calibrated)

        tracker.reset()
        self.assertFalse(tracker.is_calibrated)
        self.assertEqual(tracker.sample_count, 0)
        metrics = tracker.update(head_landmarks(nose=(0.6, 0.5)))
        self.assertEqual(set(metrics.values()), {0.0})

    def test_head_metrics_helper(self):
        neutral = {"yaw": 0.1, "pitch": -0.2, "roll": 0.05}
        signals = {"yaw": 0.2, "pitch": -0.1, "roll": 0.15}
        metrics = head_metrics(signals, neutral)
        self.assertAlmostEqual(metrics["head_right"], 0.1)
        self.assertAlmostEqual(metrics["head_left"], -0.1)
        self.assertAlmostEqual(metrics["head_up"], -0.1)
        self.assertAlmostEqual(metrics["head_down"], 0.1)
        self.assertAlmostEqual(metrics["head_roll"], 0.1)


if __name__ == "__main__":
    unittest.main()
