import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.database.db_manager import DBManager


class DBManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = DBManager(os.path.join(self._tmp.name, "test.db"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_profiles_are_seeded(self):
        profiles = self.db.get_all_profiles()
        self.assertEqual([profile[0] for profile in profiles], [1, 2, 3, 4, 5])
        self.assertEqual([profile[1] for profile in profiles], [f"Profile {i}" for i in range(1, 6)])

    def test_saving_an_existing_action_keeps_the_row_id(self):
        self.db.save_mapping(1, "mouth_open", "space")
        mapping_id, _, key, threshold = self.db.get_mappings(1)[0]
        self.assertEqual((key, threshold), ("space", 0.05))

        self.db.save_mapping(1, "mouth_open", "enter")
        mappings = self.db.get_mappings(1)
        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0][0], mapping_id)
        self.assertEqual(mappings[0][2], "enter")

    def test_threshold_is_preserved_when_omitted(self):
        self.db.save_mapping(1, "mouth_open", "space", threshold=0.4)
        self.db.save_mapping(1, "mouth_open", "enter")

        mapping = self.db.get_mappings(1)[0]
        self.assertEqual(mapping[2], "enter")
        self.assertEqual(mapping[3], 0.4)

    def test_threshold_can_be_overridden(self):
        self.db.save_mapping(1, "mouth_open", "space", threshold=0.4)
        self.db.save_mapping(1, "mouth_open", "space", threshold=0.9)
        self.assertEqual(self.db.get_mappings(1)[0][3], 0.9)

    def test_new_action_gets_default_threshold(self):
        self.db.save_mapping(1, "smile", "s")
        self.assertEqual(self.db.get_mappings(1)[0][3], 0.05)

    def test_mappings_are_scoped_per_profile(self):
        self.db.save_mapping(1, "mouth_open", "space")
        self.db.save_mapping(2, "mouth_open", "enter")
        self.assertEqual(self.db.get_mappings(1)[0][2], "space")
        self.assertEqual(self.db.get_mappings(2)[0][2], "enter")

    def test_update_and_delete_mapping(self):
        self.db.save_mapping(1, "mouth_open", "space")
        mapping_id = self.db.get_mappings(1)[0][0]

        self.db.update_mapping(mapping_id, "enter", 0.3)
        mapping = self.db.get_mappings(1)[0]
        self.assertEqual((mapping[2], mapping[3]), ("enter", 0.3))

        self.db.delete_mapping(mapping_id)
        self.assertEqual(self.db.get_mappings(1), [])

    def test_sensitivity_is_persisted(self):
        self.db.update_profile_sensitivity(2, 2.5)
        profiles = {profile[0]: profile for profile in self.db.get_all_profiles()}
        self.assertEqual(profiles[2][2], 2.5)

    def test_profile_name_round_trip(self):
        self.assertIsNone(self.db.get_profile_name(1))
        self.db.update_profile_name(1, "Sonic Mania")
        self.assertEqual(self.db.get_profile_name(1), "Sonic Mania")

    def test_legacy_profile_name_format_is_unwrapped(self):
        self.db.update_profile_name(3, "Προφίλ 3 (Celeste)")
        self.assertEqual(self.db.get_profile_name(3), "Celeste")

    def test_settings_round_trip(self):
        self.assertEqual(self.db.get_last_profile(), 1)
        self.db.set_last_profile(4)
        self.assertEqual(self.db.get_last_profile(), 4)
        self.assertEqual(self.db.get_setting("missing", "fallback"), "fallback")

    def test_new_mapping_can_use_a_per_gesture_default(self):
        self.db.save_mapping(1, "smile", "s", default_threshold=0.105)
        self.assertEqual(self.db.get_mappings(1)[0][3], 0.105)

        self.db.save_mapping(1, "smile", "a")
        self.assertEqual(self.db.get_mappings(1)[0][3], 0.105)

    def test_legacy_thresholds_are_migrated_once(self):
        defaults = {"mouth_open": 0.04, "smile": 0.105}
        self.db.save_mapping(1, "mouth_open", "space", threshold=0.05)
        self.db.save_mapping(1, "smile", "s", threshold=0.05)
        self.db.save_mapping(2, "jaw_left", "a", threshold=0.2)

        migrated = self.db.migrate_legacy_thresholds(defaults)
        self.assertEqual(migrated, 2)

        profile_1 = {row[1]: row[3] for row in self.db.get_mappings(1)}
        profile_2 = {row[1]: row[3] for row in self.db.get_mappings(2)}
        self.assertEqual(profile_1, {"mouth_open": 0.04, "smile": 0.105})
        self.assertEqual(profile_2, {"jaw_left": 0.2})

        # Το flag κρατά τη μεταφορά μία φορά.
        self.db.save_mapping(2, "mouth_open", "space", threshold=0.05)
        self.assertEqual(self.db.migrate_legacy_thresholds(defaults), 0)
        profile_2 = {row[1]: row[3] for row in self.db.get_mappings(2)}
        self.assertEqual(profile_2["mouth_open"], 0.05)

    def test_legacy_threshold_migration_ignores_unknown_actions(self):
        self.db.save_mapping(1, "teleport", "t", threshold=0.05)
        migrated = self.db.migrate_legacy_thresholds({"mouth_open": 0.04})
        self.assertEqual(migrated, 0)
        self.assertEqual(self.db.get_mappings(1)[0][3], 0.05)


if __name__ == "__main__":
    unittest.main()
