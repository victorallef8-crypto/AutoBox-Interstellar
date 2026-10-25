"""Espera por aproximacao: nao troca de box durante uma viagem longa."""
import unittest
from unittest.mock import Mock
import test_collection_recovery as recovery

class TargetTests(unittest.TestCase):
    def setUp(self):
        recovery.RecoveryTests.setUp(self)
        self.bot.region = {"left": 0, "top": 0, "width": 1000, "height": 600}
        self.bot._screen_capture.return_value = (object(), {"left": 0, "top": 0})
        self.bot.threshold = .9
        self.target = (900, 300)
        self.sample = object()
        self.bot._track_box = Mock(return_value=self.target)

    def wait(self):
        return self.bot._reward_wait(None, object(), {"left": 0, "top": 0},
                                     900, sample=self.sample,
                                     target=self.target, region=dict(self.bot.region))

    def test_long_approach_does_not_end_at_original_timeout(self):
        self.bot._track_box.side_effect = lambda *args: (max(500, 900 - self.clock.now * 80), 300)
        self.ns["reward_notice_visible"].side_effect = lambda *args: self.clock.now >= 4
        self.assertEqual(self.wait(), "confirmed")
        self.assertGreater(self.clock.now, 3.9)
        self.assertLess(self.clock.now, 4.3)
        self.mouse.click.assert_not_called()

    def test_stationary_target_does_not_extend_wait(self):
        self.assertEqual(self.wait(), "timeout")
        self.assertLess(self.clock.now, 1.3)

    def test_lost_target_does_not_wait_forever(self):
        self.bot._track_box.side_effect = lambda *args: ((800, 300) if self.clock.now < .8 else None)
        self.assertEqual(self.wait(), "timeout")
        self.assertLess(self.clock.now, 2.5)

    def test_motion_away_from_ship_does_not_extend_wait(self):
        self.bot._track_box.side_effect = lambda *args: (900 + self.clock.now * 40, 300)
        self.assertEqual(self.wait(), "timeout")
        self.assertLess(self.clock.now, 1.3)

    def test_oscillation_does_not_extend_wait_forever(self):
        self.bot._track_box.side_effect = lambda *args: (880 if int(self.clock.now * 4) % 2 else 900, 300)
        self.assertEqual(self.wait(), "timeout")
        self.assertLess(self.clock.now, 2)

    def test_absolute_deadline_limits_continuous_progress(self):
        self.bot.region["width"] = 200000
        self.target = (190000, 300)
        self.bot._track_box.side_effect = lambda *args: (190000 - self.clock.now * 50, 300)
        self.assertEqual(self.wait(), "timeout")
        self.assertGreaterEqual(self.clock.now, 30)
        self.assertLess(self.clock.now, 30.3)

    def test_pause_during_extended_trip_interrupts(self):
        self.bot._track_box.side_effect = lambda *args: (900 - self.clock.now * 80, 300)
        def pause_after_two(seconds):
            self.clock.sleep(seconds)
            if self.clock.now > 2:
                self.bot.running = False
        self.bot._sleep_interruptible = pause_after_two
        self.assertEqual(self.wait(), "interrupted")
        self.assertGreater(self.clock.now, 2)
        self.mouse.click.assert_not_called()

    def test_departed_box_near_ship_releases_before_full_wait(self):
        self.bot.wait_seconds = 5
        self.bot._track_box.side_effect = lambda *args: ((max(500, 900 - self.clock.now * 200), 300)
                                                       if self.clock.now < 2.2 else None)
        self.assertEqual(self.wait(), "unconfirmed")
        self.assertGreater(self.clock.now, 2.5)
        self.assertLess(self.clock.now, 3.8)
        self.mouse.click.assert_not_called()

    def test_departure_far_from_ship_does_not_release_early(self):
        self.bot.wait_seconds = 5
        self.bot._track_box.side_effect = lambda *args: ((850, 300) if self.clock.now < .8 else None)
        self.assertEqual(self.wait(), "timeout")
        self.assertGreater(self.clock.now, 5)
        self.assertLess(self.clock.now, 6)

    def test_single_missed_detection_near_ship_does_not_release(self):
        self.bot.wait_seconds = 2
        self.target = (530, 300)
        self.bot._track_box.side_effect = lambda *args: (None if self.clock.now < .3 else (530, 300))
        self.assertEqual(self.wait(), "timeout")
        self.assertGreaterEqual(self.clock.now, 2)

    def test_reward_during_departure_grace_is_still_confirmed(self):
        self.bot.wait_seconds = 5
        self.target = (530, 300)
        self.bot._track_box.return_value = None
        self.ns["reward_notice_visible"].side_effect = lambda *args: self.clock.now >= .7
        self.assertEqual(self.wait(), "confirmed")
        self.assertLess(self.clock.now, 1.1)

    def test_reappearing_target_cancels_early_departure(self):
        self.bot.wait_seconds = 2
        self.target = (530, 300)
        self.bot._track_box.side_effect = lambda *args: (None if self.clock.now < .7 else (530, 300))
        self.assertEqual(self.wait(), "timeout")
        self.assertGreaterEqual(self.clock.now, 2)

    def test_calibrated_notice_path_also_releases_departed_target(self):
        self.bot.wait_seconds = 5
        self.target = (530, 300)
        self.bot.notice_region = {"left": 0}
        self.bot._screen_area = Mock(return_value=Mock())
        self.bot._track_box.return_value = None
        self.assertEqual(self.wait(), "unconfirmed")
        self.assertLess(self.clock.now, 1.3)

    def krypton(self):
        self.bot.profile_id = "krypton"
        self.bot.ship_region = {"left": 480, "top": 280, "width": 40, "height": 40}
        self.bot.wait_seconds = 5
        self.bot._click_current_box = Mock(
            side_effect=lambda sct, sample, region, target:
                (*target, .95, object(), {"left": 0, "top": 0}))

    def test_krypton_stall_retries_same_target_before_original_timeout(self):
        self.krypton()
        self.assertEqual(self.wait(), "timeout")
        calls = self.bot._click_current_box.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.args[3] == self.target for call in calls))
        statuses = [data for kind, data in self.bot.events.queue if kind == "status"]
        self.assertTrue(any("Retomando o mesmo box" in status for status in statuses))

    def test_krypton_keeps_flying_without_repeated_clicks(self):
        self.krypton()
        self.bot._track_box.side_effect = lambda *args: (
            (max(500, 900 - self.clock.now * 100), 300) if self.clock.now < 4.2 else None)
        self.assertEqual(self.wait(), "unconfirmed")
        self.bot._click_current_box.assert_not_called()

    def test_krypton_does_not_retry_over_ship_center(self):
        self.krypton()
        self.target = (530, 300)
        self.bot._track_box.return_value = self.target
        self.assertEqual(self.wait(), "timeout")
        self.bot._click_current_box.assert_not_called()

    def test_krypton_lost_or_ambiguous_target_is_not_reclicked(self):
        self.krypton()
        self.bot._track_box.return_value = None
        self.assertEqual(self.wait(), "timeout")
        self.bot._click_current_box.assert_not_called()

    def test_krypton_reward_prevents_retry(self):
        self.krypton()
        self.bot.notice_region = {"left": 0}
        self.bot._screen_area = Mock(return_value=Mock())
        self.ns["new_reward_message"].side_effect = lambda *args: self.clock.now >= .9
        self.assertEqual(self.wait(), "confirmed")
        self.bot._click_current_box.assert_not_called()

    def test_krypton_failed_revalidation_does_not_extend_deadline(self):
        self.krypton()
        self.bot._click_current_box.return_value = None
        self.bot._click_current_box.side_effect = None
        self.assertEqual(self.wait(), "timeout")
        self.assertLess(self.clock.now, 5.3)
        self.assertLessEqual(self.bot._click_current_box.call_count, 4)

    def test_krypton_retry_uses_latest_position_not_original_click(self):
        self.krypton()
        self.bot._track_box.return_value = (800, 300)
        self.assertEqual(self.wait(), "timeout")
        self.assertTrue(all(call.args[3] == (800, 300)
                            for call in self.bot._click_current_box.call_args_list))

    def test_krypton_departure_uses_marked_ship_not_map_center(self):
        self.krypton()
        self.bot.ship_region = {"left": 120, "top": 80, "width": 40, "height": 40}
        self.target = (200, 100)
        self.bot._track_box.return_value = None
        self.assertEqual(self.wait(), "unconfirmed")
        self.assertLess(self.clock.now, 1.3)
        self.bot._click_current_box.assert_not_called()

    def test_large_ship_area_does_not_force_full_wait_after_departure(self):
        self.krypton()
        self.bot.ship_region = {"left": 420, "top": 220, "width": 160, "height": 160}
        self.target = (610, 300)
        self.bot._track_box.return_value = None
        self.assertEqual(self.wait(), "unconfirmed")
        self.assertLess(self.clock.now, 1.3)

    def test_tracker_follows_nearest_not_highest_confidence(self):
        del self.bot._track_box
        self.bot._screen_area = Mock(return_value=object())
        self.ns["locate_boxes"] = Mock(return_value=[(130, 90, .99), (85, 90, .91)])
        # Crop begins (810, 210). Nearest is (895, 300), other is (940, 300).
        result = self.bot._track_box(object(), {}, self.sample, self.bot.region, (900, 300))
        self.assertEqual(result, (895, 300))

    def test_tracker_rejects_ambiguous_neighbors(self):
        del self.bot._track_box
        self.bot._screen_area = Mock(return_value=object())
        self.ns["locate_boxes"] = Mock(return_value=[(75, 90, .99), (105, 90, .99)])
        self.assertIsNone(self.bot._track_box(object(), {}, self.sample, self.bot.region, (900, 300)))

    def test_tracker_does_not_follow_distant_other_box(self):
        del self.bot._track_box
        self.bot._screen_area = Mock(return_value=object())
        self.ns["locate_boxes"] = Mock(return_value=[(165, 90, .99)])
        self.assertIsNone(self.bot._track_box(object(), {}, self.sample, self.bot.region, (900, 300)))

if __name__ == "__main__":
    unittest.main()
