"""Cross-platform abstraction over mouse/keyboard injection and webcam capture.

Windows uses ``pydirectinput`` (raw Scan Code injection - the only reliable way
to talk to DirectX games) plus ``pyautogui`` for the screen metrics.
Linux prefers ``pynput`` for mouse/keyboard injection when available (more
reliable than pure XTest), falling back to ``pyautogui`` if it cannot be used.
On sway/Wayland, pointer movement is routed through the compositor's IPC
instead, because Wayland ignores XTest warps (see ``core/sway_ipc.py``).
macOS uses ``pyautogui`` exclusively, because ``pydirectinput`` is a
Windows-only extension and ``pynput`` is not always necessary there.

Nothing outside this module should import backend-specific libraries directly:
key names differ between backends, so all synthetic input has to funnel
through here.
"""

import contextlib
import io
import os
import sys
import threading
import time
from collections import deque

from .keys import BUTTON_ALIASES, normalize_key
from .sway_ipc import SwayIPC

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_WAYLAND = IS_LINUX and bool(os.environ.get("WAYLAND_DISPLAY"))

_driver = None
_metrics = None
_mouse_ctrl = None
_mouse_btn = None
_kb_ctrl = None
_kb_key = None
_kb_code = None
_linux_driver = "pyautogui"
_sway = None
_sway_error_logged = False

# Physical-pointer tracking, only used with the sway backend. XWayland mirrors
# the compositor pointer while it is over an X11 window, so the position can be
# read back and compared with the last position we commanded. Our own warps are
# filtered out that way, which keeps head tracking from mistaking itself for
# the user.
_MOUSE_LOCK = threading.Lock()
_MOUSE_WARP_TOLERANCE = 3
_RECENT_WARPS = deque(maxlen=16)
_mouse_activity = 0
_mouse_observed = None
_mouse_last_seen = None


