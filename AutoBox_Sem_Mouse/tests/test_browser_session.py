import ast
import json
import struct
import queue
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_session import BrowserSession, HOME_URL, GAME_URL
tree=ast.parse((Path(__file__).resolve().parents[1]/"browser_session.py").read_text(encoding="utf-8"))
nodes=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="BrowserSession"]
class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.mouse = SimpleNamespace(click=Mock())
        self.closed = False
        self.handlers = {}
        self.threads = []
        self.metrics = {"width":1280,"height":720,"dpr":1,"offset_x":0,"offset_y":0,"scale":1}
        self.png = b"\x89PNG\r\n\x1a\n" + b"\x00"*8 + struct.pack(">II",1280,720)
    def on(self, name, callback):
        self.handlers[name] = callback
    def goto(self, url, **kwargs):
        self.last_navigation = url
        self.url = url
    def is_closed(self):
        return self.closed
    def screenshot(self, **kwargs):
        self.threads.append(threading.get_ident())
        return self.png
    def evaluate(self, script):
        return dict(self.metrics)
    def wait_for_timeout(self, milliseconds):
        time.sleep(.001)

class BrowserSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4])
        self.page = FakePage()
        self.cdp = SimpleNamespace(on=Mock(),send=Mock())
        self.context = SimpleNamespace(pages=[self.page], close=Mock(),on=Mock(),
                                       new_cdp_session=Mock(return_value=self.cdp))
        self.launch = Mock(return_value=self.context)
        self.factory = Mock()
        self.factory.return_value.__enter__ = Mock(
            return_value=SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=self.launch)))
        self.factory.return_value.__exit__ = Mock(return_value=False)
        self.session = BrowserSession(Path(self.temp.name) / "isolated",
                                      {"width": 1280, "height": 720}, factory=self.factory)
        self.session.start("opera-gx.exe")
        self.assertTrue(self.session.ready.wait(2))
        self.page.url = GAME_URL  # Usuario entra no mapa pela pagina inicial.
        self.session.request("screenshot")
    def tearDown(self):
        self.session.close()
        self.temp.cleanup()

    def test_client_export_reads_scripts_without_queries_or_literal_credentials(self):
        self.page.evaluate=Mock(return_value=[
            {"path":"/play/client.js","source":'const inputChannel="secret-channel";const cfg={"token":"secret-token"};function queueInput(c){return c;}'},
            {"path":"/private.js?token=hidden","source":"private"},
            {"path":"/unavailable.js","error":"unavailable"}])
        result=self.session.request("client_sources")
        self.assertEqual(result["schema"],"autobox-client-integration-v1")
        self.assertEqual(len(result["files"]),1)
        saved=json.dumps(result)
        self.assertNotIn("secret-channel",saved)
        self.assertNotIn("secret-token",saved)
        self.assertNotIn("hidden",saved)
        self.assertIn("queueInput",saved)
        script=self.page.evaluate.call_args.args[0]
        self.assertIn("u.origin===location.origin",script)
        self.assertIn("method:'GET'",script)
        self.assertIn("redirect:'error'",script)
        self.page.mouse.click.assert_not_called()

    def test_client_export_reports_missing_scripts(self):
        self.page.evaluate=Mock(return_value=[])
        with self.assertRaisesRegex(RuntimeError,"Nenhum arquivo JavaScript"):
            self.session.request("client_sources")

    def test_passive_reader_only_enables_network_events(self):
        self.cdp.send.assert_called_once_with("Network.enable")
        callbacks=dict(call.args for call in self.cdp.on.call_args_list)
        self.assertIn("Network.eventSourceMessageReceived",callbacks)
        self.assertIn("Network.requestWillBeSent",callbacks)

    def test_reader_does_not_accept_unrelated_event_sources(self):
        callbacks=dict(call.args for call in self.cdp.on.call_args_list)
        callbacks["Network.requestWillBeSent"]({"requestId":"foreign","request":{"url":"https://example.com/events"}})
        self.assertIsNone(self.session.world_feed.stream)

    def test_selected_game_source_is_bound_and_chat_is_ignored(self):
        callbacks=dict(call.args for call in self.cdp.on.call_args_list)
        callbacks["Network.requestWillBeSent"]({"requestId":"game","request":{"url":"https://interstellar-verse.com/api/events?secret=do-not-store"}})
        self.assertEqual(self.session.world_feed.stream,(id(self.page),"game"))
        callbacks["Network.eventSourceMessageReceived"]({"requestId":"game","eventName":"chat-history","data":"not json"})
        self.assertIsNone(self.session.world_feed.state)
        self.assertNotIn("secret",repr(self.session.get_world_summary()))

    def test_feed_callbacks_accept_full_and_patch_without_sending_commands(self):
        callbacks=dict(call.args for call in self.cdp.on.call_args_list)
        callbacks["Network.requestWillBeSent"]({"requestId":"game","request":{"url":"https://interstellar-verse.com/api/events"}})
        full={"transport":"delta1","epoch":"e","sequence":1,"full":{
            "map":{"id":"m","width":1000,"height":1000,"gates":[]},
            "me":{"mapId":"m","x":100,"y":100},"boxes":[{"id":"b","x":150,"y":100}],"npcs":[]}}
        callbacks["Network.eventSourceMessageReceived"]({"requestId":"game","eventName":"message","data":json.dumps(full)})
        self.assertEqual(self.session.get_world_summary()["nearest"]["distance"],50)
        patch={"transport":"delta1","epoch":"e","sequence":2,"base":1,
               "patch":["o",[["me",["o",[["x",["v",140]]],[]]]],[]]}
        callbacks["Network.eventSourceMessageReceived"]({"requestId":"game","eventName":"message","data":json.dumps(patch)})
        self.assertEqual(self.session.get_world_summary()["nearest"]["distance"],10)
        self.cdp.send.assert_called_once_with("Network.enable")
        self.page.mouse.click.assert_not_called()
        self.page.handlers["close"](self.page)
        self.assertFalse(self.session.get_world_summary()["fresh"])

    def test_opera_uses_own_profile_and_fixed_viewport(self):
        self.assertEqual(self.page.last_navigation,HOME_URL)
        args = self.launch.call_args.kwargs
        self.assertEqual(args["executable_path"], "opera-gx.exe")
        self.assertTrue(args["user_data_dir"].endswith("isolated"))
        self.assertEqual(args["viewport"], {"width": 1280, "height": 720})
        self.assertEqual(args["device_scale_factor"], 1)
        self.assertFalse(args["headless"])
        self.assertTrue(args["chromium_sandbox"])

    def test_capture_returns_browser_pixels(self):
        self.assertEqual(self.session.request("screenshot"), self.page.png)
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

    def test_browser_zoom_33_maps_image_pixels_to_css_pixels(self):
        self.page.metrics.update(width=3840,height=2160,dpr=1/3)
        self.session.request("screenshot")
        self.assertTrue(self.session.request("click",(781,371)))
        self.page.mouse.click.assert_called_once_with(2343,1113,button="left",delay=40)
        self.assertEqual(self.session.last_click["image"],(781,371))
        self.assertEqual(self.session.last_click["css"],(2343,1113))

    def test_zoom_50_and_hidpi_use_actual_image_size(self):
        self.page.metrics.update(width=2560,height=1440,dpr=1)
        self.page.png=b"\x89PNG\r\n\x1a\n"+b"\x00"*8+struct.pack(">II",2560,1440)
        self.session.request("screenshot")
        self.session.request("click",(700,400))
        self.page.mouse.click.assert_called_once_with(700,400,button="left",delay=40)

    def test_minimap_click_uses_the_same_zoom_mapping(self):
        self.page.metrics.update(width=3840,height=2160,dpr=1/3)
        self.session.request("screenshot")
        self.session.request("click",(766,684))
        self.page.mouse.click.assert_called_once_with(2298,2052,button="left",delay=40)

    def test_zoom_changed_after_screenshot_blocks_stale_click(self):
        self.page.metrics.update(width=3840,height=2160,dpr=1/3)
        with self.assertRaisesRegex(RuntimeError,"mudou apos"):
            self.session.request("click",(120,240))
        self.page.mouse.click.assert_not_called()

    def test_wrong_page_cannot_reuse_capture_coordinates(self):
        old=self.context.pages[0]
        new=FakePage(); new.url=old.url
        self.context.pages.append(new)
        with self.assertRaisesRegex(RuntimeError,"Capture a imagem"):
            self.session.request("click",(120,240))
        new.mouse.click.assert_not_called()

    def test_pause_during_geometry_check_still_blocks_click(self):
        count=[0]
        def allowed():
            count[0]+=1
            return count[0]==1
        self.assertFalse(self.session.request("click",(120,240),allowed=allowed))
        self.page.mouse.click.assert_not_called()

    def test_invalid_geometry_does_not_send_click(self):
        self.page.metrics["width"]=float("nan")
        with self.assertRaisesRegex(RuntimeError,"Medidas"):
            self.session.request("click",(120,240))
        self.page.mouse.click.assert_not_called()

    def test_failed_capture_cannot_reuse_old_mapping(self):
        self.page.screenshot=Mock(side_effect=RuntimeError("capture failed"))
        with self.assertRaises(RuntimeError):
            self.session.request("screenshot")
        with self.assertRaisesRegex(RuntimeError,"Capture a imagem"):
            self.session.request("click",(120,240))
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


if __name__=="__main__": unittest.main()
