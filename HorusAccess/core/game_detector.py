"""Cross-platform detection of installed games.

Windows uses the original sources (Epic launcher manifests, Steam ``appmanifest``
ACF files, the ``GOG.com\\Games`` registry hive and Desktop ``.lnk`` shortcuts).
On Linux the equivalent sources are used: Steam/Proton libraries (native,
Flatpak and Snap paths), Heroic/Epic manifests, GOG ``goggame-*.info`` manifests
and XDG ``.desktop`` entries. On macOS: Steam libraries, Epic manifests,
GOG ``goggame-*.info`` manifests and ``.app`` bundles.
"""

import glob
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Λίστα αποκλεισμού για συστήματα/εργαλεία που μπορεί να ξεφύγουν από launchers
IGNORED_KEYWORDS = [
    "opera", "browser", "code", "visual studio", "wps", "office", "word", "excel",
    "powerpoint", "administration", "tools", "librewolf", "chrome", "firefox",
    "edge", "discord", "spotify", "vlc", "uninstall", "setup", "help", "python",
    "git", "node", "cmd", "powershell", "control panel", "settings", "redistributable",
    "steamworks", "proton", "prerequisites", "epic online services",
]

# Επεκτάσεις που δείχνουν ότι ένα shortcut/launcher τρέχει πραγματικό πρόγραμμα
LAUNCHABLE_SUFFIXES = (
    ".exe", ".bat", ".cmd", ".com", ".sh", ".app", ".appimage", ".bin", ".x86", ".x86_64",
)

# Οι ίδιοι οι client προγράμματα των launchers δεν πρέπει να εμφανίζονται ως παιχνίδια.
# Συγκρίνονται με ολόκληρο το όνομα (χωρίς επέκταση), όχι ως substring, ώστε να μην
# φιλτραριστούν νόμιμα παιχνίδια όπως το "SteamWorld".
LAUNCHER_NAMES = {
    "steam", "steam library", "epic games launcher", "epicgameslauncher",
    "gog galaxy", "gog games", "gog", "heroic", "heroic games launcher",
    "lutris", "battle.net", "battlenet", "ea app", "ea desktop", "origin",
    "ubisoft connect", "riot client", "shortcuts", "launcher",
}


def is_valid_game(name):
    """Αποκλείει browsers, office suites, installers και ίδια τα launchers."""
    if not name:
        return False

    lowered = name.lower().strip()

    if lowered in LAUNCHER_NAMES or os.path.splitext(lowered)[0] in LAUNCHER_NAMES:
        return False

    return not any(ignored in lowered for ignored in IGNORED_KEYWORDS)


def _is_env_assignment(token):
    """True αν το token είναι ζεύγος μεταβλητής περιβάλλοντος (π.χ. WINEPREFIX=...).
    Η τιμή μπορεί να περιέχει slashes, οπότε ελέγχουμε μόνο το όνομα της μεταβλητής."""
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token))


def _first_exec_token(command):
    """Επιστρέφει το πρώτο πραγματικό εκτελέσιμο μιας γραμμής Exec=.

    Αφαιρεί επιλέγοντα env μεταβλητές, π.χ. "env WINEPREFIX=... /games/game.exe"."""
    tokens = command.split()

    while tokens and tokens[0] == "env":
        tokens.pop(0)
        while tokens and _is_env_assignment(tokens[0]):
            tokens.pop(0)

    return tokens[0] if tokens else ""


def _is_launchable_command(command):
    """True αν η εντολή δείχνει σε πραγματικό πρόγραμμα που μπορεί να εκτελεστεί."""
    token = _first_exec_token(command)
    if not token:
        return False

    # Wine/Proton και packaged binaries έχουν επέκταση
    if token.lower().endswith(LAUNCHABLE_SUFFIXES):
        return True

    # Τα native Linux builds είναι συνήθως executables χωρίς επέκταση
    if os.path.isabs(token):
        return os.path.isfile(token) and os.access(token, os.X_OK)

    return shutil.which(token) is not None