@contextlib.contextmanager
def _mute_native_warnings():
    """Swallows harmless ``print`` noise emitted by the native X11 bindings.

    python-xlib prints "Xlib.xauth: warning, no xauthority details available"
    directly to stdout when ``~/.Xauthority`` has no entries, which is normal
    on Wayland/XWayland sessions. python-xlib offers no logging hook for it.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield


with _mute_native_warnings():
    if IS_WINDOWS:
        import pydirectinput as _driver
        import pyautogui as _metrics
    elif IS_LINUX:
        # Try pynput first (more reliable for games on X11/Wayland)
        try:
            from pynput import mouse as _pynput_mouse

            _mouse_ctrl = _pynput_mouse.Controller()
            _mouse_btn = _pynput_mouse.Button
            import pyautogui as _metrics  # type: ignore
            _linux_driver = "pynput"
        except Exception:
            import pyautogui as _driver  # type: ignore
            _metrics = _driver
            _linux_driver = "pyautogui"

        if _linux_driver == "pynput":
            # Keyboard via pynput too. If that fails, keep pyautogui as a fallback.
            try:
                from pynput import keyboard as _pynput_keyboard

                _kb_ctrl = _pynput_keyboard.Controller()
                _kb_key = _pynput_keyboard.Key
                _kb_code = _pynput_keyboard.KeyCode
            except Exception:
                _kb_ctrl = None
                try:
                    import pyautogui as _driver  # type: ignore
                except Exception:
                    _driver = None

        # On sway/Wayland, XTest pointer warps never reach the compositor, so
        # movement goes through sway's own IPC command instead. pynput is still
        # initialised above for keyboard/button fallbacks on XWayland clients.
        if IS_WAYLAND and os.environ.get("SWAYSOCK"):
            try:
                _sway = SwayIPC()
            except Exception as exc:
                print(f"⚠️ [input_backend] sway IPC unavailable: {exc}")
    else:  # macOS
        import pyautogui as _driver  # type: ignore
        _metrics = _driver
        _linux_driver = "pyautogui"


def _to_pynput_key(name):
    """Maps a pynput key name to a pynput key object, or ``None``."""
    if _kb_key is not None:
        key = getattr(_kb_key, name, None)
        if key is not None:
            return key
    if _kb_code is not None and len(name) == 1:
        return _kb_code.from_char(name)
    return None


def _keyboard_backend():
    """Name of the backend that actually injects keyboard events."""
    if _kb_ctrl is not None:
        return "pynput"
    if IS_WINDOWS:
        return "pydirectinput"
    if IS_MACOS:
        return "pyautogui-darwin"
    return "pyautogui"


_UNSUPPORTED_KEYS = set()


def _log_unsupported(backend, name, detail=None):
    """Logs a key the backend cannot inject, once per key/backend pair."""
    token = (backend, name)
    if token in _UNSUPPORTED_KEYS:
        return
    _UNSUPPORTED_KEYS.add(token)
    message = f"⚠️ [input_backend] Το πλήκτρο '{name}' δεν υποστηρίζεται από {backend}."
    if detail:
        message += f" ({detail})"
    print(message)


def backend_name():
    if IS_WINDOWS:
        return "pydirectinput"
    if IS_LINUX:
        return f"pyautogui+{_linux_driver}" if _linux_driver == "pynput" else "pyautogui"
    return "pyautogui"


def disable_failsafe():
    """Turns off the "corner of screen" emergency stop on every backend.

    On Linux ``_linux_driver`` can claim "pynput" while pyautogui is the real
    keyboard driver (the pynput keyboard import failed), so every loaded driver
    is disarmed instead of trusting that flag.
    """
    for driver in {_driver, _metrics}:
        if driver is None:
            continue
        try:
            if hasattr(driver, "FAILSAFE"):
                driver.FAILSAFE = False
        except Exception:
            pass


def _pointer_app_position():
    """Live XWayland pointer position in the app's coordinate space.

    Returns ``None`` when no position can be read. XWayland mirrors the
    compositor pointer only while it is over an X11 window (our own window, or
    a game), which is exactly when a physical mouse move matters.
    """
    if _metrics is None or _sway is None:
        return None
    try:
        global_x, global_y = _metrics.position()
        origin_x, origin_y = _sway.origin()
        width, height = _sway.size()
    except Exception:
        return None
    return (
        max(0, min(width - 1, int(global_x) - origin_x)),
        max(0, min(height - 1, int(global_y) - origin_y)),
    )


def _poll_pointer():
    """Counts pointer movement that did not come from our own warp.

    Called right before each injected move, so a physical mouse movement is
    observed before the next warp overwrites it. A pointer that keeps returning
    the same position is over a native Wayland surface (XWayland freezes its
    position there), so it is left alone and head tracking keeps working.
    """
    global _mouse_activity, _mouse_observed, _mouse_last_seen
    position = _pointer_app_position()
    if position is None:
        return
    with _MOUSE_LOCK:
        previous = _mouse_last_seen
        _mouse_last_seen = position
        if previous is None or position == previous:
            return
        for warp_x, warp_y in _RECENT_WARPS:
            if (
                abs(position[0] - warp_x) <= _MOUSE_WARP_TOLERANCE
                and abs(position[1] - warp_y) <= _MOUSE_WARP_TOLERANCE
            ):
                return
        _mouse_observed = position
        _mouse_activity += 1


def _remember_warp(x, y):
    """Records a position we are about to command."""
    global _mouse_observed
    position = (int(x), int(y))
    with _MOUSE_LOCK:
        _RECENT_WARPS.append(position)
        _mouse_observed = position


def mouse_activity_count():
    """Count of physical pointer movements seen so far.

    Only movements that XWayland forwards can be observed, which is enough for
    the app's own (X11) window and for XWayland games. The counter stays at 0
    on X11/Windows/macOS, where this module does not poll for them.
    """
    with _MOUSE_LOCK:
        return _mouse_activity


def mouse_move(x, y):
    global _sway, _sway_error_logged
    if _sway is not None:
        try:
            _poll_pointer()
            width, height = _sway.size()
            target_x = max(0, min(width - 1, int(x)))
            target_y = max(0, min(height - 1, int(y)))
            _remember_warp(target_x, target_y)
            _sway.move(target_x, target_y)
            return
        except Exception as exc:
            if not _sway_error_logged:
                _sway_error_logged = True
                print(f"⚠️ [input_backend] Αποτυχία μετακίνησης μέσω sway: {exc}")
            # Stop using the compositor path and degrade to the X11 backend
            # instead of raising on every frame.
            _sway = None
    if IS_LINUX and _linux_driver == "pynput":
        _mouse_ctrl.position = (int(x), int(y))  # type: ignore
        return
    if _driver is not None:
        _driver.moveTo(int(x), int(y))
        return


def mouse_position():
    if _sway is not None:
        _poll_pointer()
        position = _pointer_app_position()
        if position is not None:
            return position
        with _MOUSE_LOCK:
            if _mouse_observed is not None:
                return _mouse_observed
        return _sway.position()
    if _metrics is not None:
        return _metrics.position()
    return (0, 0)


def mouse_down(button="left"):
    if IS_LINUX and _linux_driver == "pynput":
        btn = {
            "left": _mouse_btn.left,  # type: ignore
            "right": _mouse_btn.right,  # type: ignore
            "middle": _mouse_btn.middle,  # type: ignore
        }.get(button, _mouse_btn.left)  # type: ignore
        _mouse_ctrl.press(btn)  # type: ignore
        return
    if _driver is not None:
        _driver.mouseDown(button=button)
        return


def mouse_up(button="left"):
    if IS_LINUX and _linux_driver == "pynput":
        btn = {
            "left": _mouse_btn.left,  # type: ignore
            "right": _mouse_btn.right,  # type: ignore
            "middle": _mouse_btn.middle,  # type: ignore
        }.get(button, _mouse_btn.left)  # type: ignore
        _mouse_ctrl.release(btn)  # type: ignore
        return
    if _driver is not None:
        _driver.mouseUp(button=button)
        return


def key_down(key):
    backend = _keyboard_backend()
    name = normalize_key(key, backend)
    if not name:
        return
    if name in BUTTON_ALIASES:
        mouse_down(BUTTON_ALIASES[name])
        return
    if _kb_ctrl is not None:
        pynput_key = _to_pynput_key(name)
        if pynput_key is None:
            _log_unsupported(backend, name)
            return
        try:
            _kb_ctrl.press(pynput_key)
        except Exception as exc:
            _log_unsupported(backend, name, exc)
        return
    if _driver is not None:
        try:
            _driver.keyDown(name)
        except Exception as exc:
            _log_unsupported(backend, name, exc)


def key_up(key):
    backend = _keyboard_backend()
    name = normalize_key(key, backend)
    if not name:
        return
    if name in BUTTON_ALIASES:
        mouse_up(BUTTON_ALIASES[name])
        return
    if _kb_ctrl is not None:
        pynput_key = _to_pynput_key(name)
        if pynput_key is None:
            _log_unsupported(backend, name)
            return
        try:
            _kb_ctrl.release(pynput_key)
        except Exception as exc:
            _log_unsupported(backend, name, exc)
        return
    if _driver is not None:
        try:
            _driver.keyUp(name)
        except Exception as exc:
            _log_unsupported(backend, name, exc)


def screen_size():
    if _sway is not None:
        return _sway.size()
    return _metrics.size()


def screen_origin():
    """Top-left of the desktop in the OS's global pointer coordinates.

    Windows and X11 start at ``(0, 0)``. Sway can place its output elsewhere, so
    Tk's root coordinates have to be shifted before they can be compared with
    the app's cursor coordinates.
    """
    if _sway is not None:
        return _sway.origin()
    return (0, 0)


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