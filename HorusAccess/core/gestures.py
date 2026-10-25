"""Face-gesture registry, metric computation and head-pose calibration.

Every gesture the application can advertise is declared exactly once here. The
dispatcher, the motion picker, the Horus AI prompt and the database threshold
migration all read this registry, so a motion can never be offered in one place
and silently ignored in another.

The module is deliberately dependency-free (no MediaPipe, no GUI): the landmark
objects only need ``x``/``y`` attributes, which keeps it importable and testable
in a headless environment.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GestureSpec:
    """Everything the rest of the app needs to know about one gesture."""

    name: str
    label: str
    short_label: str
    direction: str  # "above" or "below" the stored threshold
    default_threshold: float


# Insertion order is the order shown in the UI.
GESTURES = {
    "mouth_open": GestureSpec(
        "mouth_open", "Στόμα Ανοιχτό 😮", "Στόμα Ανοιχτό", "above", 0.05,
    ),
    "smile": GestureSpec(
        "smile", "Χαμόγελο 😊", "Χαμόγελο", "above", 0.11,
    ),
    "left_eye_blink": GestureSpec(
        "left_eye_blink", "Αριστερό Βλέφαρο 👁️", "Αριστερό Βλέφαρο", "below", 0.012,
    ),
    "right_eye_blink": GestureSpec(
        "right_eye_blink", "Δεξί Βλέφαρο 👁️", "Δεξί Βλέφαρο", "below", 0.012,
    ),
    "eyebrows_up": GestureSpec(
        "eyebrows_up", "Φρύδια Πάνω 😲", "Φρύδια Πάνω", "above", 0.035,
    ),
    "eyebrows_frown": GestureSpec(
        "eyebrows_frown", "Συνοφρύωση 😠", "Συνοφρύωση", "below", 0.022,
    ),
    "jaw_left": GestureSpec(
        "jaw_left", "Σαγόνι Αριστερά 👈", "Σαγόνι Αριστερά", "below", 0.07,
    ),
    "jaw_right": GestureSpec(
        "jaw_right", "Σαγόνι Δεξιά 👉", "Σαγόνι Δεξιά", "below", 0.07,
    ),
    "lips_pucker": GestureSpec(
        "lips_pucker", "Χείλη Μπροστά (O) 😗", "Χείλη Μπροστά (O)", "above", 0.28,
    ),
    "nose_scrunch": GestureSpec(
        "nose_scrunch", "Σούφρωμα Μύτης 🐽", "Σούφρωμα Μύτης", "below", 0.07,
    ),
    "cheek_puff": GestureSpec(
        "cheek_puff", "Φούσκωμα Μάγουλων 😤", "Φούσκωμα Μάγουλων", "above", 0.15,
    ),
    "head_up": GestureSpec(
        "head_up", "Κεφάλι Πάνω ⬆️", "Κεφάλι Πάνω", "above", 0.06,
    ),
    "head_down": GestureSpec(
        "head_down", "Κεφάλι Κάτω ⬇️", "Κεφάλι Κάτω", "above", 0.06,
    ),
    "head_left": GestureSpec(
        "head_left", "Κεφάλι Αριστερά ⬅️", "Κεφάλι Αριστερά", "above", 0.06,
    ),
    "head_right": GestureSpec(
        "head_right", "Κεφάλι Δεξιά ➡️", "Κεφάλι Δεξιά", "above", 0.06,
    ),
    "head_roll": GestureSpec(
        "head_roll", "Κλίση Κεφαλιού 🔄", "Κλίση Κεφαλιού", "above", 0.12,
    ),
}

# Legacy action names found in older databases.
_ALIASES = {
    "kiss": "lips_pucker",
}

# The facial metrics computed from the raw landmark coordinates. Head metrics
# are supplied separately by HeadPoseTracker because they need a neutral pose.
_FACIAL_METRICS = (
    "mouth_open",
    "smile",
    "left_eye_blink",
    "right_eye_blink",
    "eyebrows_up",
    "eyebrows_frown",
    "jaw_left",
    "jaw_right",
    "lips_pucker",
    "nose_scrunch",
    "cheek_puff",
)


def canonical_motion(name):
    """Returns the registry name for a stored action, or ``None``."""
    if name is None:
        return None
    key = str(name).strip().lower()
    if not key:
        return None
    key = _ALIASES.get(key, key)
    return key if key in GESTURES else None


def default_threshold(action):
    """Returns the per-gesture default, or ``None`` for an unknown action."""
    name = canonical_motion(action)
    if name is None:
        return None
    return GESTURES[name].default_threshold


def default_thresholds():
    """All defaults plus legacy aliases, for the one-time DB migration."""
    defaults = {name: spec.default_threshold for name, spec in GESTURES.items()}
    for alias, name in _ALIASES.items():
        defaults[alias] = GESTURES[name].default_threshold
    return defaults


def display_name(action):
    """Human-readable label for the UI (falls back to the raw action)."""
    name = canonical_motion(action)
    if name is None:
        return str(action)
    return GESTURES[name].label


def short_display_name(action):
    """Label without the emoji, used for the compact motion buttons."""
    name = canonical_motion(action)
    if name is None:
        return str(action)
    return GESTURES[name].short_label


def is_gesture_active(action, value, threshold=None):
    """Applies the gesture's direction to a metric value."""
    name = canonical_motion(action)
    if name is None or value is None:
        return False

    spec = GESTURES[name]
    if threshold is None:
        threshold = spec.default_threshold
    try:
        threshold = float(threshold)
        value = float(value)
    except (TypeError, ValueError):
        return False

    if spec.direction == "below":
        return value < threshold
    return value > threshold


