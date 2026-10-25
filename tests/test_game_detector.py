import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core import game_detector


class ExecTokenTests(unittest.TestCase):
    def test_quoted_path_with_spaces(self):
        self.assertEqual(
            game_detector._first_exec_token('"/opt/My Game/run.sh" %F'),
            "/opt/My Game/run.sh",
        )

    def test_env_prefix_is_removed(self):
        self.assertEqual(
            game_detector._first_exec_token(
                'env WINEPREFIX="/tmp/wine prefix" "/opt/My Game/run.sh" %U'
            ),
            "/opt/My Game/run.sh",
        )

    def test_field_codes_are_dropped(self):
        self.assertEqual(game_detector._first_exec_token("%f"), "")
        self.assertEqual(
            game_detector._first_exec_token('"/opt/Game/run.sh" %f %U'),
            "/opt/Game/run.sh",
        )

    def test_empty_command(self):
        self.assertEqual(game_detector._first_exec_token(""), "")

    def test_unbalanced_quotes_do_not_raise(self):
        self.assertEqual(game_detector._first_exec_token('"/opt/Game/run.sh'), "/opt/Game/run.sh")


class LaunchableCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base_dir = self._tmp.name

        self.script = os.path.join(self.base_dir, "run.sh")
        with open(self.script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        os.chmod(self.script, 0o755)

        self.native = os.path.join(self.base_dir, "native-game")
        with open(self.native, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        os.chmod(self.native, 0o755)

        self.not_executable = os.path.join(self.base_dir, "notes.txt")
        with open(self.not_executable, "w", encoding="utf-8") as handle:
            handle.write("hello\n")
        os.chmod(self.not_executable, 0o644)

    def tearDown(self):
        self._tmp.cleanup()

    def test_relative_script_next_to_desktop_entry(self):
        self.assertTrue(game_detector._is_launchable_command("./run.sh", self.base_dir))
        self.assertTrue(game_detector._is_launchable_command("run.sh", self.base_dir))

    def test_missing_relative_file_is_rejected(self):
        self.assertFalse(game_detector._is_launchable_command("./missing.sh", self.base_dir))

    def test_missing_absolute_executable_is_rejected(self):
        missing = os.path.join(self.base_dir, "missing.exe")
        self.assertFalse(game_detector._is_launchable_command(missing))

    def test_existing_suffixed_file_is_accepted(self):
        self.assertTrue(game_detector._is_launchable_command(self.script))

    def test_existing_native_executable_is_accepted(self):
        self.assertTrue(game_detector._is_launchable_command(self.native))

    def test_existing_non_executable_without_suffix_is_rejected(self):
        self.assertFalse(game_detector._is_launchable_command(self.not_executable))

    def test_bare_command_is_resolved_through_path(self):
        self.assertTrue(game_detector._is_launchable_command("sh"))


class ValidGameTests(unittest.TestCase):
    def test_manifest_titles_use_lenient_filter(self):
        self.assertTrue(game_detector.is_valid_game("Code Vein", strict=False))
        self.assertTrue(game_detector.is_valid_game("Sonic Mania", strict=False))

    def test_desktop_titles_use_strict_filter(self):
        self.assertFalse(game_detector.is_valid_game("Code Vein"))
        self.assertFalse(game_detector.is_valid_game("Setup Wizard"))

    def test_tooling_is_always_rejected(self):
        self.assertFalse(game_detector.is_valid_game("Visual Studio Code", strict=False))
        self.assertFalse(game_detector.is_valid_game("Google Chrome", strict=False))
        self.assertFalse(game_detector.is_valid_game("Steam", strict=False))

    def test_launcher_names_are_rejected(self):
        self.assertFalse(game_detector.is_valid_game("Heroic Games Launcher", strict=False))


class GogManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, content):
        path = os.path.join(self._tmp.name, "goggame-1.info")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_top_level_name(self):
        path = self._write(json.dumps({"name": "Top Level Game"}))
        self.assertEqual(game_detector._parse_goggame(path), "Top Level Game")

    def test_nested_name_falls_back_to_regex(self):
        path = self._write(json.dumps({"gameId": "1", "info": {"name": "Nested Game"}}))
        self.assertEqual(game_detector._parse_goggame(path), "Nested Game")

    def test_no_name_returns_none(self):
        path = self._write(json.dumps({"gameId": "1"}))
        self.assertIsNone(game_detector._parse_goggame(path))


class LinuxDesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.desktop_dir = self._tmp.name

        game_dir = os.path.join(self.desktop_dir, "Game Dir")
        os.makedirs(game_dir)
        script = os.path.join(game_dir, "run game.sh")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write("#!/bin/sh\n")
        os.chmod(script, 0o755)

        entry = os.path.join(self.desktop_dir, "game.desktop")
        with open(entry, "w", encoding="utf-8") as handle:
            handle.write(
                "[Desktop Entry]\n"
                "Name=My Quoted Game\n"
                f'Exec="{script}" %F\n'
            )

    def tearDown(self):
        self._tmp.cleanup()

    def test_quoted_exec_path_is_detected(self):
        games = game_detector._detect_linux_desktop_entries(self.desktop_dir)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["title"], "My Quoted Game")
        self.assertTrue(games[0]["path"].endswith("run game.sh"))


class DetectAllTests(unittest.TestCase):
    def test_a_failing_detector_does_not_hide_the_others(self):
        epic_game = {"title": "Epic Game", "platform": "Epic Games", "image_url": None}
        steam_game = {"title": "Steam Game", "platform": "Steam", "image_url": None}

        def boom(_found_names):
            raise OSError("permission denied")

        with mock.patch.object(game_detector, "_detect_epic", return_value=[epic_game]), \
             mock.patch.object(game_detector, "_detect_steam", return_value=[steam_game]), \
             mock.patch.object(game_detector, "_detect_gog", side_effect=boom), \
             mock.patch.object(game_detector, "_detect_desktop_entries", return_value=[]):
            games = game_detector.detect_installed_games()

        self.assertEqual([game["title"] for game in games], ["Epic Game", "Steam Game"])

    def test_result_is_sorted_case_insensitively(self):
        games = [
            {"title": "zeta", "platform": "Steam", "image_url": None},
            {"title": "Alpha", "platform": "Epic Games", "image_url": None},
            {"title": "beta", "platform": "GOG", "image_url": None},
        ]

        def return_games(subset):
            return lambda _found_names: list(subset)

        with mock.patch.object(game_detector, "_detect_epic", side_effect=return_games([games[0]])), \
             mock.patch.object(game_detector, "_detect_steam", side_effect=return_games([games[1]])), \
             mock.patch.object(game_detector, "_detect_gog", side_effect=return_games([games[2]])), \
             mock.patch.object(game_detector, "_detect_desktop_entries", return_value=[]):
            result = game_detector.detect_installed_games()

        self.assertEqual([game["title"] for game in result], ["Alpha", "beta", "zeta"])

    def test_safe_detect_returns_empty_list_on_failure(self):
        def boom(_found_names):
            raise RuntimeError("broken")

        self.assertEqual(game_detector._safe_detect("test", boom, set()), [])


if __name__ == "__main__":
    unittest.main()
