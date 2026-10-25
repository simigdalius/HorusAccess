# HorusAccess — Known Issues / Bug Tracker

Living document for the defects found during the code review of the current
codebase. **Batches 1 and 2 (30 items) are implemented** — see
[Appendix C — Batch 1 resolution log](#appendix-c--batch-1-resolution-log) and
[Appendix D — Batch 2 resolution log](#appendix-d--batch-2-resolution-log). The
remaining 6 items are still findings waiting for a product decision or a
separate change; the problem descriptions below stay in their pre-fix form so
the original analysis remains readable.

| Field | Meaning |
| --- | --- |
| **ID** | Stable identifier. Keep it when editing so links/comments survive. |
| **Severity** | S1 Critical · S2 High · S3 Medium · S4 Low |
| **Status** | `open` · `in-progress` · `fixed` · `wontfix` · `verified` |
| **Area** | `gestures` · `gui` · `db` · `llm` · `detector` · `input` |

**Review context**

- Commit: `1d9694d` ("chore: removed database"), branch `refactor`
- Platform used for verification: Linux · Python 3.12 · mediapipe 0.10.21
  · customtkinter · pynput · pyautogui (X11)
- Verification method: static reading + targeted runtime probes (pynput/pyautogui
  key semantics, mediapipe landmark layout, SQLite schema, detector helpers)
  and a numeric simulation of the gesture metrics. See
  [Appendix A — Verification notes](#appendix-a--verification-notes).

---

## Summary

| ID | Severity | Area | Short title | Status |
| --- | --- | --- | --- | --- |
| BUG-001 | S1 | gestures | Head motions can never trigger a key | fixed |
| BUG-002 | S1 | gestures | `lips_pucker` UI action never matches the `kiss` metric | fixed |
| BUG-003 | S1 | gestures | `eyebrows_frown` has no metric at all | fixed |
| BUG-004 | S1 | gestures | Default threshold `0.05` makes 3 gestures permanently active and 5 never fire | fixed |
| BUG-005 | S1 | gestures | Head-roll → mouse X axis is inverted | fixed |
| BUG-006 | S1 | gestures | Pressed keys are never released (face lost / profile switch) | fixed |
| BUG-007 | S2 | gui | `ProfileReviewWindow` is defined twice, second definition shadows the first | fixed |
| BUG-008 | S2 | gui | `enable_edit` / `save_and_lock` reference widgets that are never created | fixed |
| BUG-009 | S2 | gui | Editing keys/thresholds in the review window is not implemented | fixed |
| BUG-010 | S3 | gui | Review-window header column does not align with the rows | fixed |
| BUG-011 | S2 | db | Sensitivity slider value is never persisted | fixed |
| BUG-012 | S2 | db | Game/app name is never stored or displayed | fixed |
| BUG-013 | S3 | db | `INSERT OR REPLACE` + `AUTOINCREMENT` changes row ids on re-save | fixed |
| BUG-014 | S3 | db | Every query opens a connection that is never closed | fixed |
| BUG-015 | S2 | llm | LLM output is not validated against allowed motions/keys | fixed |
| BUG-016 | S2 | llm | Malformed LLM reply raises `KeyError` inside a Tk callback | fixed |
| BUG-017 | S2 | llm | Target-profile fallback silently overwrites profile 1 | fixed |
| BUG-018 | S2 | llm | Ollama call blocks the Tk main thread (UI freeze) | open |
| BUG-019 | S4 | llm | Browser branch is unreachable dead code | open |
| BUG-020 | S2 | detector | Quoted `Exec=` paths containing spaces break detection | fixed |
| BUG-021 | S2 | detector | `is_valid_game` substring blacklist rejects valid games | fixed |
| BUG-022 | S2 | detector | A single unreadable directory aborts *all* game detection | fixed |
| BUG-023 | S3 | detector | `_is_launchable_command` has both false positives and false negatives | fixed |
| BUG-024 | S3 | detector | Windows GOG registry enumeration aborts on the first error | fixed |
| BUG-025 | S3 | detector | `_parse_goggame` regex fallback is unreachable in one case | fixed |
| BUG-026 | S4 | detector | Detected game order is nondeterministic | fixed |
| BUG-027 | S2 | input | pynput silently swallows key names outside `_PYNPUT_SPECIAL_KEYS` | fixed |
| BUG-028 | S3 | input | Key-name mismatch between backends (`page_up` vs `pageup`) | fixed |
| BUG-029 | S3 | input | Alias tables are inconsistent across the three backends | open |
| BUG-030 | S4 | input | `disable_failsafe` early-returns even when pyautogui became the driver | fixed |
| BUG-031 | S2 | gui | Game detection + image downloads + LLM all run on the Tk thread | open |
| BUG-032 | S3 | gui | A new `CTkImage` is allocated every frame (~66/s) | open |
| BUG-033 | S3 | gui | `sys.path` is manipulated *after* the `core.*` imports | fixed |
| BUG-034 | S3 | gui | Destroying the selector window can orphan its child dialog | fixed |
| BUG-035 | S4 | gui | Dead code / unused state across the app | open |
| BUG-036 | S3 | gui | "left_click must be mapped" invariant relies on exact string match | fixed |

**Progress:** 30 fixed (24 in batch 1 + 6 in batch 2) · 6 open (deferred — see
[Appendix B](#appendix-b--suggested-fix-order)).

---

## A. Gesture detection (`HorusAccess/gui/main.py`)

### BUG-001 · S1 · Head motions can never trigger a key

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** `gui/main.py:1269-1295` (metric table + dispatcher), UI list
`gui/main.py:693-696`, AI prompt `gui/main.py:193, 220, 229-232`, fallbacks
`gui/main.py:273-292`.

**Problem**
`current_metrics` only ever contains:
`mouth_open, smile, eyebrows_up, left_eye_blink, right_eye_blink, kiss,
jaw_left, jaw_right, nose_scrunch, cheek_puff`.
There is **no metric for `head_up`, `head_down`, `head_left`, `head_right`**.
The dispatcher then does:

```python
if not target_key or action not in current_metrics:
    continue
```

so every head mapping is silently skipped.

**Impact**
- The Motion Input window offers 4 head motions that can never fire.
- The Horus AI prompt explicitly *orders* the model to prioritise head motions
  (`"ALWAYS prioritize head motions ... for character movement keys"`), and the
  built-in fallback mappings (`head_left→a`, `head_up→w`, `head_down→s`,
  `head_right→d`) are all head motions. The AI therefore produces mappings that
  look correct in the confirmation dialog and do nothing at runtime.
- Head tracking currently only influences the mouse, never the keyboard.

**Fix direction** — either add head-pose metrics (roll/pitch/yaw relative to a
calibrated neutral pose) to `current_metrics` and route them through the same
dispatcher, or remove head motions from the selectable list and from every
AI prompt/fallback so the app never advertises what it cannot do.

---

### BUG-002 · S1 · `lips_pucker` UI action never matches the `kiss` metric

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** `gui/main.py:692` (UI stores `lips_pucker`), `gui/main.py:1275`
(metric is named `kiss`), `gui/main.py:1271` (`smile` metric).

**Problem**
Two separate defects:

1. The "Χείλη Μπροστά (O)" button saves the action `lips_pucker`, but the
   code computes `kiss`. `lips_pucker` is never in `current_metrics` → the
   mapping can never trigger.
2. `kiss` is computed with the **identical formula** as `smile`:

   ```python
   "smile": math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y),
   "kiss":   math.hypot(landmarks[61].x - landmarks[291].x, landmarks[61].y - landmarks[291].y),
   ```

   The two gestures are mathematically the same distance with opposite
   polarity, so at most one of them can ever be true. A puckered mouth is
   indistinguishable from a smile.

**Impact** The `lips_pucker` button produces a dead mapping; `kiss` (only
reachable if the name is written directly into the DB) is really just
"not smiling".

**Fix direction** — rename the metric to match the UI action (or vice versa)
and give the pucker its own metric (e.g. lip width vs. lip height ratio, or
the upper/lower inner-lip distance), not a copy of the smile metric.

---

### BUG-003 · S1 · `eyebrows_frown` has no metric at all

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** UI `gui/main.py:689`, AI `available_motions` `gui/main.py:193`,
metric table `gui/main.py:1269-1280`.

**Problem** `eyebrows_frown` is selectable and offered to the LLM, but no
`eyebrows_frown` metric is ever computed, so it can never fire.

**Fix direction** — add a brow-down metric (e.g. brow-to-brow distance, or the
inverse of the existing `eyebrows_up` measurement) or drop the action.

---

### BUG-004 · S1 · Default threshold `0.05` breaks every gesture

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** schema default `database/db_manager.py:37`, dispatch logic
`gui/main.py:1292-1295`, all `save_mapping` callers that omit `threshold`
(`gui/main.py:349-353`, `gui/main.py:836-840`).

**Problem**
A single `threshold` column is reused with **opposite polarity** depending on
the gesture, but every metric is a *normalised distance* (order 0.01–0.15), so
the fixed default of `0.05` is meaningless for most of them.

Simulated values for a typical frontal face in a 640×480 frame (see
[Appendix A](#appendix-a--verification-notes)):

| metric | ~value | code rule | effective behaviour |
| --- | --- | --- | --- |
| `smile` | 0.094 | `> 0.05` | **always active** → key held down permanently |
| `cheek_puff` | 0.131 | `> 0.05` | **always active** |
| `left_eye_blink` | 0.021 | `< 0.05` | **always active with the eye open** (inverted) |
| `right_eye_blink` | 0.021 | `< 0.05` | **always active with the eye open** (inverted) |
| `mouth_open` | 0.017 | `> 0.05` | only a very wide mouth triggers it |
| `eyebrows_up` | 0.027 | `> 0.05` | never fires |
| `jaw_left` / `jaw_right` | 0.086 | `< 0.05` | never fires |
| `nose_scrunch` | 0.088 | `< 0.05` | never fires |

**Impact** With the shipped default only `mouth_open` is usable; three
gestures are *permanently* active (the mapped key is held down at all times)
and five never fire. The values scale with how much of the frame the face
fills, so the behaviour also changes when the user moves closer/further from
the camera.

**Fix direction** — store per-gesture defaults derived from the actual metric
scale, give each gesture an explicit direction flag instead of inferring it
from a hardcoded list, and make the threshold user-editable (blocked by
BUG-009).

---

### BUG-005 · S1 · Head-roll → mouse X axis is inverted

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:1198-1222` (and the horizontal mirror at
`gui/main.py:1179`).

**Problem**

```python
left_face  = face_landmarks.landmark[234]
right_face = face_landmarks.landmark[454]
roll_tilt  = right_face.y - left_face.y
...
move_x = sign_x * (excess_x * 500 * sens_val)
```

In MediaPipe's canonical face model, 234 is the **subject's right** cheek and
454 the **subject's left** cheek. The frame is horizontally flipped before
processing, so the subject's left cheek sits on the left of the processed
image. Tilting the head to the user's left lowers the left cheek → 454.y
increases → `roll_tilt > 0` → `move_x > 0` → **the cursor moves right while the
user tilts left**.

The pitch axis (`gui/main.py:1207-1209`) is consistent; only roll is flipped.

**Fix direction** — swap the sign (or the 234/454 assignment) and verify with
a physical left/right tilt test.

---

### BUG-006 · S1 · Pressed keys are never released

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:1283-1307` (gesture block), `gui/main.py:1183`
(face-detected guard), `gui/main.py:882-889` (`refresh_active_mappings`).

**Problem**
Key release happens only inside the `if results and results.multi_face_landmarks:`
block, and `self.pressed_keys` is only mutated there.

Consequences:

1. **Face lost** (user looks away, camera stalls, `results` empty) → the
   gesture block is skipped entirely → any key that was held stays held
   indefinitely.
2. **Profile switch / mapping edit** → `refresh_active_mappings()` clears
   `active_mappings` but never releases the keys in `self.pressed_keys`, so the
   old key stays physically down.
3. **Two motions → same key** → the first motion to deactivate releases the
   key even though the second motion is still active.

**Fix direction** — release everything in `pressed_keys` whenever the face is
lost, whenever `active_mappings` is rebuilt, and at window close; ideally
track the key→action ownership so a shared key is only released when no
action still claims it.

---

## B. Review window / GUI structure

### BUG-007 · S2 · `ProfileReviewWindow` is defined twice

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:387` (first definition) and `gui/main.py:440`
(second definition).

**Problem** The second class shadows the first at import time; the first one
(≈50 lines: `__init__`, `_build_ui`, `delete_entry`) is unreachable dead code
and the two implementations disagree about behaviour.

**Fix direction** — delete the first definition.

---

### BUG-008 · S2 · `enable_edit` / `save_and_lock` reference non-existent widgets

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** `gui/main.py:581-635`.

**Problem**
`load_data` (`gui/main.py:495-579`) only creates a label, a non-interactive key
badge and a delete button. It never populates `self.row_widgets` (it only ever
calls `self.row_widgets.clear()` at `gui/main.py:501`) and `self.btn_lock` is
never created. Therefore:

- `enable_edit` → `KeyError` on `self.row_widgets[mapping_id]`
  (`gui/main.py:585`);
- `save_and_lock` → `AttributeError` on `self.btn_lock`
  (`gui/main.py:612`).

**Fix direction** — implement the widgets these methods expect, or remove both
methods (see BUG-009).

---

### BUG-009 · S2 · Editing keys/thresholds is not implemented

**Status** `fixed` in batch 2 — see [Appendix D](#appendix-d--batch-2-resolution-log).

**Location** `gui/main.py:495-579` (read-only rendering), README
"Εμφάνιση Καταχωρημένων — review, **edit** or delete saved mappings".

**Problem** The README promises editing, but the review window is read-only
plus delete. Combined with BUG-004 this means **the user has no way to correct
a broken threshold**, and the `threshold` column can only ever hold the
default `0.05`.

**Fix direction** — add a key dropdown + threshold entry per row, wire them to
`DBManager.update_mapping`, and persist the values.

---

### BUG-010 · S3 · Review-window header does not align with the rows

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** header `gui/main.py:535-541`, rows `gui/main.py:552-579`.

**Problem** The header configures columns `0, 1, 2` but places the "Ενέργεια"
label in `column=3`, while the rows place the delete button in `column=2`.

**Fix direction** — use the same column index for the header label and the
row buttons.

---

## C. Persistence (`HorusAccess/database/db_manager.py`)

### BUG-011 · S2 · Sensitivity slider value is never persisted

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:1042` (slider), `gui/main.py:1147-1148`
(`update_sens_label`), `database/db_manager.py:71`
(`update_profile_settings` — never called).

**Problem** The slider only updates the on-screen label. The value *is* read
live at `gui/main.py:1188-1192`, but it is never written to the database, so
it is lost on profile switch (`load_profile_data` resets it to the stored
value) and on restart.

**Fix direction** — call `update_profile_settings` (or a dedicated
`update_sensitivity`) when the slider settles.

---

### BUG-012 · S2 · Game/app name is never stored or displayed

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:356-357` (`db.update_profile_name`),
`gui/main.py:461-466` (`db.get_profile_name`, `parent.profile_games`),
`database/db_manager.py` (no such methods).

**Problem** The GUI probes for `update_profile_name` / `get_profile_name` with
`hasattr`, but `DBManager` implements neither, and `SmartControllerApp` has no
`profile_games` attribute. The `hasattr` guards therefore silently disable the
feature: the profile is always titled "Προφίλ N" and the game name is lost
after the Horus AI picks it.

**Fix direction** — add the two methods (the `profiles.name` column already
exists) or store the name in the `settings` table.

---

### BUG-013 · S3 · `INSERT OR REPLACE` + `AUTOINCREMENT` changes row ids

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `database/db_manager.py:83-86`.

**Problem** `save_mapping` uses `INSERT OR REPLACE` against
`UNIQUE(profile_id, action)`. SQLite implements that as *delete + insert*, so
re-saving an existing motion allocates a **new** `id`. Any UI already holding
the old id (e.g. the delete button lambda captured in
`gui/main.py:577`) will delete nothing.

**Fix direction** — use `INSERT ... ON CONFLICT(profile_id, action) DO UPDATE
SET mapped_key=..., threshold=...` so the row id is stable.

---

### BUG-014 · S3 · Connections are opened but never closed

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `database/db_manager.py:12-14` and every `with self._get_connection()`
usage.

**Problem** `sqlite3.Connection.__exit__` commits/rolls back the transaction
but does **not** close the connection. A new connection is created for every
single query (profiles, mappings, settings are each queried in their own
`with` block).

**Fix direction** — close explicitly (`contextlib.closing`) or keep one
long-lived connection.

---

## D. Horus AI (`HorusAccess/gui/main.py`)

### BUG-015 · S2 · LLM output is not validated

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:256-262` (parse), `gui/main.py:345-353` (save).

**Problem** The prompt restricts the model to `available_motions` and
`allowed_keys`, but the parsed result is persisted verbatim. The model may
return a motion with no metric (`head_tilt`, `tongue_out`, …) or a key that
does not exist; such a mapping is stored, shown in the UI as valid, and then
silently does nothing at runtime.

**Fix direction** — filter/validate each item against the allowed lists before
saving, and drop (or report) invalid entries.

---

### BUG-016 · S2 · Malformed LLM reply raises `KeyError` in a Tk callback

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:335` (`m['motion']`, `m['key']`), `gui/main.py:349-352`.

**Problem** The dialog assumes every item is a dict with `motion` and `key`
keys. A reply missing either key raises `KeyError` inside the Tk event
loop → traceback on stderr, half-built dialog, no user-facing error.

**Fix direction** — validate the shape of each item before rendering/saving
(same place as BUG-015).

---

### BUG-017 · S2 · Target-profile fallback silently overwrites profile 1

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:294-301`.

**Problem**

```python
target_profile = 1
for p_id in range(1, 6):
    existing = self.parent.db.get_mappings(p_id)
    if not existing:
        target_profile = p_id
        break
```

If all five profiles already have mappings, the loop never breaks and
`target_profile` stays `1`, so the AI's mappings are written over profile 1
without any warning.

**Fix direction** — detect "no free profile" explicitly and ask the user which
profile to overwrite (or refuse).

---

### BUG-018 · S2 · Ollama call blocks the Tk main thread

**Location** `gui/main.py:241-251`.

**Problem** `ollama.chat()` is a synchronous network call that can take
10–60 s on a local model. The Tk event loop is blocked for the whole time, so
the app appears frozen and the window stops repainting.

**Fix direction** — run the call in a worker thread and marshal the result back
to the Tk thread.

---

### BUG-019 · S4 · Browser branch is unreachable dead code

**Location** `gui/main.py:188`, `gui/main.py:197-199`, `gui/main.py:272-278`.

**Problem** `is_valid_game` already rejects anything matching
`opera/chrome/edge/firefox/browser` (`core/game_detector.py:59`), so no browser
can reach `select_game`. The browser-specific instructions, allowed-key list
and fallback mappings can never run.

**Fix direction** — remove the branch, or keep it but relax the detector rule
if browsers are genuinely meant to be supported.

---

## E. Game detection (`HorusAccess/core/game_detector.py`)

### BUG-020 · S2 · Quoted `Exec=` paths containing spaces break detection

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:68-79` (`_first_exec_token`),
`core/game_detector.py:82-96` (`_is_launchable_command`).

**Problem** `_first_exec_token` splits on whitespace with no quote handling.
Verified:

```
'"/opt/My Game/run.sh" %F'  -> first token '"/opt/My'  -> launchable: False
```

Quoting is *mandatory* in desktop entries for paths containing spaces, so a
large class of Linux games is dropped silently.

**Fix direction** — parse the `Exec=` line with `shlex.split()` (desktop-entry
spec quoting) instead of `str.split()`.

---

### BUG-021 · S2 · `is_valid_game` blacklist rejects valid games

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:25-31` (keyword list),
`core/game_detector.py:49-59` (substring match).

**Problem** The filter is a plain substring match over the whole title. Verified
rejections: `is_valid_game("Code Vein") -> False` (matches `"code"`). Other
risky entries: `"proton"`, `"node"`, `"office"`, `"word"`, `"tools"`,
`"setup"`, `"admin..."`.

**Fix direction** — match on whole words / word boundaries, or restrict the
blacklist to the launcher/system-app directories rather than the title text.

---

### BUG-022 · S2 · One unreadable directory aborts *all* game detection

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:539-550` (`detect_installed_games`),
call sites `core/game_detector.py:251` (`os.listdir`),
`core/game_detector.py:496` (`os.listdir`), catch-all in
`gui/main.py:94-98`.

**Problem** There is no per-detector error isolation. If a single
`os.listdir` (permission denied, broken symlink, racing uninstall) raises, the
whole `detect_installed_games()` raises; the GUI's catch-all turns it into an
empty list and the user is shown **zero** games even though Steam/Epic/GOG
detection succeeded.

**Fix direction** — wrap each detector in its own `try/except` and log the
failure, so one bad source cannot hide all the others.

---

### BUG-023 · S3 · `_is_launchable_command` has false positives and negatives

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:82-96`.

**Problem**

- **False positive:** any token ending in `.exe/.sh/.bat/…` is accepted even
  when the file does not exist (verified: `env WINEPREFIX=… /games/game.exe`
  → `True`, file absent).
- **False negative:** a relative path is only accepted if it is in `PATH`
  (`shutil.which`), so `Exec=./launch.sh` next to the `.desktop` file is
  dropped.

**Fix direction** — resolve the token relative to the `.desktop` file's
directory before checking, and verify existence for relative paths.

---

### BUG-024 · S3 · Windows GOG registry enumeration aborts on the first error

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:326-344`.

**Problem** The inner `try/except OSError: break` wraps `EnumKey`,
`OpenKey` *and* `QueryValueEx`. A subkey that simply lacks `gameName`
terminates the enumeration, so the remaining GOG games are never seen.

**Fix direction** — catch the error per subkey and `continue` instead of
`break`.

---

### BUG-025 · S3 · `_parse_goggame` regex fallback is unreachable in one case

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:302-315`.

**Problem** When the file parses as JSON but has no `"name"` key, the function
returns `None` immediately and never tries the regex fallback below it.

**Fix direction** — fall through to the regex when the parsed object has no
usable name.

---

### BUG-026 · S4 · Detected game order is nondeterministic

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/game_detector.py:539-550` (uses `glob`/`os.listdir` order).

**Problem** `glob` and `os.listdir` return entries in filesystem order, so the
game grid re-orders between runs and between machines.

**Fix direction** — sort the final result by title (or platform + title).

---

## F. Input backend (`HorusAccess/core/input_backend.py`)

### BUG-027 · S2 · pynput silently swallows key names outside the alias table

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/input_backend.py:84-110` (`_PYNPUT_SPECIAL_KEYS`),
`core/input_backend.py:113-119` (`_to_pynput_key`),
`core/input_backend.py:235-240` / `:252-257` (swallowed exception).

**Problem** `_to_pynput_key` only knows the names in `_PYNPUT_SPECIAL_KEYS`.
For any other multi-character name (`f1`–`f12`, `insert`, `num_lock`,
`print_screen`, …) it returns the raw string. pynput's `Controller._resolve`
raises `ValueError` for strings whose length ≠ 1, and `key_down`/`key_up`
swallow it with `except Exception: pass`. The key is **silently never
pressed** — no log, no error.

**Fix direction** — extend the alias table (or map from pynput's `Key`
members), and log instead of silently swallowing unknown keys.

---

### BUG-028 · S3 · Key-name mismatch between backends

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/input_backend.py:84-110`, `core/input_backend.py:124-133`
(`_KEY_ALIASES`).

**Problem** The app speaks "pydirectinput key names", but the pyautogui path
(Linux fallback and macOS) uses X11/Quartz names. Verified against
`pyautogui.KEYBOARD_KEYS`: `page_up` / `page_down` are **not** valid (pyautogui
uses `pageup` / `pagedown`), and pyautogui's X11 `_keyDown` returns silently
for unknown keys — no exception, no effect. `_KEY_ALIASES` does not cover
this case.

**Fix direction** — extend the alias tables per backend so the logical key
name resolves on every driver.

---

### BUG-029 · S3 · Alias tables are inconsistent across backends

**Location** `core/input_backend.py:84-133`.

**Problem** The same logical key has different spellings depending on the
platform (`esc`/`escape`, `enter`/`return`), and the tables are applied at
different stages. A mapping stored as `escape` behaves differently on Linux
and Windows; `esc` is the reverse. Because the DB stores whatever string the
user/LLM produced, the same saved profile can work on one OS and silently do
nothing on another.

**Fix direction** — normalise to one internal name at write time
(`DBManager.save_mapping`) and translate only at injection time.

---

### BUG-030 · S4 · `disable_failsafe` early-returns even when pyautogui became the driver

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `core/input_backend.py:162-171`, `core/input_backend.py:64-77`.

**Problem** On Linux the function returns immediately when
`_linux_driver == "pynput"`. But if the pynput *keyboard* import failed, the
code sets `_driver = pyautogui` (`:74-75`) while `_linux_driver` stays
`"pynput"`, so pyautogui is the keyboard driver with its failsafe still armed.

**Fix direction** — disable the failsafe on whichever driver is actually used
for input.

---

## G. Application / runtime

### BUG-031 · S2 · Game detection, image downloads and the LLM all run on the Tk thread

**Location** `gui/main.py:84` (detection in `__init__`),
`gui/main.py:124-128` + `gui/main.py:33-65` (HTTP per game card),
`gui/main.py:241-251` (Ollama).

**Problem** All three block the event loop: the game scan walks every Steam
library, GOG tree and desktop folder; each card performs up to two HTTP
requests with 3 s timeouts (Steam CDN + Steam store search API); the LLM call
blocks for tens of seconds. The window appears frozen the whole time.

**Fix direction** — move detection and image loading to a worker thread and
populate the grid incrementally; keep the LLM call off the UI thread
(BUG-018).

---

### BUG-032 · S3 · A new `CTkImage` is allocated every frame

**Location** `gui/main.py:1312-1315`.

**Problem** At ~66 fps a fresh `CTkImage` (and the underlying Tk `PhotoImage`)
is created and assigned each iteration, producing constant allocation/GC churn
and needless ImageTk work.

**Fix direction** — reuse a single `CTkImage` and update its contents, or
reduce the loop rate.

---

### BUG-033 · S3 · `sys.path` is manipulated after the `core.*` imports

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:14-25` (imports), `gui/main.py:27`
(`sys.path.append`).

**Problem** The `sys.path` fix-up runs *after* `from core.input_backend import …`
and `from core.game_detector import …`. It only works because the Makefile
sets `PYTHONPATH=HorusAccess` (`Makefile:56`); running
`python HorusAccess/gui/main.py` directly raises `ModuleNotFoundError`.

**Fix direction** — move the path setup above the imports, or use relative
package imports (`from ..core.input_backend import …`).

---

### BUG-034 · S3 · Destroying the selector window can orphan its child dialog

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:69-180` (no `WM_DELETE_WINDOW` handler),
`gui/main.py:308` (child `CTkToplevel`).

**Problem** `show_confirmation_dialog` creates a `CTkToplevel` whose parent is
the selector window. Tk does not destroy child *toplevels* when the parent
toplevel is destroyed, so closing the selector with the window-manager button
while the confirmation dialog is open leaves the dialog alive on screen.

**Fix direction** — register a `WM_DELETE_WINDOW` handler on the selector that
destroys the child dialog as well.

---

### BUG-035 · S4 · Dead code and unused state

**Location**

| Item | Location |
| --- | --- |
| `smooth_x`, `smooth_y` (never used) | `gui/main.py:933` |
| `dwell_start_time`, `dwell_threshold`, `dwell_duration`, `is_dwelling` | `gui/main.py:936-940` |
| `apply_magnetic_snap`, `get_all_widgets` (never called) | `gui/main.py:1340-1380` |
| `mp_drawing`, `mp_drawing_styles` (no landmark overlay is ever drawn) | `gui/main.py:916-917` |
| `is_recording_motion`, `recorded_landmarks`, `recorded_frames` | `gui/main.py:896-898` |
| `DBManager.update_profile_settings` (never called) | `database/db_manager.py:71` |
| `input_backend.tap_key` (never called) | `core/input_backend.py:262` |
| `input_backend.click` (never called) | `core/input_backend.py:217` |
| first `ProfileReviewWindow` definition | `gui/main.py:387-436` |

**Fix direction** — delete the unused code or finish wiring it up; each entry
is also a maintenance trap (see BUG-007).

---

### BUG-036 · S3 · "left_click must always be mapped" invariant relies on exact string matching

**Status** `fixed` in batch 1 — see [Appendix C](#appendix-c--batch-1-resolution-log).

**Location** `gui/main.py:594-602` (review window guard),
`gui/main.py:825-834` (motion window guard), `core/input_backend.py:137-141`
(`_BUTTON_ALIASES`).

**Problem** Both guards compare the stored key against the literal
`"left_click"`. The Horus AI may legitimately answer `"LEFT_CLICK"` or
`"L. CLICK"`; `normalize_key()` lowercases only at injection time, not in the
database. Such a row satisfies the *runtime* alias but not the *guard*, so the
user is blocked with "Απαιτείται Κλικ" even though left click is mapped —
and, conversely, the invariant can be broken without the app noticing.

**Fix direction** — compare using the same normalisation used at injection
time, or store a canonical key name.

---

## Appendix A — Verification notes

Reproduced locally (Linux, Python 3.12, mediapipe 0.10.21, pynput 3.7,
pyautogui 0.9.54):

1. **pynput rejects multi-character strings** —
   `pynput.keyboard.Controller._resolve` raises `ValueError` when
   `len(key) != 1`; `key_down`/`key_up` catch it with `except Exception: pass`
   → silent no-op (BUG-027).

2. **pyautogui key names** — `pyautogui.KEYBOARD_KEYS` contains `pageup` /
   `pagedown` but **not** `page_up` / `page_down`; on X11,
   `pyautogui._pyautogui_x11._keyDown` returns silently for a key that is not
   in `keyboardMapping` (BUG-028).

3. **Detector helpers** —
   `_first_exec_token('"/opt/My Game/run.sh" %F')` → `'"/opt/My'`;
   `_is_launchable_command(...)` → `False`;
   `_is_launchable_command('env WINEPREFIX=/home/u/.wine /games/game.exe')` →
   `True` although the file does not exist;
   `is_valid_game("Code Vein")` → `False`, `is_valid_game("Sonic Mania")` →
   `True` (BUG-020, BUG-021, BUG-023).

4. **Gesture metric magnitudes** — computed with normalised landmark
   coordinates for a representative frontal face (~220 px wide, 640×480
   frame): `mouth_open` 0.017, `smile`/`kiss` 0.094, `left/right_eye_blink`
   0.021, `eyebrows_up` 0.027, `jaw_left/right` 0.086, `nose_scrunch` 0.088,
   `cheek_puff` 0.131. Applying the current rules with the default threshold
   `0.05` reproduces the table in BUG-004.

5. **DB schema** — the shipped `HorusAccess/database/smart_controller.db`
   matches `db_manager.py` (tables `profiles`, `mappings`, `settings`), with
   `mappings.UNIQUE(profile_id, action)` and
   `mappings.threshold REAL DEFAULT 0.05`. The database file itself is
   `.gitignore`d, so a fresh checkout starts with five empty profiles.

6. **Batch 1 re-check** — the pre-fix results above were reproduced again
   after the fixes, from the fixed code:
   `_first_exec_token('"/opt/My Game/run.sh" %F')` → `/opt/My Game/run.sh`;
   a relative `Exec=./run.sh` next to the `.desktop` file → launchable;
   a missing absolute `*.exe` → rejected;
   `is_valid_game("Code Vein")` → `False` (desktop) / `True`
   (`strict=False`, manifests);
   `normalize_key("page_up", "pynput")` → `page_up` and
   `normalize_key("page_up", "pyautogui")` → `pageup`;
   `_to_pynput_key("f5")` → `Key.f5`, unknown names → `None` + a single logged
   warning. `pyautogui` on macOS is still code-review-only (the local
   environment has no `Quartz`).

## Appendix B — Suggested fix order

> Batch 1 covered the first slice of every group and BUG-014. Batch 2 closed the
> gesture core (BUG-001/002/003/004) and the review-window edit UI
> (BUG-008/009). What is left, in the order it should be tackled:

1. **Responsiveness** — BUG-018 and BUG-031 (worker threads for detection,
   images and Ollama), then BUG-032 (per-frame `CTkImage`).
2. **Input completeness** — BUG-029 (canonical names in storage + migration);
   the `pyautogui-darwin` aliases still need a real macOS check.
3. **Product question** — BUG-019 (keep or remove the browser branch).
4. **Cleanup** — BUG-035, now that BUG-009 has landed.

## Appendix C — Batch 1 resolution log

Implemented on branch `refactor` and committed as `4b96e9f`
(`fix: resolve first batch of 24 logic bugs`). Verification:
`.venv/bin/python -m unittest discover -s tests -v` → **44 tests, all passing**;
`py_compile` clean for the five touched modules. Manual checks are listed at
the end.

**Files**

- `HorusAccess/core/keys.py` *(new)* — canonical key names, per-backend
  `KEY_ALIASES`, `BUTTON_ALIASES`, `canonical_key()`, `normalize_key()`. Imports
  no backend so it stays usable without an X display.
- `HorusAccess/core/input_backend.py` — dispatches through `keys.py`, maps
  pynput `Key` members, logs unsupported keys instead of swallowing them.
- `HorusAccess/core/game_detector.py` — quote-aware `Exec=` parsing, two-tier
  keyword filter, per-detector isolation, GOG parsing/registry fixes, sorting.
- `HorusAccess/database/db_manager.py` — closing connection context manager,
  UPSERT mappings, profile name/sensitivity methods.
- `HorusAccess/gui/main.py` — import order, LLM validation, profile-name
  persistence, key release, roll sign, debounced sensitivity, dialog lifecycle.
- `tests/test_keys.py`, `tests/test_game_detector.py`,
  `tests/test_db_manager.py` *(new)* — stdlib `unittest`.

**Per bug**

| Bug | Change | How it is checked |
| --- | --- | --- |
| BUG-005 | Roll sign inverted (`sign_x = -1 if roll_tilt > 0`), with a comment explaining the horizontal flip. | Needs a physical tilt test (below). |
| BUG-006 | Per-frame `desired_keys` set drives press/release; `_release_all_keys()` runs on face loss, on `refresh_active_mappings()` and in `on_closing()`. Shared keys stay held while any motion claims them. | Code review + forced-face-loss scenario (below). |
| BUG-007 | Duplicate first `ProfileReviewWindow` deleted; the complete implementation is the only one left. | `grep -c "class ProfileReviewWindow"` → 1. |
| BUG-010 | Header "Ενέργεια" moved from column 3 to column 2, matching the row delete button. | Manual layout check (below). |
| BUG-011 | `DBManager.update_profile_sensitivity()` added; slider changes are saved 400 ms after the last move and flushed in `on_closing()`; `load_profile_data()` still restores the stored value. | `test_sensitivity_is_persisted`. |
| BUG-012 | `update_profile_name()` / `get_profile_name()` added. The AI dialog stores the raw game title and the review window shows `Προφίλ N - <game>`; the legacy `Προφίλ N (Game)` form is unwrapped. | `test_profile_name_round_trip`, `test_legacy_profile_name_format_is_unwrapped`. |
| BUG-013 | `INSERT ... ON CONFLICT(profile_id, action) DO UPDATE` keeps the row id; `threshold=None` (the new default) preserves an existing threshold and uses `0.05` for new rows. | `test_saving_an_existing_action_keeps_the_row_id`, `test_threshold_is_preserved_when_omitted`, `test_threshold_can_be_overridden`. |
| BUG-014 | `_connection()` context manager commits/rolls back and always closes; every method uses it instead of `with self._get_connection()`. | Exercised by all DB tests. |
| BUG-015 | `_validate_mappings()` keeps only advertised motions/keys, canonicalises the key, drops duplicates and logs each rejection. It validates against what the prompt advertises (head motions included) so it does not pre-empt BUG-001/004. | Headless probe of `_validate_mappings()`; invalid items are filtered. |
| BUG-016 | Same validator rejects non-dict/short items; the dialog renderer uses `.get()` and the save loop skips incomplete entries. | Probe with garbage list items — no exception. |
| BUG-017 | `target_profile` starts as `None`; when all five profiles are occupied the AI shows a warning and returns instead of overwriting profile 1. | Code review (needs a UI scenario). |
| BUG-020 | `_first_exec_token()` uses `shlex.split(posix=True)` (fallback for unbalanced quotes), drops `%f/%F/%u/%U`, and `_is_launchable_command()` resolves relative paths against the `.desktop` directory. | `ExecTokenTests`, `LinuxDesktopEntryTests`. |
| BUG-021 | Two keyword tiers: `IGNORED_KEYWORDS` always, ambiguous words (`code`, `word`, `tools`, `node`, `setup`) only with `strict=True` and word boundaries. Manifest detectors call `is_valid_game(..., strict=False)`. | `ValidGameTests`; "Code Vein" accepted from manifests, "Visual Studio Code" still rejected. |
| BUG-022 | `_safe_detect()` wraps each detector; one failure is logged and the rest still run. | `DetectAllTests`. |
| BUG-023 | A token is launchable only if the file exists (suffix or `X_OK`); `shutil.which()` is used only for bare command names. Missing absolute paths and bare non-executable files are rejected. | `LaunchableCommandTests`. |
| BUG-024 | GOG registry loop opens each subkey in a `with`, skips a subkey without `gameName`, and increments the index before reading. | Windows-only path, code review. |
| BUG-025 | `_parse_goggame()` parses the JSON once and falls through to the regex when the object has no top-level `name` (or is not a dict). | `GogManifestTests`. |
| BUG-026 | Final list sorted by `title.casefold()`; detector order is fixed (Epic, Steam, GOG, desktop). | `test_result_is_sorted_case_insensitively`. |
| BUG-027 | `_to_pynput_key()` resolves any pynput `Key` member by name (so `f1`–`f20`, `insert`, `num_lock`, `print_screen`, … work) and returns `None` for unknown names; `_log_unsupported()` prints once per backend/key instead of `except Exception: pass`. | `NormalizeKeyTests` + runtime probe (`f5` → `Key.f5`, bogus → `None`). |
| BUG-028 | Backend names come from `_keyboard_backend()` (the backend that actually injects); `keys.py` translates `pageup/pagedown/printscreen/...` for pynput, pyautogui and pyautogui-darwin (`command`/`option`). | `NormalizeKeyTests`. |
| BUG-030 | `disable_failsafe()` iterates `{_driver, _metrics}` and disarms every loaded driver; the early return that trusted `_linux_driver` is gone. | Runtime probe on Linux; import path executes it. |
| BUG-033 | `sys.path` setup moved above the `core.*` / `database.*` imports. | `python HorusAccess/main.py` import order; headless import check. |
| BUG-034 | Selector stores its child dialog in `self._dialog` and registers `WM_DELETE_WINDOW → _on_close()`, which closes the child, releases the grab and destroys itself; the close button calls the same handler. The dialog clears `_dialog` when it closes. | Code review + close-with-dialog-open scenario (below). |
| BUG-036 | Both invariant checks compare through `canonical_key()`, so `Left Click`, `left_click` and legacy spellings all count. | Code review; `canonical_key` tests. |

**Deferred at the end of batch 1** (BUG-001/002/003/004/008/009 have since been
closed by [Appendix D](#appendix-d--batch-2-resolution-log))

- BUG-001/002/003/004 — need a product decision on head-gesture metrics and
  per-gesture thresholds; the fix also changes what users can map.
- BUG-008/009 — the edit UI belongs with BUG-004 (keys/thresholds per gesture).
- BUG-018/031 — need a worker-thread refactor of detection, images and Ollama.
- BUG-019 — whether a browser profile is wanted is a product question.
- BUG-029 — canonical storage plus a migration of existing rows.
- BUG-032 — `CTkImage` reuse/perf work.
- BUG-035 — cleanup depends on BUG-009; BUG-007/011 are now done.

**Manual verification still required**

1. Tilt the head left/right: the cursor should follow the tilt direction.
2. Hold a gesture that presses a key, then cover the face / look away:
   the key must be released (`🔴 [ΑΝΕΝΕΡΓΟ]`).
3. Move the sensitivity slider, switch profiles, restart: the value persists.
4. Fill all five profiles, then run Horus AI: it must warn and save nothing.
5. Stop Ollama or return a malformed reply: no crash, only valid suggestions.
6. Open the confirmation dialog and close the selector: both close, the main
   window becomes clickable again.
7. Check the review-window header alignment and the `Προφίλ N - <game>` title.
8. macOS: pyautogui `command`/`option` mapping is untested here (no `Quartz`).

## Appendix D — Batch 2 resolution log

Implemented on branch `refactor` (not committed yet). Verification:
`.venv/bin/python -m unittest discover -s tests` → **61 tests, all passing**;
`py_compile` clean for the three touched application modules; plus a GUI smoke
run that built both windows against a temporary database, migrated legacy
thresholds, saved an edit, rejected an invalid threshold, exercised the
left-click guard and built all 16 motion buttons. The smoke script is not part
of the suite because it needs a display.

**Product decisions**

- Head gestures use a **calibrated neutral pose**: the first 30 tracked frames
  are averaged, all four head metrics are deviations from that pose, and a
  "🎯 Επαναφορά Κέντρου" button starts a new capture.
- Existing profiles get a **one-time migration** of rows whose threshold is
  exactly the old `0.05` default. User-edited values are preserved and a
  `threshold_defaults_v2` settings flag prevents repeat migrations.

**Files**

- `HorusAccess/core/gestures.py` *(new)* — `GESTURES` registry (label, direction,
  per-gesture default), legacy `kiss → lips_pucker` alias, facial metric
  computation, head signals, `HeadPoseTracker` and the shared
  `is_gesture_active()` dispatcher.
- `HorusAccess/gui/main.py` — registry-driven motion/AI lists, head calibration
  UI and dispatch, editable review window, per-gesture defaults on save.
- `HorusAccess/database/db_manager.py` — `migrate_legacy_thresholds()` and the
  `default_threshold` argument on `save_mapping()`.
- `tests/test_gestures.py` *(new)* — registry, aliases, metric values, pucker
  distinctness, head directions, calibration/reset.
- `tests/test_db_manager.py` — per-gesture inserts and one-time migration.

**Per bug**

| Bug | Change | How it is checked |
| --- | --- | --- |
| BUG-001 | Head yaw/pitch/roll are normalised by face size and turned into `head_up/down/left/right` (plus `head_roll`) deviations from the captured neutral pose. Calibration returns zero metrics until complete. | `HeadPoseTests`; GUI smoke shows the reset control. |
| BUG-002 | The canonical action is `lips_pucker`; legacy `kiss` rows are aliased to it in the registry, dispatcher and threshold migration. The pucker has its own shape metric (`outer lip height / lip width`), not the smile distance. | `test_legacy_kiss_is_the_pucker`, `test_pucker_is_not_a_copy_of_the_smile`, `test_smile_and_pucker_can_be_told_apart`. |
| BUG-003 | `eyebrows_frown` is computed from the same brow-to-eye height as `eyebrows_up` but with the opposite direction, so it fires when the brows drop instead of being permanently open. | `test_metric_values`, `test_direction_of_each_gesture`. |
| BUG-004 | Every gesture declares its own direction and default threshold in the registry. New mappings use that default, old exact-`0.05` rows are migrated once, and the review window lets the user tune each value. | DB tests, GUI smoke, `RegistryTests`. |
| BUG-008 | Rows now populate `row_widgets`; `btn_lock` exists; `_apply_lock_state()` updates every row and button; `enable_edit()` focuses the row's threshold field. | GUI smoke: save → lock → unlock, widgets change state. |
| BUG-009 | Each review row has a key dropdown, threshold entry, edit shortcut and delete button. `save_and_lock()` validates all rows before writing, accepts comma decimals, enforces `0 < threshold ≤ 1`, and refreshes the live dispatcher. | GUI smoke: edit persisted and invalid value rejected without a write. |

**Related hardening**

- The left-click invariant now only blocks removing/changing the *last*
  `left_click` binding. Previously, deleting any row from a profile that never
  had a click binding was refused, which also made the new edit UI unusable on
  such profiles.
- The motion picker, review window and AI prompt all derive their motion names
  from the registry, so `nose_scrunch`, `cheek_puff` and `head_roll` are no
  longer hidden capabilities.

**Manual verification still required**

1. Start tracking and keep the head neutral for ~0.5 s: the sidebar shows
   "✅ Κέντρο κεφαλιού καταγράφηκε"; move only the head to check each direction
   and the roll gesture, then press "Επαναφορά Κέντρου" and repeat.
2. Check the new defaults in real lighting/camera distance, especially
   `smile` (0.11), `lips_pucker` (0.28) and `eyebrows_frown` (0.022); tune them
   in the review window if needed.
3. Open a profile saved before this batch: its exact-`0.05` thresholds should
   change to the per-gesture defaults once, while a deliberately edited value
   stays.
4. Review window: edit a key and a threshold, save/lock, unlock, delete a row,
   and confirm the live key presses follow immediately.
5. Try to change/delete the last `L. CLICK` mapping: it must warn, while a
   profile without any click binding can still have its other rows edited and
   deleted.