# Οι Epic manifest δεν περιέχουν πραγματική διεύθυνση εικόνας. Χρησιμοποιείται
# μια χειροκίνητη υπόδειξη για συγκεκριμένους τίτλους (Steam cover fallback).
EPIC_IMAGE_HINTS = {
    "sonic mania": "https://cdn2.unrealengine.com/egs-sonicmania-sega-s2-1200x1600-244243640.jpg",
}


def _expand(path):
    return os.path.normpath(os.path.expanduser(path))


def _existing_dirs(paths):
    resolved = []
    for path in paths:
        full = _expand(path)
        if os.path.isdir(full) and full not in resolved:
            resolved.append(full)
    return resolved


# ==========================================
# STEAM
# ==========================================
def _steam_roots():
    """Πιθανές ρίζες του Steam client, ανάλογα με το OS."""
    roots = []

    if IS_WINDOWS:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                if steam_path:
                    roots.append(steam_path)
        except Exception:
            pass

        roots += [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
            r"D:\Steam\SteamLibrary",
            r"E:\Steam\SteamLibrary",
            r"D:\SteamLibrary",
            r"E:\SteamLibrary",
        ]
    elif IS_MACOS:
        roots.append("~/Library/Application Support/Steam")
    else:
        roots += [
            "~/.steam/steam",
            "~/.steam/root",
            "~/.local/share/Steam",
            "~/.var/app/com.valvesoftware.Steam/data/Steam",
            "~/.var/app/com.valvesoftware.Steam/.steam/steam",
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
            "~/.steam/debian-installation",
            "~/.local/share/Steam/steamapps",
        ]

    return _existing_dirs(roots)


def _steam_libraries(steam_root):
    """Διαβάζει το libraryfolders.vdf ώστε να βρει και τα δεύτερα/τρίτα libraries."""
    libraries = [steam_root]
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")

    if os.path.isfile(vdf_path):
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            content = ""

        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
            # Το Steam γράφει τα Windows paths με escaped backslashes.
            fixed = raw_path.replace("\\\\", "\\").replace("\\/", "/")
            library = _expand(fixed)
            if os.path.isdir(library) and library not in libraries:
                libraries.append(library)

    return libraries


def _parse_acf(acf_path):
    """Επιστρέφει (name, appid) από ένα Steam appmanifest_*.acf."""
    try:
        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return None, None

    name = re.search(r'"name"\s+"([^"]*)"', content)
    appid = re.search(r'"appid"\s+"([^"]*)"', content)

    if not name or not appid:
        return None, None

    return name.group(1), appid.group(1)


def _detect_steam(found_names):
    games = []

    for root in _steam_roots():
        for library in _steam_libraries(root):
            pattern = os.path.join(library, "steamapps", "appmanifest_*.acf")
            for manifest in glob.glob(pattern):
                title, app_id = _parse_acf(manifest)
                if not title or title in found_names or not is_valid_game(title):
                    continue

                found_names.add(title)
                games.append({
                    "title": title,
                    "platform": "Steam",
                    # Εικόνα εξωφύλλου απευθείας από το CDN του Steam
                    "image_url": f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg",
                })

    return games


# ==========================================
# EPIC GAMES
# ==========================================
def _epic_manifest_dirs():
    if IS_WINDOWS:
        candidates = [
            r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests",
            r"C:\ProgramData\Epic\UnrealEngineLauncher\Manifests",
        ]
    elif IS_MACOS:
        candidates = [
            "~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests",
        ]
    else:
        candidates = [
            "~/.config/Epic/EpicGamesLauncher/Data/Manifests",
            "~/.config/Epic/Manifests",
            "~/.var/app/com.heroicgameslauncher.hgl/config/Epic/EpicGamesLauncher/Data/Manifests",
            "~/.var/app/com.epicgames.launcher/config/Epic/EpicGamesLauncher/Data/Manifests",
        ]

    return _existing_dirs(candidates)


