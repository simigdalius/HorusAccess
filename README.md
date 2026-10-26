# HorusAccess

Head-tracked and face-gesture game controller. Uses the webcam to map head
movements and facial gestures to keyboard and mouse input, with an optional
local LLM ("Horus AI") that generates control mappings for a game.

Runs on **Windows, Linux and macOS**.

## Get Started

```bash
git clone https://github.com/simigdalius/HorusAccess && cd HorusAccess
```

### 1. Set up the environment

```bash
make setup
```

This creates a `.venv` virtual environment and installs everything from
`requirements.txt`. Run it from the repository root.

`make setup` uses [`uv`](https://docs.astral.sh/uv/) to fetch Python 3.12
automatically if it is installed, otherwise it falls back to a `python3.12` or
`python3.11` already on your `PATH`. **A Python 3.11/3.12 interpreter is
required** — `mediapipe` publishes no wheels for 3.13+, so the install fails on
newer interpreters. If you have neither `uv` nor 3.11/3.12 available, `make
setup` exits with an error rather than creating a broken venv.

### 2. System packages

**Linux** — Tk is required by `customtkinter`, and `xdotool` by `pyautogui`:

```bash
sudo apt install python3-tk xdotool     # Debian / Ubuntu
sudo pacman -S tk xdotool               # Arch
```

An X11 or Wayland display is required; the app cannot run headless.

**macOS** — `tk` ships with the system Python, so there is nothing extra to
install. You do need to grant Accessibility permission to your terminal
(*System Settings → Privacy & Security → Accessibility*), otherwise
`pyautogui` cannot move the mouse or send key events.

### 3. Run

```bash
make run
```

Equivalent to `PYTHONPATH=HorusAccess .venv/bin/python HorusAccess/main.py`.

You can also skip the venv entirely and run it by hand — in that case the
inner `HorusAccess/` directory must be the one on `sys.path`, so `cd` into it:

```bash
cd HorusAccess && python main.py
```

### 4. (Optional) Horus AI

Only the **"ΕΠΙΛΟΓΗ HORUS AI"** button needs a local LLM. Everything else
works without it.

```bash
ollama serve &
ollama pull llama3.2:1b
```

If no model is available, that button falls back to a built-in default mapping
for the detected game category instead of failing.

## Make targets

| Target | What it does |
| --- | --- |
| `make help` | Lists the available targets. |
| `make setup` | Creates `.venv` (Python 3.11/3.12, via `uv` if available) and installs `requirements.txt`. Recreates the venv if it is missing or has no `pip`. |
| `make run` | Launches the app with `PYTHONPATH=HorusAccess .venv/bin/python HorusAccess/main.py`. Errors out if `.venv` is missing, telling you to run `make setup`. |
| `make test` | Runs the unit tests with `.venv/bin/python -m unittest discover -s tests`. Errors out if `.venv` is missing, telling you to run `make setup`. |
| `make clean` | Removes `.venv`. Does not touch your saved mappings. |

All targets are `.PHONY`, so they work even though no file by those names
exists.

`make clean` deletes the virtual environment only. Your profiles live in
`HorusAccess/database/smart_controller.db` and are preserved.

## First run

- The camera opens automatically on device `0`. The terminal prints
  `✅ Η κάμερα στο ID 0 άνοιξε επιτυχώς!` on success. Face tracking is
  mirrored, so move your head as if looking at the screen.
- The camera preview draws the face mesh by default. Set `SHOW_FACE_MESH =
  False` at the top of `HorusAccess/main.py` to hide the overlay.
- Head tracking pulls the cursor to the centre of a nearby button, slider or
  switch, so aiming at the interface does not have to be pixel-perfect.
- **Εισαγωγή Κίνησης** — pick a facial/head motion, then a key.
- **Εμφάνιση Κατοχωρημένων** — review, edit or delete saved mappings.
- The sensitivity slider scales the mouse and head-tracking gain.
- Profiles 1–5 each keep their own set of mappings, stored in a local SQLite
  database at `HorusAccess/database/smart_controller.db`.

## Known limitations

**Synthetic input may not reach the game on Linux and macOS.** On Windows,
`pydirectinput` injects at the Scan Code layer, which DirectX games read
directly. On Linux and macOS there is no equivalent, so `pyautogui` falls back
to XTest / Quartz events. Many games capture input below that layer and will
ignore them entirely. Mapping and calibration work normally; actual in-game
response is best-effort and game-dependent.

**Pointer movement on Wayland.** Wayland compositors ignore XTest pointer warps,
so `pynput`/`pyautogui` can only move the pointer inside XWayland, not on the
desktop. On **sway**, the app detects `WAYLAND_DISPLAY` together with
`SWAYSOCK` and sends `seat - cursor set` over the sway IPC socket instead, which
moves the compositor pointer without extra packages. Other compositors are not
supported for pointer movement yet; they need something like `ydotool`/`uinput`
(root access) or a RemoteDesktop portal. Keyboard and click injection still go
through `pynput`, so they may be ignored by native Wayland windows.

Each IPC warp also focuses the window that the pointer lands on, emulating sway's
`focus_follows_mouse`, so hovering another app gives it the keyboard focus and
the app's own UI can be aimed at and clicked too. Moving the physical mouse
pauses head tracking for a few seconds, so the cursor can be repositioned by
hand without the tracker pulling it back every frame. That detection relies on
XWayland's pointer position, which is only mirrored while the pointer is over an
X11 window, so it works over the app's UI and XWayland games but not over native
Wayland surfaces.

**mediapipe on Apple Silicon.** Official `mediapipe` wheels are built for
Intel macOS; expect to build from source or use Rosetta on M-series Macs.

**Font availability.** The UI picks the first installed font from a per-OS
preferred list (Segoe UI on Windows, SF Pro on macOS, Ubuntu/Cantarell/DejaVu
on Linux). On a minimal Linux install with few fonts installed, Tk may only
report a couple of families and the UI falls back to whatever remains.

## Project layout

```
HorusAccess/
├── Makefile                     setup / run / clean targets
├── requirements.txt
├── main.py                      entry point (via make run)
└── HorusAccess/
    ├── main.py                  app bootstrap
    ├── gui/gui_main.py          all windows and the face-tracking loop
    ├── core/
    │   ├── input_backend.py     mouse/keyboard + webcam, per-OS
    │   ├── game_detector.py     installed-game detection, per-OS
    │   └── ui_utils.py          OS-aware font selection
    └── database/db_manager.py   SQLite schema and queries
```

Run all `make` targets from the repository root.

The `core/` package holds everything platform-specific — `gui/gui_main.py`
contains no OS-conditional code. Game detection scans Steam (including
secondary libraries via `libraryfolders.vdf`), Epic Games, GOG, and your
desktop: `.lnk` shortcuts on Windows, `.desktop` entries on Linux, and `.app`
bundles on macOS.

