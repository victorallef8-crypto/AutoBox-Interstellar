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

    def data_snapshot(self):
        return {"fresh":True,"map":"m","respawn_revision":5,"hp_percent":80,"dead":False,
                "candidates":[{"id":"box","revision":63,"x":300,"y":500}]}

    def test_data_action_uses_current_box_coordinates_and_never_windows_mouse(self):
        self.session.world_feed.navigation_snapshot=Mock(return_value=self.data_snapshot())
        self.page.evaluate=Mock(return_value={"action":"collect"})
        result=self.session.request("data_target",{"map":"m","respawn_revision":5,"id":"box","revision":63,"x":999999})
        self.assertEqual(result["action"],"collect")
        payload=self.page.evaluate.call_args.args[1]
        self.assertEqual((payload["x"],payload["y"]),(300,500))
        self.assertTrue(payload["can_collect"])
        self.session.request("data_target",{"map":"m","respawn_revision":5,"id":"box","revision":63})
        payload=self.page.evaluate.call_args.args[1]
        self.assertFalse(payload["can_collect"])
        self.assertFalse(payload["can_move"])
        self.page.mouse.click.assert_not_called()

    def test_stale_dead_low_health_and_changed_life_block_data_actions(self):
        for field,value in (("fresh",False),("dead",True),("hp_percent",25),("hp_percent",None),("map","other"),("respawn_revision",6)):
            with self.subTest(field=field,value=value):
                data=self.data_snapshot(); data[field]=value
                self.session.world_feed.navigation_snapshot=Mock(return_value=data)
                self.page.evaluate=Mock()
                with self.assertRaises(RuntimeError):
                    self.session.request("data_target",{"map":"m","respawn_revision":5,"id":"box","revision":63})
                self.page.evaluate.assert_not_called()

    def test_changed_box_revision_and_pause_cancel_data_actions(self):
        self.session.world_feed.navigation_snapshot=Mock(return_value=self.data_snapshot())
        self.page.evaluate=Mock()
        self.assertEqual(self.session.request("data_target",{"map":"m","respawn_revision":5,"id":"box","revision":62})["action"],"gone")
        self.assertFalse(self.session.request("data_target",{},allowed=lambda:False))
        self.page.evaluate.assert_not_called()

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

    def test_removed_image_operations_are_rejected(self):
        for operation in ("screenshot","click"):
            with self.assertRaisesRegex(RuntimeError,"desconhecido"):
                self.session.request(operation,(10,20))
        self.page.mouse.click.assert_not_called()

    def test_expired_data_request_is_cancelled(self):
        reply=queue.Queue(); cancelled=threading.Event(); cancelled.set()
        self.session.jobs.put(("data_target",{},lambda:True,reply,cancelled))
        self.assertFalse(reply.get(timeout=1)[0])
        self.page.mouse.click.assert_not_called()

    def test_close_ends_session_and_browser(self):
        self.session.close()
        self.assertTrue(self.session.closed.wait(1))
        self.assertFalse(self.session.ready.is_set())
        self.context.close.assert_called_once()

    def test_capture_does_not_use_global_mouse(self):
        # O servico depende apenas do objeto page, sem importar PyAutoGUI.
        names = {n.id for n in ast.walk(next(n for n in nodes if isinstance(n, ast.ClassDef)))
                 if isinstance(n, ast.Name)}
        self.assertNotIn("pyautogui", names)
        self.assertNotIn("send_windows_click", names)


if __name__=="__main__": unittest.main()
