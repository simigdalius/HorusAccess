"""Cross-platform abstraction over mouse/keyboard injection and webcam capture.

Windows uses ``pydirectinput`` (raw Scan Code injection - the only reliable way
to talk to DirectX games) plus ``pyautogui`` for the screen metrics.
Linux prefers ``pynput`` for mouse/keyboard injection when available (more
reliable than pure XTest), falling back to ``pyautogui`` if it cannot be used.
macOS uses ``pyautogui`` exclusively, because ``pydirectinput`` is a
Windows-only extension and ``pynput`` is not always necessary there.

Nothing outside this module should import backend-specific libraries directly:
key names differ between backends, so all synthetic input has to funnel
through here.
"""

import contextlib
import io
import sys

from .keys import BUTTON_ALIASES, normalize_key

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

_driver = None
_metrics = None
_mouse_ctrl = None
_mouse_btn = None
_kb_ctrl = None
_kb_key = None
_kb_code = None
_linux_driver = "pyautogui"


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


def mouse_move(x, y):
    if IS_LINUX and _linux_driver == "pynput":
        _mouse_ctrl.position = (int(x), int(y))  # type: ignore
        return
    if _driver is not None:
        _driver.moveTo(int(x), int(y))
        return


def mouse_position():
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


def click(x=None, y=None):
    if x is not None and y is not None:
        mouse_move(x, y)
    if IS_LINUX and _linux_driver == "pynput":
        _mouse_ctrl.click(_mouse_btn.left)  # type: ignore
        return
    if _driver is not None:
        _driver.click()
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


def tap_key(key, presses=1, interval=0.05):
    backend = _keyboard_backend()
    name = normalize_key(key, backend)
    if not name:
        return
    if name in BUTTON_ALIASES:
        for _ in range(presses):
            mouse_down(BUTTON_ALIASES[name])
            mouse_up(BUTTON_ALIASES[name])
        return
    import time
    for i in range(presses):
        key_down(name)
        key_up(name)
        if i < presses - 1:
            time.sleep(interval)


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