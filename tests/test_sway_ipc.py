import json
import os
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from HorusAccess.core import sway_ipc
from HorusAccess.core.sway_ipc import (
    SwayIPC,
    _focused_workspace,
    _window_at,
    layout_bounds,
)

OUTPUTS = [
    {"active": True, "rect": {"x": 1920, "y": 0, "width": 1920, "height": 1080}},
]

# No rects: used by the movement tests, where the pointer must not focus
# anything (the tree lookup simply finds nothing).
TREE = {
    "focused": False,
    "nodes": [
        {
            "focused": False,
            "nodes": [
                {"focused": False, "pid": 111, "nodes": []},
                {"focused": True, "pid": 4242, "nodes": []},
            ],
        }
    ],
    "floating_nodes": [{"focused": False, "pid": 222, "nodes": []}],
}

HOVER_OUTPUTS = [
    {"active": True, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
]


def hover_tree(focused_id=None):
    """Two tiled views side by side plus stacked floating windows."""

    def view(node_id, pid, rect, visible=True):
        return {
            "id": node_id,
            "pid": pid,
            "focused": node_id == focused_id,
            "visible": visible,
            "rect": rect,
            "nodes": [],
        }

    return {
        "id": 1,
        "focused": False,
        "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
        "nodes": [
            {
                "id": 2,
                "focused": False,
                "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                "nodes": [
                    view(10, 111, {"x": 0, "y": 0, "width": 960, "height": 1080}),
                    view(11, 4242, {"x": 960, "y": 0, "width": 960, "height": 1080}),
                    view(12, 333, {"x": 0, "y": 0, "width": 1920, "height": 1080}, False),
                ],
            }
        ],
        "floating_nodes": [
            view(20, 222, {"x": 100, "y": 100, "width": 300, "height": 200}),
            view(21, 555, {"x": 150, "y": 150, "width": 300, "height": 200}),
        ],
    }


def workspace_tree(focused_workspace=2):
    """Two workspaces whose views share the same rectangle.

    Mirrors the live layout bug: a view on a workspace that is not focused keeps
    a stale rect that overlaps the visible workspace, so only workspace scoping
    can tell them apart.
    """

    def view(node_id, pid):
        return {
            "id": node_id,
            "pid": pid,
            "focused": False,
            "visible": True,
            "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "nodes": [],
        }

    return {
        "id": 1,
        "type": "root",
        "focused": False,
        "nodes": [
            {
                "id": 3,
                "type": "output",
                "focused": False,
                "nodes": [
                    {
                        "id": 5,
                        "type": "workspace",
                        "name": "1",
                        "focused": focused_workspace == 1,
                        "nodes": [view(7, 2064)],
                        "floating_nodes": [],
                    },
                    {
                        "id": 50,
                        "type": "workspace",
                        "name": "2",
                        "focused": False,
                        "nodes": [
                            {
                                "id": 60,
                                "type": "con",
                                "focused": focused_workspace == 2,
                                "ns": "view",
                                "nodes": [view(61, 3430)],
                                "floating_nodes": [],
                            }
                        ],
                        "floating_nodes": [],
                    },
                ],
            }
        ],
    }


class FakeSocket:
    """Responds like sway's IPC socket for the requests we send."""

    def __init__(self, outputs, tree):
        self.outputs = outputs
        self.tree = tree
        self.commands = []
        self.requests = []
        self.path = None
        self._buffer = b""

    def connect(self, path):
        self.path = path

    def close(self):
        pass

    def sendall(self, data):
        assert data[:6] == b"i3-ipc", data[:6]
        length, message_type = struct.unpack("=II", data[6:14])
        payload = data[14:14 + length]
        self.requests.append(message_type)

        if message_type == sway_ipc._GET_OUTPUTS:
            body = json.dumps(self.outputs).encode()
        elif message_type == sway_ipc._GET_TREE:
            body = json.dumps(self.tree).encode()
        elif message_type == sway_ipc._RUN_COMMAND:
            self.commands.append(payload.decode())
            body = b'[{"success": true}]'
        else:
            raise AssertionError(message_type)

        self._buffer = (
            b"i3-ipc" + struct.pack("=II", len(body), message_type) + body
        )

    def recv(self, size):
        chunk, self._buffer = self._buffer[:size], self._buffer[size:]
        return chunk


