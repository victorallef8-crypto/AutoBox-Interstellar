"""Verifica SendInput com API simulada: nao envia cliques ao computador."""
import ast
import ctypes
import os
import unittest
from pathlib import Path
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "send_windows_click")
ns = dict(ctypes=ctypes, os=os)
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), ns)
send_windows_click = ns["send_windows_click"]

class Sender:
    def __init__(self, results=None):
        self.calls = []
        self.results = iter(results) if results is not None else None
    def __call__(self, count, inputs, size):
        self.calls.append((count, [(inputs[i].mi.dx, inputs[i].mi.dy, inputs[i].mi.dwFlags)
                                  for i in range(count)], size))
        return next(self.results) if self.results is not None else count

class API:
    def __init__(self, results=None, left=0, top=0):
        self.SendInput = Sender(results)
        self.metrics = {76: left, 77: top, 78: 1920, 79: 1080}
    def GetSystemMetrics(self, key):
        return self.metrics[key]

class WindowsClickTests(unittest.TestCase):
    def setUp(self):
        self.api = API()
        self.wait = Mock()
    def click(self, ready=lambda: True, wait=None):
        return send_windows_click(100, 200, .12, ready, wait or self.wait, self.api)

    def test_one_down_and_one_up_with_correct_input_size(self):
        self.assertTrue(self.click())
        down, up = self.api.SendInput.calls
        self.assertEqual(down[0], 2)
        self.assertEqual([item[2] for item in down[1]], [0xC001, 0x0002])
        self.assertEqual(up[1][0][2], 0x0004)
        self.assertEqual(down[2], 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.wait.assert_called_once_with(.12)

    def test_releases_button_when_wait_fails(self):
        with self.assertRaises(RuntimeError):
            self.click(wait=Mock(side_effect=RuntimeError("paused")))
        self.assertEqual(self.api.SendInput.calls[-1][1][0][2], 0x0004)

    def test_blocked_input_reports_failure(self):
        self.api = API(results=[0])
        with self.assertRaisesRegex(OSError, "0/2"):
            self.click()
        self.wait.assert_not_called()

    def test_partial_move_without_press_does_not_report_success(self):
        self.api = API(results=[1])
        with self.assertRaisesRegex(OSError, "1/2"):
            self.click()

    def test_failed_release_reports_failure(self):
        self.api = API(results=[2, 0])
        with self.assertRaisesRegex(OSError, "liberacao"):
            self.click()

    def test_not_ready_sends_no_events(self):
        self.assertFalse(self.click(ready=lambda: False))
        self.assertEqual(self.api.SendInput.calls, [])

    def test_virtual_desktop_negative_coordinates(self):
        self.api = API(left=-1000, top=-500)
        self.assertTrue(send_windows_click(-1000, -500, .1, lambda: True, self.wait, self.api))
        self.assertEqual(self.api.SendInput.calls[0][1][0][:2], (0, 0))

    def test_outside_desktop_is_rejected(self):
        with self.assertRaises(ValueError):
            send_windows_click(-1, 100, .1, lambda: True, self.wait, self.api)
        self.assertEqual(self.api.SendInput.calls, [])

if __name__ == "__main__":
    unittest.main()
