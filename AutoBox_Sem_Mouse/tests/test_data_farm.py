import json
import unittest
from copy import deepcopy
from controller import DataFarmPlanner
from browser_session import WorldFeed, ManualCollectProbe

def world():
    return {"fresh":True,"map":"m","position":(100,100),"speed":100,"hp_percent":80,
            "respawn_revision":1,"box_counter":10,"candidates":[
                {"id":"far","revision":1,"x":300,"y":100},{"id":"near","revision":2,"x":130,"y":140}],
            "gates":[{"id":"portal","x":100,"y":100}]}

class FarmPlannerTests(unittest.TestCase):
    def setUp(self): self.planner=DataFarmPlanner(arrival_radius=10)
    def test_nearest_box_by_map_coordinates_not_gate(self):
        plan=self.planner.step(world(),0)
        self.assertEqual(plan["target_id"],"near")
        self.assertEqual(plan["phase"],"approach")
        self.assertEqual(plan["eta"],.5)
    def test_does_not_switch_during_current_collection(self):
        self.planner.step(world(),0)
        updated=world(); updated["candidates"].append({"id":"new","x":101,"y":100})
        self.assertEqual(self.planner.step(updated,.5)["target_id"],"near")
    def test_arrival_does_not_count_as_collection(self):
        self.planner.step(world(),0)
        updated=world(); updated["position"]=(130,140)
        self.assertEqual(self.planner.step(updated,1)["phase"],"collect")
    def test_counter_and_disappearance_after_arrival_confirm(self):
        self.planner.step(world(),0)
        updated=world(); updated["position"]=(130,140)
        self.planner.step(updated,1)
        updated["candidates"]=[updated["candidates"][0]]; updated["box_counter"]=11
        self.assertEqual(self.planner.step(updated,2)["phase"],"confirmed")
        self.assertEqual(self.planner.step(updated,3)["target_id"],"far")
    def test_disappearance_without_reward_is_not_confirmed(self):
        self.planner.step(world(),0)
        updated=world(); updated["candidates"]=[]
        self.assertEqual(self.planner.step(updated,1)["phase"],"unconfirmed")
    def test_revision_change_does_not_follow_respawned_box(self):
        self.planner.step(world(),0)
        updated=world(); updated["candidates"][1]["revision"]=3
        self.assertEqual(self.planner.step(updated,1)["phase"],"unconfirmed")
    def test_missing_live_data_clears_target(self):
        self.planner.step(world(),0)
        self.assertEqual(self.planner.step({"fresh":False},1)["phase"],"paused")
        self.assertIsNone(self.planner.target)
    def test_map_and_respawn_changes_pause(self):
        for field,value in (("map","other"),("respawn_revision",2)):
            self.planner.reset(); self.planner.step(world(),0)
            updated=world(); updated[field]=value
            self.assertEqual(self.planner.step(updated,1)["phase"],"paused")
    def test_stalled_target_is_not_replaced_with_farther_box(self):
        self.planner.step(world(),0)
        self.assertEqual(self.planner.step(world(),8)["phase"],"stalled")
        self.assertEqual(self.planner.target["id"],"near")
    def test_low_hp_takes_priority(self):
        updated=world(); updated["hp_percent"]=20
        self.assertEqual(self.planner.step(updated,0)["phase"],"recover")
        self.assertIsNone(self.planner.target)
    def test_empty_map_searches_without_fabricating_destination(self):
        updated=world(); updated["candidates"]=[]
        result=self.planner.step(updated,0)
        self.assertEqual(result["phase"],"search")
        self.assertNotIn("destination",result)

class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.now=1.
        self.feed=WorldFeed(clock=lambda:self.now)
        self.feed.begin("s")
        self.full={"transport":"delta1","epoch":"e","sequence":1,"full":{
            "map":{"id":"m","width":1000,"height":1000,"gates":[]},
            "me":{"mapId":"m","x":100,"y":100,"inputSeq":10,
                  "achievements":{"counters":{"bonusboxes":10},"private":"ignore"}},
            "boxes":[{"id":"near","revision":1,"x":130,"y":140}],"npcs":[]}}
        self.feed.ingest("s",json.dumps(self.full))
        self.probe=ManualCollectProbe(self.feed,clock=lambda:self.now)
    def post(self, seq=11, **extra):
        cmd={"inputSeq":seq,"respawnRevision":1,"destination":{"x":130,"y":140}}
        cmd.update(extra)
        self.probe.observe(json.dumps({"inputTransport":"cumulative-input-v1",
                                      "inputChannel":"secret-channel","commands":[cmd]}))
    def test_recording_does_not_reset_feed_and_keeps_diagnostic_after_failure(self):
        before=deepcopy(self.feed.navigation_snapshot())
        self.probe.arm()
        self.assertEqual(self.feed.navigation_snapshot(),before)
        self.post()
        self.feed.ingest("s",json.dumps({"transport":"delta1","epoch":"e","sequence":2,"base":1,
            "patch":["o",[["boxes",["s",0,[]]]],[]]}))
        report=self.probe.report()
        self.assertEqual(report["reader"]["failure"]["path"],"boxes")
        self.assertEqual(len(report["commands"]),1)
        self.assertFalse(report["data_fresh"])
        report["reader"]["failure"]["path"]="modified"
        self.assertEqual(self.probe.report()["reader"]["failure"]["path"],"boxes")

    def test_arm_requires_live_state(self):
        self.now=4
        with self.assertRaises(ValueError): self.probe.arm()
    def test_ordinary_command_is_described_without_credentials(self):
        self.probe.arm(); self.post(secret="secret-value",boxId="near")
        report=self.probe.report()
        self.assertEqual(report["commands"][0]["near_box_id"],"near")
        self.assertEqual(report["commands"][0]["box_references"],{"boxId":"near"})
        self.assertNotIn("secret-value",json.dumps(report))
        self.assertNotIn("secret-channel",json.dumps(report))
        self.assertEqual(report["automatic_commands_sent"],0)
    def test_cumulative_backlog_is_ignored_and_duplicates_not_added(self):
        self.probe.arm(); self.post(seq=10); self.post(); self.post()
        self.assertEqual(len(self.probe.report()["commands"]),1)
    def test_recording_expires(self):
        self.probe.arm(); self.now=32; self.post()
        self.assertEqual(self.probe.report()["commands"],[])
        self.assertFalse(self.probe.report()["recording"])
    def test_observed_reward_counter_increment(self):
        self.probe.arm(); self.post()
        full=deepcopy(self.full); full["sequence"]=2
        full["full"]["me"]["achievements"]["counters"]["bonusboxes"]=11
        self.feed.ingest("s",json.dumps(full))
        self.assertEqual(self.probe.report()["observed_box_increment"],1)
    def test_report_does_not_return_shared_mutable_objects(self):
        self.probe.arm(); self.post()
        self.probe.report()["commands"].clear()
        self.assertEqual(len(self.probe.report()["commands"]),1)

if __name__=="__main__": unittest.main()