class LayoutBoundsTests(unittest.TestCase):
    def test_single_output(self):
        self.assertEqual(layout_bounds(OUTPUTS), (1920, 0, 1920, 1080))

    def test_multiple_outputs_use_the_bounding_box(self):
        outputs = [
            {"active": True, "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}},
            {"active": True, "rect": {"x": 1920, "y": 180, "width": 2560, "height": 1440}},
        ]
        self.assertEqual(layout_bounds(outputs), (0, 0, 4480, 1620))

    def test_inactive_outputs_are_ignored(self):
        outputs = [
            {"active": False, "rect": {"x": 0, "y": 0, "width": 800, "height": 600}},
            {"active": True, "rect": {"x": 1920, "y": 0, "width": 1920, "height": 1080}},
        ]
        self.assertEqual(layout_bounds(outputs), (1920, 0, 1920, 1080))

    def test_no_active_output_returns_none(self):
        self.assertIsNone(layout_bounds([]))
        self.assertIsNone(
            layout_bounds([{"active": False, "rect": {"x": 0, "y": 0, "width": 0, "height": 0}}])
        )


class WindowAtTests(unittest.TestCase):
    def test_returns_the_tiled_window_under_the_point(self):
        self.assertEqual(_window_at(hover_tree(), 1500, 500)["id"], 11)
        self.assertEqual(_window_at(hover_tree(), 300, 500)["id"], 10)

    def test_floating_windows_win_over_tiled_ones(self):
        self.assertEqual(_window_at(hover_tree(), 200, 200)["id"], 21)

    def test_topmost_floating_window_wins_when_they_overlap(self):
        tree = hover_tree()
        tree["floating_nodes"][1]["rect"] = {"x": 100, "y": 100, "width": 300, "height": 200}
        self.assertEqual(_window_at(tree, 200, 200)["id"], 21)

    def test_hidden_views_are_ignored(self):
        hidden = {
            "id": 12,
            "pid": 333,
            "focused": False,
            "visible": False,
            "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "nodes": [],
        }
        tree = {
            "id": 1,
            "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "nodes": [
                {
                    "id": 2,
                    "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                    "nodes": [hidden],
                }
            ],
            "floating_nodes": [],
        }
        self.assertIsNone(_window_at(tree, 500, 500))

        hidden["visible"] = True
        self.assertEqual(_window_at(tree, 500, 500)["pid"], 333)

    def test_returns_none_outside_every_window(self):
        self.assertIsNone(_window_at(hover_tree(), 5000, 5000))

    def test_only_the_focused_workspace_is_searched(self):
        # Both views occupy the same rectangle; the unfocused one must not win.
        self.assertEqual(_window_at(workspace_tree(), 500, 500)["id"], 61)
        self.assertEqual(_window_at(workspace_tree(1), 500, 500)["id"], 7)

    def test_falls_back_to_the_whole_tree_without_a_focused_workspace(self):
        tree = workspace_tree(None)
        tree["nodes"][0]["nodes"].pop()
        self.assertEqual(_window_at(tree, 500, 500)["id"], 7)


class FocusedWorkspaceTests(unittest.TestCase):
    def test_finds_the_workspace_of_the_focused_view(self):
        self.assertEqual(_focused_workspace(workspace_tree())["id"], 50)

    def test_finds_a_workspace_that_is_focused_itself(self):
        tree = {
            "id": 1,
            "focused": False,
            "nodes": [
                {"id": 2, "type": "workspace", "focused": True, "nodes": []},
            ],
        }
        self.assertEqual(_focused_workspace(tree)["id"], 2)

    def test_returns_none_when_nothing_is_focused(self):
        self.assertIsNone(_focused_workspace(workspace_tree(None)))
        self.assertIsNone(_focused_workspace(hover_tree()))

    def test_ignores_containers_that_are_not_workspaces(self):
        tree = {
            "id": 1,
            "type": "output",
            "focused": True,
            "nodes": [],
        }
        self.assertIsNone(_focused_workspace(tree))