def _detect_epic(found_names):
    games = []

    for manifest_dir in _epic_manifest_dirs():
        for file_name in os.listdir(manifest_dir):
            if not file_name.endswith(".item"):
                continue

            try:
                with open(os.path.join(manifest_dir, file_name), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            title = data.get("DisplayName")
            if not title or title in found_names or not is_valid_game(title):
                continue

            found_names.add(title)
            games.append({
                "title": title,
                "platform": "Epic Games",
                "image_url": EPIC_IMAGE_HINTS.get(title.lower()),
            })

    return games


# ==========================================
# GOG
# ==========================================
def _gog_search_roots():
    if IS_WINDOWS:
        candidates = [
            r"C:\GOG Games\Galaxy\Games",
            r"D:\GOG Games\Galaxy\Games",
            r"C:\Program Files (x86)\GOG Galaxy\Games",
            r"C:\Program Files\GOG Galaxy\Games",
        ]
    elif IS_MACOS:
        candidates = [
            "~/Library/Application Support/GOG.com/Games",
            "~/GOG Games",
        ]
    else:
        candidates = [
            "~/.config/heroic/gog_store",
            "~/.config/gogstore/games",
            "~/GOG Games",
            "~/.local/share/heroic/gog_store",
        ]

    return _existing_dirs(candidates)


def _parse_goggame(info_path):
    """Επιστρέφει το display name ενός goggame-*.info manifest."""
    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f).get("name")
    except Exception:
        pass

    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            match = re.search(r'"name"\s*:\s*"([^"]+)"', f.read())
        return match.group(1) if match else None
    except OSError:
        return None


def _detect_gog(found_names):
    games = []

    # 1. Windows: πληροφορίες εγκατάστασης από το registry
    if IS_WINDOWS:
        try:
            import winreg

            gog_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\GOG.com\Games")
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(gog_key, index)
                    subkey = winreg.OpenKey(gog_key, subkey_name)
                    title, _ = winreg.QueryValueEx(subkey, "gameName")
                    if title and title not in found_names and is_valid_game(title):
                        found_names.add(title)
                        games.append({
                            "title": title,
                            "platform": "GOG",
                            "genre": "GOG Game",
                        })
                    index += 1
                except OSError:
                    break
        except Exception:
            pass

    # 2. Όλα τα OS: goggame-*.info manifests (Heroic / GOG Galaxy / Wine)
    for root in _gog_search_roots():
        for info_path in glob.glob(os.path.join(root, "**", "goggame-*.info"), recursive=True):
            title = _parse_goggame(info_path)
            if not title or title in found_names or not is_valid_game(title):
                continue

            found_names.add(title)
            games.append({
                "title": title,
                "platform": "GOG",
                "genre": "GOG Game",
            })

    return games


