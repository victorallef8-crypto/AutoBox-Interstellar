"""Sessao dedicada simulada: nenhum navegador real ou mouse do Windows e usado."""
import ast
import contextlib
import os
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
nodes = [n for n in tree.body if
         (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "GAME_URL" for t in n.targets))
         or (isinstance(n, ast.ClassDef) and n.name == "BrowserSession")]
ns = dict(Path=Path, queue=queue, threading=threading, os=os)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
BrowserSession = ns["BrowserSession"]

class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.mouse = SimpleNamespace(click=Mock())
        self.closed = False
        self.threads = []
    def goto(self, url, **kwargs):
        self.url = url
    def is_closed(self):
        return self.closed
    def screenshot(self, **kwargs):
        self.threads.append(threading.get_ident())
        return b"fake-png"
    def wait_for_timeout(self, milliseconds):
        time.sleep(.001)

class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4])
        self.page = FakePage()
        self.context = SimpleNamespace(pages=[self.page], close=Mock())
        self.launch = Mock(return_value=self.context)
        self.factory = Mock()
        self.factory.return_value.__enter__ = Mock(
            return_value=SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=self.launch)))
        self.factory.return_value.__exit__ = Mock(return_value=False)
        self.session = BrowserSession(Path(self.temp.name) / "isolated",
                                      {"width": 1280, "height": 720}, factory=self.factory)
        self.session.start("opera-gx.exe")
        self.assertTrue(self.session.ready.wait(2))
    def tearDown(self):
        self.session.close()
        self.temp.cleanup()

    def test_opera_uses_own_profile_and_fixed_viewport(self):
        args = self.launch.call_args.kwargs
        self.assertEqual(args["executable_path"], "opera-gx.exe")
        self.assertTrue(args["user_data_dir"].endswith("isolated"))
        self.assertEqual(args["viewport"], {"width": 1280, "height": 720})
        self.assertEqual(args["device_scale_factor"], 1)
        self.assertFalse(args["headless"])
        self.assertTrue(args["chromium_sandbox"])

    def test_capture_returns_browser_pixels(self):
        self.assertEqual(self.session.request("screenshot"), b"fake-png")
        self.assertNotEqual(self.page.threads[0], threading.get_ident())

    def test_click_uses_page_mouse_with_viewport_coordinates(self):
        self.assertTrue(self.session.request("click", (120, 240), allowed=lambda: True))
        self.page.mouse.click.assert_called_once_with(120, 240, button="left", delay=40)

    def test_paused_bot_does_not_send_queued_click(self):
        self.assertFalse(self.session.request("click", (120, 240), allowed=lambda: False))
        self.page.mouse.click.assert_not_called()

    def test_expired_request_is_not_executed_later(self):
        reply = queue.Queue()
        cancelled = threading.Event()
        cancelled.set()
        self.session.jobs.put(("click", (120, 240), lambda: True, reply, cancelled))
        self.session.request("screenshot")
        self.assertFalse(reply.get(timeout=1)[0])
        self.page.mouse.click.assert_not_called()

    def test_offsite_navigation_blocks_clicks(self):
        self.page.url = "https://example.com/"
        with self.assertRaisesRegex(RuntimeError, "pagina de jogo"):
            self.session.request("click", (120, 240))
        self.page.mouse.click.assert_not_called()

    def test_outside_viewport_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "fora"):
            self.session.request("click", (1280, 200))
        self.page.mouse.click.assert_not_called()

    def test_close_ends_session_and_browser(self):
        self.session.close()
        self.assertTrue(self.session.closed.wait(1))
        self.assertFalse(self.session.ready.is_set())
        self.context.close.assert_called_once()

    def test_screenshot_failure_is_reported(self):
        self.page.screenshot = Mock(side_effect=RuntimeError("capture failed"))
        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            self.session.request("screenshot")

    def test_capture_does_not_use_global_mouse(self):
        # O servico depende apenas do objeto page, sem importar PyAutoGUI.
        names = {n.id for n in ast.walk(next(n for n in nodes if isinstance(n, ast.ClassDef)))
                 if isinstance(n, ast.Name)}
        self.assertNotIn("pyautogui", names)
        self.assertNotIn("send_windows_click", names)

class BackgroundInputTests(unittest.TestCase):
    def setUp(self):
        original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BackgroundApp")
        methods = [n for n in original.body if isinstance(n, ast.FunctionDef)
                   and n.name in ("_ready_to_click", "_game_click", "_capture_context")]
        cls = ast.ClassDef(name="Panel", bases=[], keywords=[], body=methods, decorator_list=[])
        scope = dict(contextlib=contextlib)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                     str(source), "exec"), scope)
        self.app = scope["Panel"]()
        self.app.state_lock = threading.Lock()
        self.app.running = True
        self.app.stopped = False
        self.app.session = SimpleNamespace(ready=threading.Event(), request=Mock(return_value=True))
        self.app.session.ready.set()

    def test_foreground_window_not_required(self):
        self.assertTrue(self.app._ready_to_click())
        self.assertTrue(self.app._game_click(10, 20))
        self.assertEqual(self.app.session.request.call_args.args, ("click", (10, 20)))

    def test_pause_blocks_click(self):
        self.app.running = False
        self.assertFalse(self.app._game_click(10, 20))
        self.app.session.request.assert_not_called()

    def test_missing_browser_blocks_click(self):
        self.app.session.ready.clear()
        self.assertFalse(self.app._game_click(10, 20))
        self.app.session.request.assert_not_called()

    def test_background_context_does_not_open_screen_capture(self):
        with self.app._capture_context() as capture:
            self.assertIsNone(capture)

if __name__ == "__main__":
    unittest.main()
