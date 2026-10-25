import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import NpcTestWorker
from browser_session import BrowserSession
import test_combat_travel as probe_tests

class Stop:
    def __init__(self): self.stopped=False; self.now=0
    def is_set(self): return self.stopped
    def set(self): self.stopped=True
    def wait(self,seconds): self.now+=seconds; return self.stopped

class Session:
    def __init__(self,stop,ack=True,damage=True):
        self.stop=stop;self.ack=ack;self.damage=damage;self.calls=[]
        self.state=dict(fresh=True,map="3-4",respawn_revision=1,position=(0,0),hp_percent=100,sequence=1,
            account={"xp":1000},combat={"attacking":False,"selectedAmmo":"lcb10","target_id":None},
            npc_candidates=[dict(id="mordon",respawnRevision=1,kind="mordon",x=100,y=0,hp=1000,shield=0)])
    def get_world_snapshot(self):
        self.state["sequence"]+=1
        if self.state["combat"]["attacking"] and self.damage and self.state["npc_candidates"]:
            self.state["npc_candidates"][0]["hp"]-=200
            if self.state["npc_candidates"][0]["hp"]<=0:
                self.state["npc_candidates"]=[]
                self.state["account"]["xp"]+=100
                self.state["combat"].update(attacking=False,target_id=None)
        return copy.deepcopy(self.state)
    def request(self,op,payload,allowed):
        self.calls.append((op,dict(payload)))
        if not allowed():return {"action":"cancelled"}
        action=payload["action"]
        if action=="select":
            self.state["combat"].update(target_id="mordon",attacking=False)
            return {"action":"select_sent"}
        if action=="attack":
            if self.ack:self.state["combat"]["attacking"]=True
            return {"action":"attack_sent"}
        if action=="stop":
            self.state["combat"]["attacking"]=False
            return {"action":"stop_sent" if self.state["npc_candidates"] else "stopped"}
        return {"action":"move_sent"}

class NpcWorkerTests(unittest.TestCase):
    def engine(self,session,stop):
        return NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now)
    def test_single_npc_ends_after_damage_disappearance_and_reward(self):
        stop=Stop();session=Session(stop);engine=self.engine(session,stop);engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertTrue(engine.report["damage_observed"])
        self.assertTrue(engine.report["stop_confirmed"])
        self.assertEqual([p["action"] for _,p in session.calls],["select","attack","stop"])
    def test_lost_attack_ack_does_not_repeat_ctrl(self):
        stop=Stop();session=Session(stop,ack=False);engine=self.engine(session,stop);engine.run()
        self.assertFalse(engine.report["kill_confirmed"])
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)
        self.assertTrue(engine.report["stop_confirmed"])
        self.assertIn("não foi confirmado",engine.report["status"])
    def test_no_damage_times_out_and_ceases_fire(self):
        stop=Stop();session=Session(stop,damage=False);engine=self.engine(session,stop);engine.run()
        self.assertIn("Sem aproximação ou dano",engine.report["status"])
        self.assertTrue(engine.report["stop_confirmed"])
    def test_low_start_hp_and_wrong_ammo_send_no_attack(self):
        for changes in ({"hp_percent":55},{"combat":{"selectedAmmo":"mcb50","attacking":False}}):
            stop=Stop();session=Session(stop);session.state.update(changes)
            engine=self.engine(session,stop);engine.run()
            self.assertEqual(session.calls,[])
    def test_pause_after_attack_still_dispatches_stop_only(self):
        stop=Stop();session=Session(stop)
        original=session.request
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":stop.set()
            return result
        session.request=request
        engine=self.engine(session,stop);engine.run()
        self.assertEqual([p["action"] for _,p in session.calls],["select","attack","stop"])
        self.assertTrue(engine.report["stop_confirmed"])
    def test_hp_threshold_stops_fire(self):
        stop=Stop();session=Session(stop,damage=False)
        original=session.request
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":session.state["hp_percent"]=39
            return result
        session.request=request
        engine=self.engine(session,stop);engine.run()
        self.assertIn("Vida no limite",engine.report["status"])
        self.assertTrue(engine.report["stop_confirmed"])
    def test_disappearing_target_without_reward_is_not_kill(self):
        stop=Stop();session=Session(stop,damage=False)
        original=session.request
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":
                session.state["npc_candidates"]=[];session.state["combat"]["attacking"]=False
            return result
        session.request=request
        engine=self.engine(session,stop);engine.run()
        self.assertFalse(engine.report["kill_confirmed"])
    def test_browser_cannot_attack_player_or_stale_revision(self):
        browser=BrowserSession(Path("unused"),{"width":1280,"height":720})
        stop=Stop();session=Session(stop)
        browser.world_feed=Mock()
        browser.world_feed.navigation_snapshot.return_value=session.get_world_snapshot()
        page=Mock()
        for changes in ({"id":"player"},{"revision":2}):
            result=browser._npc_action(page,dict(action="attack",map="3-4",life=1,id="mordon",revision=1,**{} )|changes,lambda:True)
            self.assertEqual(result["action"],"gone")
        page.evaluate.assert_not_called()

class RecordingRetentionTests(unittest.TestCase):
    setUp=probe_tests.CombatProbeTests.setUp
    send=probe_tests.CombatProbeTests.send
    packet=probe_tests.CombatProbeTests.packet
    def test_movement_flood_does_not_erase_stop(self):
        self.probe.arm()
        commands=[{"targetId":"npc-1"},{"attacking":True},{"attacking":False}]
        self.probe.observe(self.packet(0,commands))
        for i in range(3,303):
            self.probe.observe(self.packet(i,[{"destination":{"x":i,"y":0}}]))
        values=[c["values"] for c in self.probe.report()["commands"]]
        self.assertIn({"attacking":False},values)
        self.assertIn({"targetId":"npc-1"},values)
        self.assertLessEqual(len(values),160)
