"""Regressoes de clique durante movimento, sem controlar o mouse real."""
import ast
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AutoBoxApp")
methods = [n for n in app.body if isinstance(n, ast.FunctionDef)
           and n.name in ("_click_current_box", "_patrol_wait", "_game_click", "_ship_area_valid", "_ship_center", "_box_allowed")]

class ClickTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.mouse = SimpleNamespace(moveTo=Mock(), click=Mock())
        self.detector = Mock()
        self.ns = dict(pyautogui=self.mouse, locate_boxes=self.detector,
                       time=SimpleNamespace(monotonic=lambda: self.now),
                       radiation_visible=Mock(return_value=False),
                       find_death_panel=Mock(return_value=None))
        cls = ast.ClassDef(name="App", bases=[], keywords=[], body=methods, decorator_list=[])
        exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])),
                     str(source), "exec"), self.ns)
        self.bot = self.ns["App"]()
        self.bot.profile_id = "interstellar"
        self.bot.click_hold = 0
        self.bot.coordinator = None
        self.bot.region = {"left": 100, "top": 200, "width": 500, "height": 400}
        self.bot.threshold = .9
        self.bot.patrol_seconds = 7
        self.bot.events = queue.Queue()
        self.active = True
        self.bot._ready_to_click = lambda: self.active
        self.bot._sleep_interruptible = self.sleep
        self.frame = object()
        self.monitor = {"left": 0, "top": 0}
        self.bot._screen_capture = Mock(return_value=(self.frame, self.monitor))
        self.bot._screen_area = Mock(return_value=object())

    def sleep(self, seconds):
        self.now += seconds

    def click(self, target=(200, 200)):
        return self.bot._click_current_box(None, object(), dict(self.bot.region), target)

    def test_click_uses_updated_position_and_fresh_reward_baseline(self):
        # Local crop starts at (140, 140). Old target is (200, 200).
        self.detector.side_effect = [[(70, 60, .95)], [(72, 61, .96)]]
        result = self.click()
        self.mouse.moveTo.assert_not_called()
        self.mouse.click.assert_called_once_with(312, 401)
        self.assertEqual(result[:3], (212, 201, .96))
        self.assertIs(result[3], self.frame)
        self.assertIs(result[4], self.monitor)

    def test_moving_box_is_clicked_at_latest_position(self):
        self.detector.side_effect = [[(60, 60, .95)], [(80, 70, .95)]]
        result = self.click()
        self.mouse.click.assert_called_once_with(320, 410)
        self.mouse.moveTo.assert_not_called()
        self.assertEqual(self.now, 0)
        self.assertEqual(result[:2], (220, 210))

    def test_target_jump_beyond_tracking_radius_is_not_clicked(self):
        self.detector.side_effect = [[(60, 60, .95)], [(110, 60, .95)]]
        self.assertIsNone(self.click())
        self.mouse.click.assert_not_called()

    def test_disappearing_box_is_not_clicked(self):
        self.detector.side_effect = [[(60, 60, .95)], []]
        self.assertIsNone(self.click())
        self.mouse.click.assert_not_called()

    def test_distant_match_does_not_replace_target(self):
        self.detector.return_value = [(110, 60, .95)]
        self.assertIsNone(self.click())
        self.mouse.moveTo.assert_not_called()
        self.mouse.click.assert_not_called()

    def test_pause_after_first_capture_blocks_click(self):
        def matches(*args, **kwargs):
            self.active = False
            return [(60, 60, .95)]
        self.detector.side_effect = matches
        self.assertIsNone(self.click())
        self.mouse.click.assert_not_called()

    def test_window_lost_after_final_capture_blocks_click(self):
        self.detector.side_effect = [[(60, 60, .95)], [(60, 60, .95)]]
        def crop(*args):
            if self.bot._screen_area.call_count == 2:
                self.active = False
            return object()
        self.bot._screen_area.side_effect = crop
        self.assertIsNone(self.click())
        self.mouse.click.assert_not_called()

    def test_radiation_and_death_block_click(self):
        for name, value in (("radiation_visible", True), ("find_death_panel", (1, 2, 3, 4))):
            with self.subTest(name=name):
                self.ns[name].return_value = value
                self.assertIsNone(self.click())
                self.mouse.click.assert_not_called()
                self.ns[name].return_value = False if name == "radiation_visible" else None

    def test_region_outside_monitor_blocks_click(self):
        self.bot._screen_area.return_value = None
        self.assertIsNone(self.click())
        self.mouse.click.assert_not_called()

    def test_match_near_map_edge_uses_absolute_coordinates(self):
        self.detector.side_effect = [[(8, 12, .95)], [(9, 12, .95)]]
        self.click((8, 12))
        self.mouse.click.assert_called_once_with(109, 212)
        area = self.bot._screen_area.call_args.args[2]
        self.assertEqual(area["left"], 100)
        self.assertEqual(area["top"], 200)

    def test_krypton_revalidation_cannot_replace_box_with_ship(self):
        self.bot.profile_id = "krypton"
        self.bot.ship_region = {"left": 300, "top": 380, "width": 40, "height": 40}
        self.detector.side_effect = [[(60, 60, .95)], [(30, 60, .99)]]
        self.assertIsNone(self.click((260, 200)))
        self.mouse.click.assert_not_called()

    def test_krypton_blocks_offcenter_ship_area_before_capture(self):
        self.bot.profile_id = "krypton"
        self.bot.ship_region = {"left": 180, "top": 260, "width": 40, "height": 40}
        self.assertIsNone(self.click((100, 80)))
        self.bot._screen_capture.assert_not_called()
        self.mouse.click.assert_not_called()
        self.assertTrue(self.bot._box_allowed((250, 200), self.bot.region))

    def test_patrol_returns_early_when_box_appears(self):
        self.detector.side_effect = [[], [(80, 90, .95)]]
        self.bot._patrol_wait(None, object())
        self.assertAlmostEqual(self.now, .5)
        self.mouse.click.assert_not_called()

    def test_krypton_patrol_ignores_detection_over_marked_ship(self):
        self.bot.profile_id = "krypton"
        self.bot.ship_region = {"left": 180, "top": 260, "width": 40, "height": 40}
        self.detector.return_value = [(100, 80, .99)]
        self.bot._patrol_wait(None, object())
        self.assertAlmostEqual(self.now, 7)

    def test_patrol_obeys_deadline(self):
        self.detector.return_value = []
        self.bot._patrol_wait(None, object())
        self.assertAlmostEqual(self.now, 7)

if __name__ == "__main__":
    unittest.main()
