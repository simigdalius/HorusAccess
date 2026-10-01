"""Cross-platform abstraction over mouse/keyboard injection and webcam capture.

Windows uses ``pydirectinput`` (raw Scan Code injection - the only reliable way
to talk to DirectX games) plus ``pyautogui`` for the screen metrics.
Linux and macOS use ``pyautogui`` exclusively, because ``pydirectinput`` is a
Windows-only extension and fails at import time everywhere else.

Nothing outside this module should import ``pydirectinput`` or ``pyautogui``
directly: key names differ between the two backends, so all synthetic input has
to funnel through here.
"""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

if IS_WINDOWS:
    import pydirectinput as _driver
    import pyautogui as _metrics
else:
    import pyautogui as _driver
    _metrics = _driver


# The application always speaks "pydirectinput key names". This table maps them
# onto whatever the active backend expects.
_KEY_ALIASES = {
    "win32": {},
    "linux": {
        "escape": "esc",
    },
    "darwin": {
        "enter": "return",
        "escape": "esc",
    },
}

# Mouse pseudo-keys. The profiles store these alongside real keyboard keys, so
# they have to be routed to the mouse buttons instead of the keyboard.
_BUTTON_ALIASES = {
    "left_click": "left",
    "right_click": "right",
    "middle_click": "middle",
}


def backend_name():
    return "pydirectinput" if IS_WINDOWS else "pyautogui"


def normalize_key(key):
    """Returns the backend-specific name for a logical HorusAccess key."""
    if key is None:
        return None
    name = str(key).strip().lower()
    if not name:
        return None
    return _KEY_ALIASES.get(sys.platform, {}).get(name, name)


def disable_failsafe():
    """Turns off the "corner of screen" emergency stop on every backend."""
    try:
        _driver.FAILSAFE = False
    except Exception:
        pass


def mouse_move(x, y):
    _driver.moveTo(int(x), int(y))


def mouse_position():
    return _metrics.position()


def mouse_down(button="left"):
    _driver.mouseDown(button=button)


def mouse_up(button="left"):
    _driver.mouseUp(button=button)


def click(x=None, y=None):
    if x is not None and y is not None:
        mouse_move(x, y)
    _driver.click()


def key_down(key):
    name = normalize_key(key)
    if not name:
        return
    if name in _BUTTON_ALIASES:
        _driver.mouseDown(button=_BUTTON_ALIASES[name])
        return
    _driver.keyDown(name)


def key_up(key):
    name = normalize_key(key)
    if not name:
        return
    if name in _BUTTON_ALIASES:
        _driver.mouseUp(button=_BUTTON_ALIASES[name])
        return
    _driver.keyUp(name)


def tap_key(key, presses=1, interval=0.05):
    name = normalize_key(key)
    if not name:
        return
    _driver.press(name, presses=presses, interval=interval)


def screen_size():
    return _metrics.size()


def open_webcam(index=0, width=640, height=480):
    """Opens a webcam using the capture backend that exists on this OS.

    ``cv2.CAP_DSHOW`` only exists on Windows; on Linux (V4L2) and macOS (AVFoundation)
    the default backend has to be used instead.
    """
    import cv2

    backends = []
    if IS_WINDOWS:
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY]
    elif IS_LINUX:
        backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
    elif IS_MACOS:
        backends = [cv2.CAP_AVFOUNDATION, cv2.CAP_ANY]

    if not backends:
        backends = [cv2.CAP_ANY]

    cap = None
    for backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            return cap
        cap.release()
        cap = None

    # Last resort: let OpenCV pick whatever it can find.
    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap