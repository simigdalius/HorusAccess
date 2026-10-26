"""Minimal sway IPC client used for pointer injection on Wayland.

Wayland has no protocol that lets a client warp the global pointer. XWayland's
XTest implementation only changes XWayland's internal pointer, so pynput and
pyautogui can report a "new" position while the compositor cursor never moves —
which is why head tracking silently does nothing on sway/Wayland.

Sway exposes ``seat - cursor set <x> <y>`` over its IPC socket and that command
does move the real compositor pointer. This module speaks the IPC protocol
directly instead of spawning ``swaymsg`` for every frame.

Only the pieces needed by ``core.input_backend`` are implemented: querying the
active output layout (for the desktop size), setting the cursor position, and
focusing the window the pointer lands on. The last one is needed because
``seat - cursor set`` bypasses sway's input handling, so its
``focus_follows_mouse`` logic never runs for these warps — hovering a window
would otherwise leave the keyboard focus somewhere else entirely.

Sway interprets the arguments of ``seat - cursor set <x> <y>`` as coordinates
inside the root container and normalises them by the root container size before
warping the pointer. The root container covers the whole output layout, so
passing coordinates relative to the layout's top-left corner is exactly what the
command expects — adding the layout origin would push the pointer off the edge
and clamp it there.
"""

import json
import os
import socket
import struct
import threading
import time

_IPC_MAGIC = b"i3-ipc"
_RUN_COMMAND = 0
_GET_OUTPUTS = 3
_GET_TREE = 4
_HEADER_SIZE = 14
_LAYOUT_REFRESH_SECONDS = 5.0
# Walking the whole window tree is much heavier than a cursor command, so the
# parsed tree is shared by the layout and focus checks for a fraction of a
# second. The GUI warps the pointer once per camera frame.
_TREE_CACHE_SECONDS = 0.2


def layout_bounds(outputs):
    """Bounding box of the active outputs as ``(x, y, width, height)``.

    Returns ``None`` when no output is active. Sway's root container uses this
    same box, which is why the app's ``0..width`` coordinate space can be handed
    to ``seat - cursor set`` as-is.
    """
    rects = []
    for output in outputs:
        if not output.get("active"):
            continue
        rect = output.get("rect") or {}
        if rect.get("width", 0) <= 0 or rect.get("height", 0) <= 0:
            continue
        rects.append(rect)

    if not rects:
        return None

    left = min(rect["x"] for rect in rects)
    top = min(rect["y"] for rect in rects)
    right = max(rect["x"] + rect["width"] for rect in rects)
    bottom = max(rect["y"] + rect["height"] for rect in rects)
    return left, top, right - left, bottom - top


def _contains(rect, x, y):
    """Whether desktop coordinates ``(x, y)`` fall inside ``rect``."""
    width = rect.get("width", 0)
    height = rect.get("height", 0)
    if width <= 0 or height <= 0:
        return False
    return (
        rect.get("x", 0) <= x < rect.get("x", 0) + width
        and rect.get("y", 0) <= y < rect.get("y", 0) + height
    )


def _has_focus(node):
    """Whether ``node`` or any of its descendants is focused."""
    if node.get("focused"):
        return True
    children = list(node.get("nodes") or ()) + list(node.get("floating_nodes") or ())
    return any(_has_focus(child) for child in children)


def _focused_workspace(tree):
    """Workspace container that owns the focus, or ``None``.

    Only the visible workspace can be focused, so this is the workspace the
    pointer is on. Search before using it to find the window under the cursor:
    hidden views of other workspaces keep stale rectangles that overlap the
    visible ones, and focusing one would switch to a workspace the user cannot
    even see.
    """
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.get("type") == "workspace" and _has_focus(node):
            return node
        stack.extend(node.get("nodes") or ())
        stack.extend(node.get("floating_nodes") or ())
    return None


def _window_at(tree, x, y):
    """Window (leaf view) under desktop coordinates ``(x, y)``.

    Containers are skipped because they span the whole workspace; only views
    carry a ``pid``. Floating windows are listed bottom-to-top, so processing
    them after the tiled tree lets the topmost one win when they overlap.
    Searches only the focused workspace, falling back to the whole tree when no
    workspace is marked focused (e.g. an empty one).
    """
    match = None
    stack = [_focused_workspace(tree) or tree]
    while stack:
        node = stack.pop()
        rect = node.get("rect") or {}
        if (
            node.get("pid") is not None
            and node.get("visible", True)
            and _contains(rect, x, y)
        ):
            match = node
        stack.extend(reversed(node.get("floating_nodes") or ()))
        stack.extend(reversed(node.get("nodes") or ()))
    return match


class SwayIPC:
    """Thin, thread-safe sway IPC client for absolute cursor positioning."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("SWAYSOCK")
        if not self.path:
            raise RuntimeError("SWAYSOCK is not set")

        self._lock = threading.Lock()
        self._socket = None
        self._size = (1920, 1080)
        self._origin = (0, 0)
        self._position = None
        self._layout_at = 0.0
        self._tree_data = None
        self._tree_at = 0.0
        self._hovered_id = None

        with self._lock:
            self._connect()
            self._refresh_layout()
            # Start in the middle of the desktop; the real pointer position is
            # not queryable over the sway IPC protocol.
            self._position = (self._size[0] // 2, self._size[1] // 2)

    # -- public API ---------------------------------------------------------

    def size(self):
        """Size of the desktop in the app's coordinate space."""
        with self._lock:
            return self._size

    def origin(self):
        """Top-left corner of the output layout in compositor coordinates."""
        with self._lock:
            return self._origin

    def position(self):
        """Last commanded position.

        Sway does not report the global pointer position, so this is the only
        value available. It is used to seed and re-sync the virtual cursor.
        """
        with self._lock:
            return self._position

    def move(self, x, y):
        """Move the compositor pointer to ``(x, y)`` in the app's coordinate space.

        The window under the new position is focused too, emulating
        ``focus_follows_mouse``: sway only runs that logic for real input
        events, so an IPC warp on its own would leave the focus behind.
        """
        with self._lock:
            self._refresh_layout_if_stale()
            x = max(0, min(self._size[0] - 1, int(x)))
            y = max(0, min(self._size[1] - 1, int(y)))
            self._command(f"seat - cursor set {x} {y}")
            self._position = (x, y)
            self._focus_hovered(x, y)

    def close(self):
        with self._lock:
            self._close()

    # -- IPC plumbing -------------------------------------------------------

    def _connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self.path)
        except Exception:
            sock.close()
            raise
        self._socket = sock

    def _close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _request(self, message_type, payload=b""):
        if self._socket is None:
            self._connect()

        header = _IPC_MAGIC + struct.pack("=II", len(payload), message_type)
        self._socket.sendall(header + payload)

        reply_header = self._recv_exact(_HEADER_SIZE)
        if reply_header[:6] != _IPC_MAGIC:
            raise RuntimeError("unexpected sway IPC reply header")
        length, reply_type = struct.unpack("=II", reply_header[6:])
        body = self._recv_exact(length)
        if reply_type != message_type:
            raise RuntimeError(
                f"unexpected sway IPC reply type {reply_type} (wanted {message_type})"
            )
        return json.loads(body)

    def _recv_exact(self, length):
        chunks = []
        remaining = length
        while remaining:
            chunk = self._socket.recv(remaining)
            if not chunk:
                raise ConnectionError("sway IPC connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _command(self, command):
        payload = command.encode("utf-8")
        try:
            self._request(_RUN_COMMAND, payload)
        except (OSError, ConnectionError, RuntimeError):
            # The compositor may have restarted; reconnect once.
            self._close()
            self._request(_RUN_COMMAND, payload)

    def _tree(self):
        """Cached window tree (``GET_TREE`` reply)."""
        now = time.monotonic()
        if (
            self._tree_data is not None
            and now - self._tree_at < _TREE_CACHE_SECONDS
        ):
            return self._tree_data
        try:
            tree = self._request(_GET_TREE)
        except (OSError, ConnectionError, RuntimeError):
            # The compositor may have restarted; reconnect once.
            self._close()
            tree = self._request(_GET_TREE)
        self._tree_data = tree
        self._tree_at = now
        return tree

    def _focus_hovered(self, x, y):
        """Focus the window the pointer just landed on, or do nothing.

        Only runs when the pointer enters a different window, so it never fights
        a focus change the user made without moving the pointer.
        """
        try:
            tree = self._tree()
            origin_x, origin_y = self._origin
            node = _window_at(tree, x + origin_x, y + origin_y)
        except Exception:
            return
        if node is None:
            # The pointer crossed a gap between windows. Forget the previous id
            # so entering the same window again still focuses it.
            self._hovered_id = None
            return

        node_id = node.get("id")
        if node_id == self._hovered_id:
            return
        self._hovered_id = node_id
        if node.get("focused"):
            return
        try:
            self._command(f"[con_id={node_id}] focus")
        except Exception:
            pass

    def _refresh_layout_if_stale(self):
        if time.monotonic() - self._layout_at < _LAYOUT_REFRESH_SECONDS:
            return
        try:
            self._refresh_layout()
        except Exception:
            # Keep the last known layout instead of failing every frame.
            self._layout_at = time.monotonic()

    def _refresh_layout(self):
        bounds = layout_bounds(self._request(_GET_OUTPUTS))
        if bounds is not None:
            self._origin = (bounds[0], bounds[1])
            self._size = (bounds[2], bounds[3])
            if self._position is not None:
                width, height = self._size
                self._position = (
                    max(0, min(width - 1, self._position[0])),
                    max(0, min(height - 1, self._position[1])),
                )
        self._layout_at = time.monotonic()
