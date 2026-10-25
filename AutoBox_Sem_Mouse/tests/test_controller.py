import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from controller import CollectionState, track

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.state = CollectionState({"left":480,"top":280,"width":40,"height":40})
    def test_nearest_box_wins_over_confidence(self):
        self.assertEqual(self.state.choose([(550,300,.9),(800,300,.99)],0),(550,300))
    def test_ship_area_is_never_a_target(self):
        self.assertEqual(self.state.choose([(500,300,.99),(550,300,.9)],0),(550,300))
    def test_offcenter_ship_is_used(self):
        state=CollectionState({"left":80,"top":80,"width":40,"height":40})
        self.assertEqual(state.choose([(160,100,.9),(490,300,.99)],0),(160,100))
    def test_tracking_does_not_choose_distant_box(self):
        self.assertIsNone(track([(800,300,.99)],(600,300)))
    def test_ambiguous_tracking_is_rejected(self):
        self.assertIsNone(track([(590,300,.9),(610,300,.99)],(600,300)))
    def test_approach_keeps_current_target(self):
        self.state.acquire((900,300),0); self.state.clicked((900,300),0)
        self.assertEqual(self.state.observe((850,300),.5),"wait")
        self.assertEqual(self.state.observe((800,300),1),"aim")
        self.assertEqual(self.state.target.point,(800,300))
    def test_real_progress_extends_stall_budget(self):
        self.state.acquire((900,300),0)
        self.assertNotEqual(self.state.observe((700,300),5),"failed")
        self.assertNotEqual(self.state.observe((600,300),10),"failed")
    def test_click_is_not_counted_as_progress(self):
        self.state.acquire((900,300),0)
        self.state.clicked((900,300),5)
        self.assertEqual(self.state.observe((900,300),6),"failed")
    def test_six_correction_limit(self):
        self.state.acquire((900,300),0)
        for n in range(6):
            self.state.clicked((900,300),n*.2)
        self.assertEqual(self.state.observe((800,300),2),"wait")
    def test_no_progress_timeout(self):
        self.state.acquire((900,300),0)
        self.assertEqual(self.state.observe((900,300),6),"failed")
    def test_absolute_timeout(self):
        self.state.acquire((900,300),0)
        self.assertEqual(self.state.observe((600,300),30),"failed")
    def test_near_ship_disappearance_releases_quickly(self):
        self.state.acquire((515,300),0)
        self.assertEqual(self.state.observe(None,.2),"wait")
        self.assertEqual(self.state.observe(None,.4),"wait")
        self.assertEqual(self.state.observe(None,.6),"departed")
    def test_disappearance_is_not_confirmation(self):
        self.state.acquire((550,300),0)
        self.state.observe(None,.3)
        self.assertNotEqual(self.state.observe(None,.6),"confirmed")
    def test_distant_disappearance_fails_instead_of_collecting(self):
        self.state.acquire((900,300),0)
        self.assertEqual(self.state.observe(None,3.1),"failed")
    def test_reward_has_priority(self):
        self.state.acquire((900,300),0)
        self.assertEqual(self.state.observe(None,1,reward=True),"confirmed")
    def test_box_beside_ship_is_prioritized_over_far_box(self):
        self.assertEqual(self.state.choose([(513,300,.91),(800,300,.99)],0),(513,300))

    def test_nearest_in_cooldown_does_not_cause_farther_detour(self):
        self.state.acquire((550,300),0); self.state.finish(0,failed=True)
        self.assertIsNone(self.state.choose([(550,300,.99),(850,300,.99)],1))

    def test_disappearance_50_pixels_away_never_releases_as_arrival(self):
        self.state.acquire((550,300),0)
        for now in (.2,.4,.6,.8):
            self.assertEqual(self.state.observe(None,now),"wait")

    def test_prediction_tracks_camera_motion(self):
        self.state.acquire((800,300),0)
        self.state.observe((780,300),.2)
        predicted=self.state.predicted(.4)
        self.assertAlmostEqual(predicted[0],760)
        self.assertEqual(predicted[1],300)

    def test_recent_failure_blocks_only_temporarily(self):
        self.state.acquire((600,300),0); self.state.finish(0,failed=True)
        self.assertIsNone(self.state.choose([(600,300,.99)],1))
        self.assertEqual(self.state.choose([(600,300,.99)],2.1),(600,300))

if __name__=="__main__": unittest.main()
