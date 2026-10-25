"""Testa espera e recuperacao sem abrir o jogo ou mover o mouse."""
import ast
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AutoBoxApp")
methods = [n for n in app.body if isinstance(n, ast.FunctionDef)
           and n.name in ("_reward_wait", "_recover_collection", "_collect_loop", "_track_box")]

class Clock:
    def __init__(self):
        self.now = 0
    def monotonic(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.mouse = SimpleNamespace(click=Mock(), FailSafeException=type("FailSafe", (Exception,), {}))
        self.ns = dict(time=self.clock, pyautogui=self.mouse,
                       reward_notice_visible=Mock(return_value=False),
                       new_reward_message=Mock(return_value=False),
                       radiation_visible=Mock(return_value=False),
                       find_death_panel=Mock(return_value=None))
        cls = ast.ClassDef(name="App", bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                     str(source), "exec"), self.ns)
        self.bot = self.ns["App"]()
        self.bot.events = queue.Queue()
        self.bot.running = True
        self.bot.state_lock = threading.Lock()
        self.bot.notice_region = None
        self.bot.wait_seconds = 1
        self.bot.patrol_seconds = 7
        self.bot._ready_to_click = lambda: self.bot.running
        self.bot._sleep_interruptible = self.clock.sleep
        self.bot._screen_capture = Mock(return_value=(object(), {}))
        self.bot._choose_safe_point = Mock(return_value=(20, 30))

    def wait(self):
        return self.bot._reward_wait(None, object(), {}, 50)

    def test_timeout(self):
        self.assertEqual(self.wait(), "timeout")

    def test_confirmed_reward(self):
        self.ns["reward_notice_visible"].side_effect = [False, False, False, False, True]
        self.assertEqual(self.wait(), "confirmed")

    def test_calibrated_reward_requires_two_frames(self):
        self.bot.notice_region = {"left": 0}
        baseline = Mock()
        self.bot._screen_area = Mock(return_value=baseline)
        self.ns["new_reward_message"].side_effect = [True, False, True, True]
        self.assertEqual(self.wait(), "confirmed")
        self.assertEqual(self.ns["new_reward_message"].call_count, 4)

    def test_pause_during_wait_is_interrupted(self):
        def pause(seconds):
            self.bot.running = False
        self.bot._sleep_interruptible = pause
        self.assertEqual(self.wait(), "interrupted")
        self.bot._screen_capture.assert_not_called()

    def test_radiation_and_death_interrupt(self):
        for name, value in (("radiation_visible", True), ("find_death_panel", (1, 2, 3, 4))):
            with self.subTest(name=name):
                self.ns[name].return_value = value
                self.assertEqual(self.wait(), "interrupted")
                self.ns[name].return_value = False if name == "radiation_visible" else None

    def test_recovery_clicks_only_safe_point(self):
        self.assertTrue(self.bot._recover_collection())
        self.mouse.click.assert_called_once_with(20, 30)
        self.assertEqual(self.clock.now, 7)

    def test_missing_minimap_pauses_without_click(self):
        self.bot._choose_safe_point.return_value = None
        self.assertFalse(self.bot._recover_collection())
        self.assertFalse(self.bot.running)
        self.mouse.click.assert_not_called()
        self.assertIn("Pausado", self.bot.events.get()[1])

    def test_inactive_window_blocks_recovery_click(self):
        self.bot.running = False
        self.assertFalse(self.bot._recover_collection())
        self.mouse.click.assert_not_called()

    def run_loop(self, results, boxes=None):
        self.ns["MAX_COLLECTION_TIMEOUTS"] = 3
        self.ns["TEMPLATE_PATH"] = SimpleNamespace(stat=lambda: SimpleNamespace(st_mtime_ns=1))
        self.ns["cv2"] = SimpleNamespace(imread=lambda _: object())
        context = Mock()
        context.__enter__ = Mock(return_value=None)
        context.__exit__ = Mock(return_value=False)
        self.ns["mss"] = SimpleNamespace(mss=lambda: context)
        frame = Mock()
        frame.shape = (400, 400, 3)
        frame.__getitem__ = Mock(return_value=frame)
        self.bot._screen_capture.return_value = (frame, {"left": 0, "top": 0})
        self.bot.region = {"left": 0, "top": 0, "width": 400, "height": 400}
        self.bot.safe_region = {"left": 0}
        self.bot.threshold = .9
        self.bot.exit_event = threading.Event()
        self.ns["locate_boxes"] = Mock(return_value=boxes if boxes is not None else [
            (50, 50, .99), (150, 50, .99), (250, 50, .99),
            (350, 50, .99), (50, 150, .99), (150, 150, .99)])
        pending = iter(results)
        def reward(*args, **kwargs):
            result = next(pending)
            if result == "stop":
                self.bot.exit_event.set()
                return "interrupted"
            return result
        def click_current(sct, sample, region, target):
            self.mouse.click(region["left"] + target[0], region["top"] + target[1])
            return (*target, .99, frame, {"left": 0, "top": 0})
        self.bot._click_current_box = click_current
        self.bot._reward_wait = reward
        recovery = self.bot._recover_collection
        def recover():
            result = recovery()
            self.bot.exit_event.set()
            return result
        self.bot._recover_collection = Mock(side_effect=recover)
        self.bot._collect_loop()
        statuses = list(self.bot.events.queue)
        self.assertFalse(any(event == "command" for event, _ in statuses), statuses)

    def test_each_selection_uses_ship_center_not_previous_click(self):
        self.run_loop(["confirmed", "stop"], boxes=[
            (210, 200, .99), (160, 200, .91), (260, 200, .99)])
        self.assertEqual([call.args for call in self.mouse.click.call_args_list],
                         [(210, 200), (160, 200)])

    def test_confidence_cannot_override_nearest_distance(self):
        self.run_loop(["stop"], boxes=[(200, 0, .90), (0, 150, .95)])
        self.mouse.click.assert_called_once_with(200, 0)

    def test_equal_distance_uses_confidence_as_tiebreaker(self):
        self.run_loop(["stop"], boxes=[(100, 200, .90), (300, 200, .95)])
        self.mouse.click.assert_called_once_with(300, 200)

    def test_three_timeouts_trigger_one_recovery(self):
        self.run_loop(["timeout", "timeout", "timeout"])
        self.bot._recover_collection.assert_called_once()
        self.assertEqual(self.mouse.click.call_count, 4)

    def test_success_resets_consecutive_failures(self):
        self.run_loop(["timeout", "timeout", "confirmed", "timeout", "timeout", "stop"])
        self.bot._recover_collection.assert_not_called()

    def test_interruption_does_not_count_as_timeout(self):
        self.run_loop(["timeout", "interrupted", "timeout", "stop"])
        self.bot._recover_collection.assert_not_called()

if __name__ == "__main__":
    unittest.main()