class SwayIPCTests(unittest.TestCase):
    def make_backend(self, outputs=OUTPUTS, tree=None):
        fake = FakeSocket(outputs, TREE if tree is None else tree)
        with mock.patch.object(sway_ipc.socket, "socket", return_value=fake):
            backend = SwayIPC(path="/tmp/fake-sway.sock")
        return backend, fake

    def test_size_uses_the_output_bounding_box(self):
        backend, _ = self.make_backend()
        self.assertEqual(backend.size(), (1920, 1080))

    def test_origin_is_the_top_left_corner_of_the_layout(self):
        backend, _ = self.make_backend(
            [{"active": True, "rect": {"x": 100, "y": 50, "width": 800, "height": 600}}]
        )
        self.assertEqual(backend.origin(), (100, 50))

    def test_position_starts_at_the_centre(self):
        backend, _ = self.make_backend()
        self.assertEqual(backend.position(), (960, 540))

    def test_move_uses_root_container_coordinates(self):
        backend, fake = self.make_backend()
        backend.move(100, 200)
        self.assertEqual(fake.commands, ["seat - cursor set 100 200"])
        self.assertEqual(backend.position(), (100, 200))

    def test_move_clamps_to_the_desktop(self):
        backend, fake = self.make_backend()
        backend.move(-50, 5000)
        self.assertEqual(fake.commands, ["seat - cursor set 0 1079"])
        self.assertEqual(backend.position(), (0, 1079))

    def test_layout_origin_is_not_added_to_the_command(self):
        backend, fake = self.make_backend(
            [{"active": True, "rect": {"x": 100, "y": 50, "width": 800, "height": 600}}]
        )
        backend.move(10, 20)
        self.assertEqual(fake.commands, ["seat - cursor set 10 20"])
        self.assertEqual(backend.position(), (10, 20))
        self.assertEqual(backend.size(), (800, 600))

    def test_move_focuses_the_window_under_the_pointer(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree())
        backend.move(1500, 500)
        self.assertEqual(
            fake.commands,
            ["seat - cursor set 1500 500", "[con_id=11] focus"],
        )

    def test_move_ignores_overlapping_views_from_other_workspaces(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, workspace_tree())
        backend.move(500, 500)
        self.assertEqual(
            fake.commands,
            ["seat - cursor set 500 500", "[con_id=61] focus"],
        )

    def test_move_does_not_refocus_the_same_window(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree())
        backend.move(1500, 500)
        backend.move(1600, 600)
        self.assertEqual(
            [command for command in fake.commands if command.endswith(" focus")],
            ["[con_id=11] focus"],
        )

    def test_move_focuses_when_the_pointer_enters_another_window(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree())
        backend.move(1500, 500)
        backend.move(300, 500)
        self.assertEqual(
            [command for command in fake.commands if command.endswith(" focus")],
            ["[con_id=11] focus", "[con_id=10] focus"],
        )

    def test_move_refocuses_the_same_window_after_crossing_a_gap(self):
        tree = hover_tree()
        tree["nodes"][0]["nodes"] = tree["nodes"][0]["nodes"][:2]
        tree["nodes"][0]["nodes"][0]["rect"] = {
            "x": 0, "y": 0, "width": 900, "height": 1080,
        }
        tree["nodes"][0]["nodes"][1]["rect"] = {
            "x": 1000, "y": 0, "width": 920, "height": 1080,
        }
        backend, fake = self.make_backend(HOVER_OUTPUTS, tree)
        backend.move(500, 500)
        backend.move(950, 500)  # gap: clears the remembered hover id
        backend.move(500, 500)
        self.assertEqual(
            [command for command in fake.commands if command.endswith(" focus")],
            ["[con_id=10] focus", "[con_id=10] focus"],
        )

    def test_move_skips_focus_when_the_window_already_has_it(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree(focused_id=11))
        backend.move(1500, 500)
        self.assertEqual(fake.commands, ["seat - cursor set 1500 500"])

    def test_tree_is_cached_between_warps(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree())
        with mock.patch.object(sway_ipc.time, "monotonic", return_value=2000.0):
            backend.move(1500, 500)
            backend.move(1600, 500)
        self.assertEqual(fake.requests.count(sway_ipc._GET_TREE), 1)

    def test_tree_is_refreshed_after_the_cache_expires(self):
        backend, fake = self.make_backend(HOVER_OUTPUTS, hover_tree())
        with mock.patch.object(sway_ipc.time, "monotonic", return_value=2000.0):
            backend.move(1500, 500)
        with mock.patch.object(
            sway_ipc.time,
            "monotonic",
            return_value=2000.0 + 2 * sway_ipc._TREE_CACHE_SECONDS,
        ):
            backend.move(1600, 500)
        self.assertEqual(fake.requests.count(sway_ipc._GET_TREE), 2)


if __name__ == "__main__":
    unittest.main()
