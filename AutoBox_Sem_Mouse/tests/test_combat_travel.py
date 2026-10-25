import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_session import WorldFeed, CombatProbe, BrowserSession
from controller import MapTravel, DataCollector, TravelWorker
from test_world_feed import snapshot

class CombatProbeTests(unittest.TestCase):
    def setUp(self):
        self.now=10
        self.feed=WorldFeed(clock=lambda:self.now); self.feed.begin("s")
        self.state=snapshot()
        self.state["inputAck"]=999
        self.state["npcs"]=[{"id":"npc-1","kind":"streuner","x":130,"y":100,"hp":400,"maxHp":800,"shield":100,"maxShield":100}]
        self.state["me"].update(targetId="npc-1",attacking=False,selectedAmmo="lcb10",ammo=100)
        self.sequence=0
        self.send()
        self.probe=CombatProbe(self.feed,clock=lambda:self.now)
    def send(self):
        self.sequence+=1
        self.assertTrue(self.feed.ingest("s",json.dumps(dict(transport="delta1",epoch="e",sequence=self.sequence,full=self.state))))
    def packet(self,start,commands):
        return json.dumps(dict(inputTransport="cumulative-input-v1",inputStart=start,commands=commands,inputChannel="SECRET"))
    def test_attack_without_inputseq_is_recorded_and_retries_deduplicated(self):
        self.probe.observe(self.packet(5,[{"destination":{"x":1,"y":2}}]))
        self.probe.arm()
        packet=self.packet(5,[{"destination":{"x":1,"y":2}},{"targetId":"npc-1"},{"attacking":True},{"attacking":False}])
        self.probe.observe(packet);self.probe.observe(packet)
        values=[c["values"] for c in self.probe.report()["commands"]]
        self.assertEqual(values,[{"targetId":"npc-1"},{"attacking":True},{"attacking":False}])
        self.assertTrue(self.probe.report()["checks"]["attack_started"])
        self.assertTrue(self.probe.report()["checks"]["attack_stopped"])
        self.assertNotIn("SECRET",json.dumps(self.probe.report()))
    def test_first_packet_does_not_depend_on_movement_sequence_or_ack_numbering(self):
        self.probe.arm()
        self.probe.observe(self.packet(999,[{"attacking":True}]))
        self.assertEqual(self.probe.report()["commands"][0]["values"],{"attacking":True})
        self.assertFalse(self.probe.report()["initial"]["transport_baseline_observed"])
    def test_records_hp_shield_and_ammo_without_player_data(self):
        self.probe.arm();self.now+=1
        self.state["me"].update(username="private",ammo=98,attacking=True)
        self.state["npcs"][0].update(hp=200,shield=0)
        self.send();self.probe.sample()
        last=self.probe.report()["frames"][-1]
        self.assertEqual(last["target_npc"]["hp"],200)
        self.assertEqual(last["target_npc"]["shield"],0)
        self.assertEqual(last["combat"]["ammo"],98)
        self.assertTrue(self.probe.report()["checks"]["damage_observed"])
        self.assertNotIn("private",json.dumps(self.probe.report()))
    def test_player_target_and_arbitrary_fields_are_redacted(self):
        self.probe.arm()
        self.probe.observe(self.packet(0,[{"targetId":"player-secret","token":"SECRET","chat":"SECRET","selectedAmmo":"lcb10"}]))
        report=self.probe.report()
        self.assertEqual(report["commands"][0]["values"],dict(targetId="not_npc",selectedAmmo="lcb10"))
        self.assertNotIn("SECRET",json.dumps(report))
        self.assertNotIn("player-secret",json.dumps(report))
    def test_deadline_and_explicit_stop_end_recording(self):
        self.probe.arm();self.now+=91
        self.assertFalse(self.probe.report()["recording"])
        self.probe.observe(self.packet(0,[{"attacking":True}]))
        self.assertEqual(self.probe.report()["commands"],[])
    def test_map_change_and_stale_data_end_recording(self):
        self.probe.arm();self.now+=1;self.state["map"]["id"]="1-1";self.state["me"]["mapId"]="1-1";self.send()
        self.probe.sample();self.assertFalse(self.probe.report()["recording"])
        self.probe.arm();self.now+=3
        self.assertFalse(self.probe.report()["recording"])
    def test_unknown_protocol_cannot_poison_baseline(self):
        self.probe.observe('{"inputTransport":"other","inputStart":999999,"commands":[{}]}')
        self.assertIsNone(self.probe.highest)
    def test_missing_data_prevents_recording(self):
        self.now+=3
        with self.assertRaises(ValueError):self.probe.arm()

class TravelTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.stop=threading.Event();self.session=Mock();self.events=[]
        self.snap=dict(fresh=True,map="1-1",position=(0,0),hp_percent=100)
        self.route=dict(action="route",map="1-1",gate="g",next_map="1-2",distance=500)
        self.session.request.return_value=self.route
        self.travel=MapTravel(self.session,self.stop,lambda *e:self.events.append(e),"1-3",lambda:self.now)
    def test_arrival_sends_no_command(self):
        self.assertTrue(self.travel.step(dict(self.snap,map="1-3")))
        self.session.request.assert_not_called()
    def test_route_check_precedes_movement_and_retries_are_spaced(self):
        self.assertFalse(self.travel.step(self.snap))
        self.assertEqual([c.args[1]["execute"] for c in self.session.request.call_args_list],[False,True])
        self.now=1;self.travel.step(self.snap)
        self.assertEqual([c.args[1]["execute"] for c in self.session.request.call_args_list],[False,True,False])
    def test_pause_between_route_and_movement_blocks_movement(self):
        def route(*a,**kw):
            self.stop.set();return self.route
        self.session.request.side_effect=route
        self.travel.step(self.snap)
        self.assertEqual(self.session.request.call_count,1)
    def test_low_hp_dead_and_stale_prevent_movement(self):
        for update in ({"hp_percent":25},{"hp_percent":None},{"dead":True},{"fresh":False}):
            with self.assertRaises(ValueError):self.travel.step(dict(self.snap,**update))
        self.session.request.assert_not_called()
    def test_blocked_and_stalled_routes_pause(self):
        self.session.request.return_value={"action":"blocked","reason":"level"}
        with self.assertRaisesRegex(ValueError,"level"):self.travel.step(self.snap)
        self.session.request.return_value=self.route
        self.travel.step(self.snap);self.now=31
        with self.assertRaisesRegex(ValueError,"Sem progresso"):self.travel.step(self.snap)
    def test_gate_change_resets_progress(self):
        self.travel.step(self.snap);self.now=31
        self.session.request.return_value=dict(self.route,map="1-2",gate="g2",distance=900)
        self.assertFalse(self.travel.step(dict(self.snap,map="1-2")))
    def test_browser_rejects_invalid_map_and_cancelled_travel(self):
        session=BrowserSession(Path("unused"),{"width":1280,"height":720})
        session.world_feed=Mock()
        session.world_feed.navigation_snapshot.return_value=self.snap
        page=Mock()
        for dest in ("https://other","galaxy","1-2;","",None):
            with self.assertRaises(ValueError):session._travel(page,{"destination":dest},lambda:True)
        self.assertEqual(session._travel(page,{"destination":"1-2"},lambda:False)["action"],"cancelled")
        page.evaluate.assert_not_called()
    def test_collection_travels_before_targeting_boxes(self):
        frames=[dict(self.snap,candidates=[dict(id="old-box",x=1,y=1,revision=1)]),
                dict(self.snap,map="1-3",candidates=[dict(id="new-box",x=1,y=1,revision=1)])]
        self.session.get_world_snapshot.side_effect=frames
        def request(op,*a,**kw):
            if op=="data_target":self.stop.set();return {"action":"collect"}
            return self.route
        self.session.request.side_effect=request
        engine=DataCollector(self.session,self.stop,lambda *e:self.events.append(e),settings={"farm_map":"1-3"})
        engine.run()
        commands=self.session.request.call_args_list
        self.assertEqual([c.args[0] for c in commands],["travel","travel","data_target"])
        self.assertEqual(commands[-1].args[1]["id"],"new-box")
