# Architecture and Development Workflows

HorusAccess is a desktop accessibility controller: a webcam tracks the user's
head and face, and those movements are translated into keyboard and mouse input.
Profiles (1–5) store the motion → key mappings, and an optional local LLM
("Horus AI") can propose a profile for a detected game.

This document covers how the code is organised, how a camera frame becomes
input, how the windows and database interact, and the workflows for running,
testing and extending the project.

**Contents:** [At a glance](#1-at-a-glance) ·
[Directory map](#2-directory-map) · [Startup](#3-startup-workflow) ·
[Tracking loop](#4-frame-by-frame-tracking-workflow) ·
[Gesture data flow](#5-gesture--key-data-flow) · [Windows](#6-window-workflows) ·
[Persistence](#7-persistence) · [Platform backends](#8-platform-input-backends) ·
[Snapping](#9-cursor-snapping) · [Testing](#10-testing-workflow) ·
[Development](#11-development-workflows) · [Invariants](#12-invariants-worth-protecting) ·
[Next steps](#13-where-to-look-next)

---

## 1. At a glance

```
HorusAccess/main.py              bootstrap, SHOW_FACE_MESH
        │
        ▼
HorusAccess/gui/main.py          Tk windows + face-tracking loop
        │
        ├── gui/common.py        key layout, fonts, modal grab
        ├── gui/snapping.py      magnetic cursor targets
        ├── core/                tracking, input, detection, AI rules
        └── database/            SQLite persistence
```

Five layering rules keep the system predictable:

1. **`core/` is display-light.** Tracking maths, input injection, key names and
   AI mapping rules live here. Everything except `input_backend` can be
   imported and tested without a display.
2. **`gui/` owns every Tk widget.** No other package creates or configures a
   window.
3. **All synthetic input goes through `core/input_backend.py`.** No other module
   imports `pydirectinput`, `pynput` or `pyautogui` directly.
4. **`core/gestures.py` is the single gesture registry.** The UI, the LLM
   prompt, threshold defaults and the frame dispatcher all read it.
5. **The database stores canonical actions and keys.** Aliases are normalised on
   write and migrated once on startup.

---

## 2. Directory map

| Path | Responsibility | Notable entry points |
| --- | --- | --- |
| `Makefile` | Environment, run, test and clean targets. | `setup`, `run`, `test`, `clean` |
| `requirements.txt` | Runtime and per-OS dependencies. | — |
| `HorusAccess/main.py` | Application bootstrap; defines `SHOW_FACE_MESH`. | `run_app()` |
| `HorusAccess/gui/main.py` | App shell, all dialog windows, camera loop and gesture dispatch. | `SmartControllerApp`, `AutonomousGameSelectorWindow`, `ProfileReviewWindow`, `MotionInputWindow` |
| `HorusAccess/gui/common.py` | Shared key layout/labels, OS-aware font factory, reliable modal grab. | `KEYBOARD_LAYOUT`, `key_label()`, `ui_font()`, `grab_modal()` |
| `HorusAccess/gui/snapping.py` | Finds the controls of the active window and snaps the cursor to their centres. | `SnapCursorMixin`, `SNAP_DISTANCE` |
| `HorusAccess/core/input_backend.py` | Cross-platform mouse/keyboard injection, pointer polling and webcam opening. | `mouse_move()`, `key_down()`, `key_up()`, `open_webcam()` |
| `HorusAccess/core/sway_ipc.py` | Native sway IPC pointer warps and focus handling on Wayland. | `SwayIPC` |
| `HorusAccess/core/keys.py` | Canonical key vocabulary and backend aliases. | `canonical_key()`, `BUTTON_ALIASES` |
| `HorusAccess/core/gestures.py` | Gesture registry, facial metrics, head-pose calibration. | `GESTURES`, `compute_facial_metrics()`, `HeadPoseTracker` |
| `HorusAccess/core/ai_mappings.py` | Horus AI prompt, validation, platformer detection, fallbacks, click rule. | `build_request()`, `validate_mappings()`, `ensure_left_click()` |
| `HorusAccess/core/game_detector.py` | Installed-game detection for Steam, Epic, GOG and desktop entries. | `detect_installed_games()` |
| `HorusAccess/core/game_images.py` | Cover-art download for the game picker (Tk-free). | `download_game_image()` |
| `HorusAccess/core/ui_utils.py` | Font-family selection and nearest-target maths. | `default_font_family()`, `snap_to_nearest()` |
| `HorusAccess/database/db_manager.py` | SQLite schema, profile/mapping/settings queries and migrations. | `DBManager` |
| `tests/` | Headless stdlib `unittest` suite. | `test_*.py` |
| `docs/BUGS.md` | Historical issue log. | — |

### Window classes

| Class | Role | Typical lifetime |
| --- | --- | --- |
| `SmartControllerApp` | Main window, profile selector, sensitivity slider, camera preview, frame loop. Owns `DBManager`, `HeadPoseTracker` and the active mapping cache. | Whole process |
| `AutonomousGameSelectorWindow` | Game grid, cover art, LLM request and confirmation dialog. | Opened by “ΕΠΙΛΟΓΗ HORUS AI” |
| `ProfileReviewWindow` | Table of a profile's mappings; unlock, edit, delete, save. | Opened by “Εμφάνιση Καταχωρημένων” |
| `MotionInputWindow` | Motion + key picker for manual mapping. | Opened by “Εισαγωγή Κίνησης” |

`SnapCursorMixin` is not a window; it adds active-window target discovery and
cursor snapping to `SmartControllerApp`. Its `__init__` is cooperative because
it appears before `ctk.CTk` in the MRO.

---

## 3. Startup workflow

1. `make run` invokes
   `PYTHONPATH=HorusAccess .venv/bin/python HorusAccess/main.py`.
2. `HorusAccess/main.py` imports `SmartControllerApp`, reads `SHOW_FACE_MESH`
   and constructs the app.
3. `SmartControllerApp.__init__` runs through `SnapCursorMixin.__init__` into
   `customtkinter.CTk`, then:
   - creates `DBManager()`, which opens
     `HorusAccess/database/smart_controller.db` and creates/seeds the
     `profiles`, `mappings` and `settings` tables;
   - runs the one-time legacy migrations (per-gesture thresholds, key aliases,
     action aliases);
   - creates the MediaPipe `FaceMesh` and pre-computes mesh/contour/iris edge
     arrays for the preview overlay;
   - reads the screen size and initialises the virtual cursor at screen centre;
   - records the current physical-mouse activity counter.
4. `_build_ui()` builds the main window; `load_profile_data()` restores the last
   profile's sensitivity and `refresh_active_mappings()` loads its mappings into
   memory.
5. `open_webcam(0, 640, 480)` opens the camera with the OS-appropriate backend.
6. `self.after(100, self.start_video_loop)` lets the window paint before the
   first frame.
7. `start_video_loop()` calls `update_video()` and re-schedules itself every
   **15 ms** (~60 FPS) on the Tk main thread.

The database is not created in the repository root: `DBManager` resolves the
filename next to `db_manager.py`, so profiles live at
`HorusAccess/database/smart_controller.db` and are gitignored.

---

## 4. Frame-by-frame tracking workflow

Every tick of `SmartControllerApp.update_video()` performs the same pipeline:

```
camera.read()
   → flip + RGB
   → MediaPipe FaceMesh
   → optional mesh overlay
   → physical-mouse override check
   → head roll/pitch → virtual cursor delta
   → clamp to screen
   → snap to active-window control
   → input_backend.mouse_move()
   → facial metrics + head-pose metrics
   → active mapping thresholds → desired key set
   → diff against pressed keys → key_down / key_up
   → update the preview image
```

### 4.1 Pointer movement

1. The frame is mirrored horizontally, so the user moves their head as if
   looking at the screen.
2. Roll (`right_face.y - left_face.y`) drives horizontal movement; pitch
   (`nose.y - face_center_y`) drives vertical movement.
3. Deadzones suppress noise (`0.025` for roll, `0.005` for pitch) and the
   profile sensitivity slider scales the remaining movement.
4. The virtual cursor is clamped to the screen and passed through
   `SnapCursorMixin._snap_cursor()`.
5. `input_backend.mouse_move()` chooses the platform route:
   - sway: `seat - cursor set` over IPC, plus focus of the window under the
     pointer;
   - Linux with pynput: `mouse.Controller.position`;
   - otherwise: `pyautogui`/`pydirectinput` `moveTo()`.
6. Each injected position is remembered as a warp, so the next physical-mouse
   poll can tell synthetic movement from a real hand movement.

### 4.2 Physical-mouse override

`input_backend.mouse_activity_count()` increments when the real pointer moves
without a matching warp. When the counter changes, the app pauses head-driven
warps for `MOUSE_OVERRIDE_SECONDS` (3 s) and keeps re-syncing the virtual cursor
to the real pointer. This works on Windows, X11 and macOS; on sway the polling
observes XWayland's mirrored pointer, so it covers the app's own UI and
XWayland games.

When tracking is toggled off, the virtual cursor is re-synced and the activity
counter is refreshed, so resuming does not immediately re-trigger the override.

### 4.3 Gesture dispatch

1. `compute_facial_metrics(landmarks)` returns the facial metric values.
2. `HeadPoseTracker.update(landmarks)` adds calibrated head metrics. The first
   neutral pose is captured automatically; “Επαναφορά Κέντρου” resets it.
3. For each active mapping, `is_gesture_active(action, value, threshold)` applies
   the gesture's direction — `value > threshold` for most gestures,
   `value < threshold` for blinks, frown, jaw and nose scrunch.
4. The dispatcher builds a **desired key set**, then diffs it against
   `pressed_keys`:
   - keys only in the desired set are pressed;
   - keys only in the pressed set are released.
5. If no face is detected, `_release_all_keys()` runs, so a key cannot stay
   stuck down when tracking is lost.

Mapping to the same key from two motions is safe: the key stays pressed until
the last motion releases it.

### 4.4 Preview

The RGB frame is copied into one reusable `ImageTk.PhotoImage`, with the face
mesh drawn only when `SHOW_FACE_MESH` is `True`. Reusing the image avoids a new
allocation every frame. `SHOW_FACE_MESH` is read once at startup.

---

## 5. Gesture → key data flow

```
GESTURES registry
   ├── UI motion picker       (display_name / short_display_name)
   ├── AI prompt              (AVAILABLE_MOTIONS)
   ├── threshold defaults     (default_threshold)
   └── frame dispatcher       (is_gesture_active)
              ▲
              │
      active_mappings {motion: {key, threshold}}
              ▲
              │
      database mappings table
```

`refresh_active_mappings()` reloads the current profile after any edit and
canonicalises each stored action. Unknown actions are skipped with a warning,
which keeps old or hand-edited databases usable.

Thresholds are stored per mapping. A new mapping gets the gesture's default; an
existing mapping keeps its value when only the key changes.

### Last-click invariant

The manual editors protect an **existing** `left_click` binding:

- a click binding cannot be deleted or reassigned unless another mapping still
  maps to `left_click`;
- a profile that never had a click binding may remain keyboard-only (for
  example a 2D platformer profile).

Horus AI additionally guarantees a click for generic PC games via
`ensure_left_click()`, because the LLM sometimes follows the schema example too
closely and omits it.

---

## 6. Window workflows

### 6.1 Manual mapping — `MotionInputWindow`

1. The user picks one motion and one key; the save button enables only when both
   are selected.
2. `save_to_db()` reads the **parent's current profile**, so changing the
   profile while the picker is open still writes to the right place.
3. It checks the last-click invariant, then upserts the mapping with the
   gesture's default threshold.
4. The modal grab is released and the window stays open for more mappings; the
   main window's mappings and sensitivity are refreshed immediately.
5. Closing the window releases the grab.

### 6.2 Review and edit — `ProfileReviewWindow`

1. The window opens with a modal grab in edit mode, showing one row per stored
   mapping.
2. “Αποθήκευση & Κλείδωμα” validates **every** edited row first (known key,
   numeric threshold in `(0, 1]`), then writes all updates, so a bad row cannot
   leave the profile half-updated.
3. Saving re-checks that a pre-existing click binding still exists, then
   refreshes the main window's active mappings and locks the table.
4. While locked, “Ξεκλείδωμα” re-enables the key dropdowns, threshold entries,
   edit and delete buttons.
5. Deletion checks the last-click invariant before removing the row.

### 6.3 Horus AI — `AutonomousGameSelectorWindow`

1. Opening the selector installs a modal grab and starts game detection in a
   daemon thread. The Tk thread keeps painting.
2. `detect_installed_games()` scans Steam, Epic, GOG and desktop entries for the
   current OS. Results return through a thread-safe queue and are rendered as
   cards; cover art is downloaded in another worker thread.
3. Selecting a card calls `build_request(game_title)` from
   `core/ai_mappings.py`. This pure function returns:
   - the prompt,
   - the allowed key list,
   - the fallback profile.
4. A worker calls Ollama (`llama3.2:1b`, falling back to `llama3.2`) with
   `format='json'`, parses the response, and passes it to
   `validate_mappings()`, which drops unknown gestures, disallowed keys and
   duplicates.
5. Back on the Tk thread:
   - empty or invalid output falls back to the category-specific profile;
   - non-platformer games get `ensure_left_click()`;
   - the first completely empty profile from 1–5 is selected; if none is free,
     a warning explains that a profile must be cleared first.
6. The confirmation dialog lists the proposed bindings. **OK** saves every
   mapping with its gesture default, renames the profile to the game title,
   switches to it and closes both dialogs. Closing without OK saves nothing.

2D platformers are detected from known title hints. Their prompts forbid mouse
clicks, their allowed-key list excludes them, and their fallback has no click.

### 6.4 Profiles, sensitivity and shutdown

- Changing the profile selector persists the new id in `settings`, reloads the
  sensitivity and refreshes the active mappings.
- Moving the sensitivity slider updates the label immediately and debounces the
  database write by 400 ms.
- Closing the app cancels a pending sensitivity save, releases every pressed
  key, persists the last profile, releases the camera and destroys the window.

---

## 7. Persistence

**Location:** `HorusAccess/database/smart_controller.db` (gitignored).

| Table | Columns | Notes |
| --- | --- | --- |
| `profiles` | `id` (1–5), `name`, `sensitivity` | Seeded with `Profile 1`…`Profile 5`; `id` is constrained by a `CHECK`. |
| `mappings` | `id`, `profile_id`, `action`, `mapped_key`, `threshold` | `UNIQUE(profile_id, action)`; saving the same motion updates the row. |
| `settings` | `key`, `value` | Last profile, migration markers. |

Write rules:

- keys and known actions are canonicalised by `save_mapping()` /
  `update_mapping()`;
- `UNIQUE(profile_id, action)` makes saves an upsert;
- thresholds are preserved on key-only edits.

One-time migrations are guarded by markers in `settings`:

| Migration | Marker |
| --- | --- |
| Legacy `0.05` threshold → per-gesture defaults | `threshold_defaults_v2` |
| Legacy key spellings → canonical keys | `key_aliases_v1` |
| Legacy action names (`kiss`) → canonical action | `action_aliases_v1` |

Because the markers are one-shot, adding **new** aliases later requires either a
new marker key or a version bump, otherwise existing databases will not be
re-scanned. New databases are unaffected.

---

## 8. Platform input backends

| Platform | Pointer | Keyboard | Notes |
| --- | --- | --- | --- |
| Windows | `pydirectinput` / `pyautogui` metrics | `pydirectinput` | Scan Code injection reaches DirectX games. |
| Linux (X11) | `pynput` when available, else `pyautogui`/XTest | `pynput` or `pyautogui` | `pynput` is preferred for reliability. |
| Linux (sway/Wayland) | sway IPC (`seat - cursor set`) | `pynput` | Wayland ignores XTest warps; keyboard/click injection may still be ignored by native Wayland windows. |
| macOS | `pyautogui` (Quartz) | `pyautogui` | Requires Accessibility permission for the terminal. |

`core/input_backend.py` owns every platform branch and translates canonical key
names before injection. If the sway IPC path fails, it logs once and degrades to
the X11 backend instead of raising every frame.

### Sway specifics

- The IPC path activates when both `WAYLAND_DISPLAY` and `SWAYSOCK` are present.
- The compositor pointer is moved with `seat - cursor set`, and the window under
  the pointer is focused to emulate `focus_follows_mouse`. That lets the app's
  own controls receive hover and clicks.
- `sway_ipc.py` queries the output layout for the desktop size and remembers the
  last pointer position.
- Physical-mouse override on sway depends on XWayland mirroring the pointer; it
  works over the app UI and XWayland games, but not over native Wayland
  surfaces.

---

## 9. Cursor snapping

`gui/snapping.py` implements the magnetic-cursor behaviour:

1. Prefer the grabbed window (`grab_current()`), then the focused widget, then
   the topmost viewable toplevel in `wm stackorder`.
2. Walk that toplevel for buttons, sliders, switches, checkboxes and option
   menus.
3. Keep only viewable controls larger than 1×1 whose centre is actually exposed
   (`winfo_containing`), so hidden or covered controls are not targets.
4. Convert root coordinates to the pointer coordinate space with
   `screen_origin()`.
5. Cache the target list for **0.5 s**.
6. Snap within **45 px** of a centre using `snap_to_nearest()`.

Snapping is applied only to the head-driven warp, never to the physical pointer,
so manual mouse use is unaffected. A widget that disappears mid-scan is skipped
without aborting the whole scan.

---

## 10. Testing workflow

```bash
make test
# equivalent to:
.venv/bin/python -m unittest discover -s tests
```

The suite uses only the standard library's `unittest`; do not add a test
dependency. Tests import the package form (`HorusAccess.core...`,
`HorusAccess.database...`) and must stay headless — no display, camera, audio or
network required.

| Test file | Focus |
| --- | --- |
| `tests/test_gestures.py` | Registry completeness, metric maths, head-pose calibration and direction handling. |
| `tests/test_keys.py` | Canonical key names and aliases. |
| `tests/test_db_manager.py` | Schema seed, upsert/threshold behaviour, scoping, aliases, one-time migrations, settings. |
| `tests/test_game_detector.py` | Exec parsing, launchability filters, GOG/desktop manifests, detector isolation and sorting. |
| `tests/test_input_backend.py` | Physical-pointer polling, synthetic-warp accounting and override behaviour. |
| `tests/test_sway_ipc.py` | IPC framing, output layout, pointer warps, focus-follows-hover and gap refocus. |
| `tests/test_ui_utils.py` | Nearest-target snapping maths. |
| `tests/test_ai_mappings.py` | Platformer detection, prompt rules, validation, click guarantee and fallbacks. |

Pure logic belongs in `core/` so it can be covered here. Tk behaviour — modal
grabs, snapping against real widgets, window stacking — needs a live display and
is verified with manual or scripted probes rather than unit tests.

Expected noise in the test output:

```
⚠️ Αποτυχία ανίχνευσης GOG: permission denied
⚠️ Αποτυχία ανίχνευσης test: broken
```

Both come from deliberate failure-injection tests and are not failures.

---

## 11. Development workflows

### Set up and run

```bash
make setup      # create .venv (Python 3.11/3.12) and install requirements
make run        # PYTHONPATH=HorusAccess .venv/bin/python HorusAccess/main.py
make test       # headless unittest suite
make clean      # remove .venv; the database is preserved
```

`mediapipe` requires Python 3.11 or 3.12. On Linux, install `python3-tk` and
`xdotool`; on macOS, grant Accessibility permission to the terminal.

### Add or change a gesture

1. Add a `GestureSpec` to `GESTURES` in `core/gestures.py` (name, labels,
   direction, default threshold). Insertion order is the UI order.
2. If it is a facial gesture, compute its value in `compute_facial_metrics()`
   and add it to `_FACIAL_METRICS`. Head gestures are produced by
   `HeadPoseTracker`.
3. Add tests for the metric and its direction in `tests/test_gestures.py`.
4. Nothing else needs editing: the picker, AI prompt and dispatcher read the
   registry. Existing profiles are unaffected until the user maps the new
   gesture.

### Add a key or alias

1. Add the alias to `_CANONICAL_ALIASES` in `core/keys.py`.
2. If the key belongs in the picker, add it to `KEYBOARD_LAYOUT` in
   `gui/common.py` (and a display label in `_KEY_LABELS` if it is a special key).
3. Add a test in `tests/test_keys.py`.
4. If existing databases must be re-scanned, bump the migration marker
   (`key_aliases_v1` → a new version) or add a new marker; otherwise only new
   writes are normalised.

### Change the Horus AI behaviour

- Prompt text, allowed keys, platformer hints and fallback profiles live in
  `core/ai_mappings.py`.
- Validation and the guaranteed click policy also live there; keep them pure and
  GUI-free.
- Extend `tests/test_ai_mappings.py` for every rule change.
- The window in `gui/main.py` should only orchestrate: build the request, run
  Ollama in a worker, show the result, save on confirmation.

### Change snapping

Edit `gui/snapping.py`; keep the mixin free of app-specific state other than
`_snap_cache`. The contract is “return target centres in pointer coordinates”.
Live-check with a display after changes: modal stacking, multiple toplevels and
widgets that disappear mid-scan are the fragile cases.

### Change the database schema

1. Add the change to `_create_tables()` / `_initialize_profiles()` for new
   databases.
2. Add a one-time migration for existing databases, guarded by a `settings`
   marker.
3. Keep writing canonical actions/keys, and add tests in
   `tests/test_db_manager.py` for both fresh and migrated data.
4. Do not commit `smart_controller.db`; it is user data and gitignored.

### Code conventions

- Comments and user-facing strings mix Greek and English; match the surrounding
  file rather than translating it.
- `HorusAccess/database/db_manager.py` uses CRLF line endings. Preserve them to
  keep diffs readable.
- Keep new runtime dependencies out unless they are unavoidable; the test suite
  must remain stdlib-only.
- Preserve the layering rules in section 1 when adding modules.

---

## 12. Invariants worth protecting

- Every advertised motion exists in `GESTURES`.
- Every synthetic input event passes through `core/input_backend.py`.
- Stored actions and keys are canonical.
- A `left_click` binding cannot be removed without a replacement.
- Head tracking never overrides a physical mouse movement for at least the
  override window.
- Face loss releases all held keys.
- Snapping targets only exposed controls of the active toplevel.
- Modal windows call `grab_modal()` after their content is built, never before.
- `SnapCursorMixin.__init__` stays cooperative (`super().__init__(...)`).

---

## 13. Where to look next

- **Historical issues and fixes:** `docs/BUGS.md`.
- **User-facing setup and limitations:** `README.md`.
- **Refactor roadmap:** the next steps are to split the three dialogs into
  `gui/autonomous_selector.py`, `gui/profile_review.py` and
  `gui/motion_input.py`, then, if still useful, extract the face-tracking loop
  into `gui/face_loop.py` with pure helpers in `core/tracking.py`.