# ==========================================
# DESKTOP / APPLICATIONS FOLDERS
# ==========================================
def _linux_desktop_dir():
    """Διαβάζει τον πραγματικό φάκελο Desktop από το XDG (μπορεί να μεταφέρει)."""
    xdg = shutil.which("xdg-user-dir")
    if xdg:
        try:
            result = subprocess.run(
                [xdg, "DESKTOP"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            path = result.stdout.strip()
            if path and os.path.isdir(path):
                return path
        except Exception:
            pass
    return _expand("~/Desktop")


def _desktop_dirs():
    """ΜΟΝΟ η επιφάνεια εργασίας του χρήστη.

    Σκόπιμα δεν σαρώνονται τα «προγράμματα»/start menu (/usr/share/applications,
    /Applications, Steam library), γιατί θα επέστρεφαν κάθε εγκατεστημένη
    εφαρμογή ως «παιχνίδι» - ακριβώς όπως και στην αρχική Windows έκδοση."""
    if IS_WINDOWS:
        try:
            import winshell

            return _existing_dirs([winshell.desktop()])
        except Exception:
            return _existing_dirs(["~/Desktop", "~/OneDrive/Desktop"])

    if IS_MACOS:
        return _existing_dirs(["~/Desktop", "~/Applications"])

    return _existing_dirs([_linux_desktop_dir()])


def _detect_windows_shortcuts(desktop_dir):
    games = []
    try:
        from win32com.client import Dispatch
    except Exception:
        return games

    try:
        shell = Dispatch("WScript.Shell")
    except Exception:
        return games

    for file_name in os.listdir(desktop_dir):
        if not file_name.endswith(".lnk"):
            continue

        shortcut_path = os.path.join(desktop_dir, file_name)
        try:
            target = shell.CreateShortCut(shortcut_path).TargetPath
        except Exception:
            continue

        title = file_name[:-4]
        if not target.lower().endswith(LAUNCHABLE_SUFFIXES):
            continue

        games.append({"title": title, "path": target, "platform": "PC Game", "genre": "Standalone Game"})

    return games


def _detect_linux_desktop_entries(desktop_dir):
    games = []

    for file_name in sorted(os.listdir(desktop_dir)):
        if not file_name.endswith(".desktop"):
            continue

        entry_path = os.path.join(desktop_dir, file_name)
        try:
            with open(entry_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue

        if "NoDisplay=true" in content or "Hidden=true" in content:
            continue

        name = re.search(r"^Name=(.+)$", content, re.MULTILINE)
        exec_line = re.search(r"^Exec=(.+)$", content, re.MULTILINE)
        if not name or not exec_line:
            continue

        title = name.group(1).strip()
        command = _first_exec_token(exec_line.group(1))
        if not _is_launchable_command(exec_line.group(1)):
            continue

        games.append({"title": title, "path": command, "platform": "PC Game", "genre": "Standalone Game"})

    return games


def _macos_bundle_name(bundle_path):
    """Διαβάζει το CFBundleName από ένα .app bundle."""
    info_plist = os.path.join(bundle_path, "Contents", "Info.plist")

    try:
        with open(info_plist, "rb") as f:
            plist = plistlib.load(f)
    except Exception:
        plist = None

    if plist:
        for key in ("CFBundleDisplayName", "CFBundleName"):
            if plist.get(key):
                return plist[key]

    return os.path.splitext(os.path.basename(bundle_path))[0]


def _macos_bundle_is_launchable(bundle_path):
    macos_dir = os.path.join(bundle_path, "Contents", "MacOS")
    if not os.path.isdir(macos_dir):
        return False
    return any(os.access(os.path.join(macos_dir, entry), os.X_OK) for entry in os.listdir(macos_dir))


def _detect_macos_bundles(desktop_dir):
    games = []

    for file_name in sorted(os.listdir(desktop_dir)):
        if not file_name.endswith(".app"):
            continue

        bundle_path = os.path.join(desktop_dir, file_name)
        if not _macos_bundle_is_launchable(bundle_path):
            continue

        title = _macos_bundle_name(bundle_path)
        if not title:
            continue

        games.append({"title": title, "path": bundle_path, "platform": "Mac Game", "genre": "Standalone Game"})

    return games


def _detect_desktop_entries(found_names):
    games = []

    for desktop_dir in _desktop_dirs():
        if IS_WINDOWS:
            candidates = _detect_windows_shortcuts(desktop_dir)
        elif IS_MACOS:
            candidates = _detect_macos_bundles(desktop_dir)
        else:
            candidates = _detect_linux_desktop_entries(desktop_dir)

        for candidate in candidates:
            title = candidate["title"]
            if not title or title in found_names or not is_valid_game(title):
                continue

            found_names.add(title)
            games.append({
                "title": title,
                "platform": candidate["platform"],
                "genre": candidate["genre"],
            })

    return games


def detect_installed_games():
    """Ανιχνεύει παιχνίδια από Steam, Epic, GOG και τον φάκελο εφαρμογών/
    επιφάνειας εργασίας, ανεξάρτητα από το λειτουργικό σύστημα."""
    found_names = set()
    games = []

    games.extend(_detect_epic(found_names))
    games.extend(_detect_steam(found_names))
    games.extend(_detect_gog(found_names))
    games.extend(_detect_desktop_entries(found_names))

    return games