def _distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def compute_facial_metrics(landmarks):
    """Computes every facial gesture metric from a MediaPipe landmark list.

    Distances are normalised landmark distances, the same unit the stored
    thresholds use. ``lips_pucker`` is a shape ratio (lip height / lip width)
    instead of a copy of the smile width, so smiling and puckering are
    distinguishable.
    """
    eyebrow_height = (
        _distance(landmarks[105], landmarks[159])
        + _distance(landmarks[336], landmarks[386])
    ) / 2.0
    lip_width = max(_distance(landmarks[61], landmarks[291]), 1e-6)
    lip_height = _distance(landmarks[0], landmarks[17])

    metrics = {
        "mouth_open": _distance(landmarks[13], landmarks[14]),
        "smile": _distance(landmarks[61], landmarks[291]),
        "left_eye_blink": _distance(landmarks[159], landmarks[145]),
        "right_eye_blink": _distance(landmarks[386], landmarks[374]),
        "eyebrows_up": eyebrow_height,
        # The inverse measurement: lowered brows shrink the brow-to-eye gap.
        "eyebrows_frown": eyebrow_height,
        "jaw_left": _distance(landmarks[152], landmarks[132]),
        "jaw_right": _distance(landmarks[152], landmarks[361]),
        "lips_pucker": lip_height / lip_width,
        "nose_scrunch": _distance(landmarks[1], landmarks[13]),
        "cheek_puff": _distance(landmarks[50], landmarks[280]),
    }
    return {name: metrics[name] for name in _FACIAL_METRICS}


def head_signals(landmarks):
    """Returns scale-normalised yaw/pitch/roll signals for a face.

    The frame is already horizontally mirrored before MediaPipe sees it, so a
    positive yaw means the user turned their head to their right.
    """
    nose = landmarks[1]
    left_cheek = landmarks[234]
    right_cheek = landmarks[454]
    top = landmarks[10]
    bottom = landmarks[152]

    face_width = max(_distance(left_cheek, right_cheek), 1e-6)
    face_height = max(_distance(top, bottom), 1e-6)
    centre_x = (left_cheek.x + right_cheek.x) / 2.0
    centre_y = (top.y + bottom.y) / 2.0

    return {
        "yaw": (nose.x - centre_x) / face_width,
        "pitch": (nose.y - centre_y) / face_height,
        "roll": (right_cheek.y - left_cheek.y) / face_width,
    }


def head_metrics(signals, neutral):
    """Converts raw head signals into positive-only directional metrics."""
    return {
        "head_up": neutral["pitch"] - signals["pitch"],
        "head_down": signals["pitch"] - neutral["pitch"],
        "head_left": neutral["yaw"] - signals["yaw"],
        "head_right": signals["yaw"] - neutral["yaw"],
        "head_roll": abs(signals["roll"] - neutral["roll"]),
    }


class HeadPoseTracker:
    """Captures the user's neutral head pose and reports deviations from it.

    The first ``calibration_frames`` frames are averaged into the neutral pose.
    Until that completes all head metrics are zero, so no head key can fire
    during calibration. ``reset()`` starts a new capture (the UI exposes it as
    a "reset centre" action).
    """

    HEAD_METRICS = ("head_up", "head_down", "head_left", "head_right", "head_roll")

    def __init__(self, calibration_frames=30):
        self.calibration_frames = max(1, int(calibration_frames))
        self.reset()

    def reset(self):
        self._samples = []
        self._neutral = None

    @property
    def is_calibrated(self):
        return self._neutral is not None

    @property
    def sample_count(self):
        return len(self._samples)

    def update(self, landmarks):
        """Feeds one frame and returns the head metrics for it."""
        signals = head_signals(landmarks)

        if self._neutral is None:
            self._samples.append(signals)
            if len(self._samples) >= self.calibration_frames:
                self._neutral = self._average(self._samples)
            return self._empty_metrics()

        return head_metrics(signals, self._neutral)

    def _empty_metrics(self):
        return {name: 0.0 for name in self.HEAD_METRICS}

    @staticmethod
    def _average(samples):
        count = float(len(samples))
        return {
            axis: sum(sample[axis] for sample in samples) / count
            for axis in ("yaw", "pitch", "roll")
        }
