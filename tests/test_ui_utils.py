import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core.ui_utils import snap_to_nearest


class SnapToNearestTests(unittest.TestCase):
    TARGETS = [(100.0, 100.0), (400.0, 300.0)]

    def test_snaps_to_a_nearby_target(self):
        self.assertEqual(snap_to_nearest(120, 80, self.TARGETS, 45), (100, 100))

    def test_keeps_the_point_when_no_target_is_close(self):
        self.assertEqual(snap_to_nearest(250, 200, self.TARGETS, 45), (250, 200))

    def test_chooses_the_nearest_target(self):
        targets = [(60.0, 100.0), (100.0, 100.0)]
        self.assertEqual(snap_to_nearest(70, 105, targets, 45), (60, 100))

    def test_does_not_snap_past_the_threshold(self):
        # Exactly at the threshold: must stay put, as the old behaviour did.
        self.assertEqual(snap_to_nearest(145, 100, [(100.0, 100.0)], 45), (145, 100))

    def test_works_without_targets(self):
        self.assertEqual(snap_to_nearest(10, 20, [], 45), (10, 20))

    def test_zero_threshold_disables_snapping(self):
        self.assertEqual(snap_to_nearest(100, 100, self.TARGETS, 0), (100, 100))

    def test_truncates_fractional_centres(self):
        self.assertEqual(snap_to_nearest(101, 99, [(100.6, 99.4)], 45), (100, 99))


if __name__ == "__main__":
    unittest.main()
