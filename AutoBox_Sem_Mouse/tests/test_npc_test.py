import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import NpcTestWorker, NpcFarmWorker
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
        if action=="orbit":
            return {"action":"orbiting","direction":1}
        if action=="stop":
            self.state["combat"]["attacking"]=False
            return {"action":"stop_sent" if self.state["npc_candidates"] else "stopped"}
        return {"action":"move_sent"}

class NpcWorkerTests(unittest.TestCase):
    def test_reward_cannot_confirm_without_attack_or_with_live_target(self):
        for attacked,absent in ((False,True),(True,False)):
            stop=Stop();session=Session(stop,damage=False)
            engine=self.engine(session,stop)
            engine.target=dict(session.state["npc_candidates"][0])
            engine.context={"map":"3-4","life":1};engine.started=0
            engine.attack_sent=attacked;engine.baseline_xp=1000
            session.state["account"]["xp"]=1100
            session.state["rewards"]=[dict(id="new",time=2,type="kill")]
            if absent:session.state["npc_candidates"]=[]
            engine.confirm_target_end()
            self.assertFalse(engine.report["kill_confirmed"])

    def test_confirmation_stops_on_map_life_or_connection_change(self):
        for change in (dict(map="1-1"),dict(respawn_revision=2),dict(fresh=False),dict(dead=True)):
            stop=Stop();session=Session(stop,damage=False)
            engine=self.engine(session,stop)
            engine.target=dict(session.state["npc_candidates"][0])
            engine.context={"map":"3-4","life":1};engine.started=0
            engine.attack_sent=True;engine.baseline_xp=1000
            session.state.update(change,npc_candidates=[],account={"xp":1100})
            engine.confirm_target_end()
            self.assertFalse(engine.report["kill_confirmed"])
            self.assertEqual(stop.now,0)

    def test_visible_npc_is_selected_before_any_movement_at_all_distances(self):
        for x in (200,450,1200):
            stop=Stop();session=Session(stop)
            session.state["npc_candidates"][0]["x"]=x
            engine=self.engine(session,stop);engine.run()
            self.assertEqual([p["action"] for _,p in session.calls][:2],["select","attack"])
            self.assertTrue(engine.report["kill_confirmed"])

    def test_instant_kill_without_damage_sample_or_attack_echo(self):
        for delay in (0,3):
            stop=Stop();session=Session(stop,damage=False);original=session.request
            snapshot=session.get_world_snapshot;deadline=[None]
            def request(op,payload,allowed):
                result=original(op,payload,allowed)
                if payload["action"]=="attack":
                    session.state["npc_candidates"]=[]
                    session.state["combat"].update(attacking=False,target_id=None)
                    deadline[0]=stop.now+delay
                return result
            def read():
                if deadline[0] is not None and stop.now>=deadline[0]:
                    session.state["account"]["xp"]=1100
                return snapshot()
            session.request=request;session.get_world_snapshot=read
            engine=self.engine(session,stop);engine.run()
            self.assertTrue(engine.report["kill_confirmed"])
            self.assertFalse(engine.report["damage_observed"])
            self.assertTrue(engine.report["stop_confirmed"])
            self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)
            self.assertGreaterEqual(stop.now,delay)

    def test_fast_kill_events_exclude_old_pet_and_box_rewards(self):
        for event,expected in ((dict(id="new",time=2,type="kill"),True),
                               (dict(id="old",time=1,type="kill"),False),
                               (dict(id="pet",time=2,type="kill",pet=True),False),
                               (dict(id="box",time=2,type="box-collected"),False)):
            stop=Stop();session=Session(stop,damage=False);original=session.request
            session.state["rewards"]=[dict(id="old",time=1,type="kill")]
            def request(op,payload,allowed):
                result=original(op,payload,allowed)
                if payload["action"]=="attack":
                    session.state["npc_candidates"]=[]
                    session.state["combat"].update(attacking=False,target_id=None)
                    session.state["rewards"].append(event)
                return result
            session.request=request
            engine=self.engine(session,stop);engine.run()
            self.assertEqual(engine.report["kill_confirmed"],expected)

    def test_continuous_farm_chains_two_instant_kills(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request;spawned=[False]
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":
                session.state["npc_candidates"]=[]
                session.state["account"]["xp"]+=100
                session.state["combat"].update(attacking=False,target_id=None)
            if payload["action"]=="stop" and not spawned[0]:
                spawned[0]=True
                session.state["npc_candidates"]=[dict(id="mordon",respawnRevision=2,kind="mordon",x=400,y=0,hp=100)]
            return result
        session.request=request
        def emit(event,data):
            if event=="npc_report" and data.get("kills")==2:stop.set()
        engine=NpcFarmWorker(session,stop,emit,kind="mordon",clock=lambda:stop.now)
        engine.run()
        self.assertEqual(engine.kills,2)
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),2)

    def test_cancel_during_delayed_reward_wait_does_not_confirm_kill(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        snapshot=session.get_world_snapshot
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":
                session.state["npc_candidates"]=[]
                session.state["combat"].update(attacking=False,target_id=None)
            return result
        def read():
            if stop.now>=1:stop.set()
            return snapshot()
        session.request=request;session.get_world_snapshot=read
        engine=self.engine(session,stop);engine.run()
        self.assertFalse(engine.report["kill_confirmed"])
        self.assertLess(stop.now,2)

    def engine(self,session,stop):
        return NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now)
    def test_single_npc_ends_after_damage_disappearance_and_reward(self):
        stop=Stop();session=Session(stop);engine=self.engine(session,stop);engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertTrue(engine.report["damage_observed"])
        self.assertTrue(engine.report["stop_confirmed"])
        self.assertEqual([p["action"] for _,p in session.calls if p["action"]!="orbit"],["select","attack","stop"])
    def test_hidden_target_approaches_again_before_selecting(self):
        stop=Stop();session=Session(stop);original=session.request;visible=[False]
        def request(op,payload,allowed):
            if payload["action"]=="select" and not visible[0]:
                session.calls.append((op,dict(payload)));return {"action":"not_visible"}
            if payload["action"]=="approach":
                visible[0]=True
            return original(op,payload,allowed)
        session.request=request
        engine=self.engine(session,stop);engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertEqual([p["action"] for _,p in session.calls if p["action"]!="orbit"],["select","approach","select","attack","stop"])

    def test_permanently_hidden_target_times_out_without_attack(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="select":
                session.calls.append((op,dict(payload)));return {"action":"not_visible"}
            return original(op,payload,allowed)
        session.request=request
        engine=self.engine(session,stop);engine.run()
        self.assertIn("Sem aproximação ou dano",engine.report["status"])
        self.assertFalse(any(p["action"]=="attack" for _,p in session.calls))
        self.assertLessEqual(sum(p["action"]=="approach" for _,p in session.calls),31)

    def test_orbit_only_after_attack_confirmation(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="orbit":
                self.assertTrue(session.state["combat"]["attacking"])
                session.calls.append((op,dict(payload)));return {"action":"orbiting","direction":-1}
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True)
        engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertTrue(any(p["action"]=="orbit" for _,p in session.calls))

    def test_recovery_stops_fire_then_enables_repair_once(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="retreat":
                session.calls.append((op,dict(payload)))
                if not payload["enable_repair"]:
                    return {"action":"retreating","gate":"portal","distance":20 if session.state["combat"].get("repairing") else 400,"repair":"waiting"}
                self.assertFalse(session.state["combat"]["attacking"])
                session.state["combat"]["repairing"]=True
                session.state["hp_percent"]=95
                return {"action":"retreating","gate":"portal","distance":20,"repair":"sent"}
            result=original(op,payload,allowed)
            if payload["action"]=="attack":session.state["hp_percent"]=39
            return result
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,repair_portal=True)
        engine.run()
        retreats=[p for _,p in session.calls if p["action"]=="retreat"]
        self.assertEqual(sum(p["enable_repair"] for p in retreats),1)
        self.assertIn("Recuperada no portal",engine.report["status"])
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)


    def test_failed_stop_at_portal_exits_without_repair_or_new_attack(self):
        from unittest.mock import patch
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="stop":
                session.calls.append((op,dict(payload)))
                return {"action":"stop_ctrl_sent" if payload["allow_ctrl_stop"] else "stop_unavailable"}
            if payload["action"]=="retreat":
                session.calls.append((op,dict(payload)))
                self.assertFalse(payload["enable_repair"])
                return {"action":"retreating","gate":"near","distance":0,"repair":"waiting"}
            result=original(op,payload,allowed)
            if payload["action"]=="attack": session.state["hp_percent"]=35.9
            return result
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,repair_portal=True)
        with patch("controller.time.sleep"):
            engine.run()
        self.assertIn("Ataque não parou",engine.report["status"])
        self.assertFalse(engine.report["stop_confirmed"])
        self.assertLess(stop.now,20)
        stops=[p for _,p in session.calls if p["action"]=="stop"]
        self.assertEqual(sum(p["allow_ctrl_stop"] for p in stops),1)
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_secondary_volley_does_not_confirm_stopped(self):
        from unittest.mock import patch
        stop=Stop();session=Session(stop,damage=False)
        session.state["combat"]["secondaryVolley"]=True
        engine=self.engine(session,stop)
        engine.target=session.state["npc_candidates"][0]
        engine.context={"map":"3-4","life":1};engine.started=0
        with patch("controller.time.sleep"):
            engine.cease_fire()
        self.assertFalse(engine.report["stop_confirmed"])

    def test_missing_repair_confirmation_does_not_toggle_again(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="retreat":
                session.calls.append((op,dict(payload)))
                return {"action":"retreating","gate":"portal","distance":400,"repair":"sent" if payload["enable_repair"] else "waiting"}
            result=original(op,payload,allowed)
            if payload["action"]=="attack":session.state["hp_percent"]=39
            return result
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,repair_portal=True)
        engine.run()
        self.assertIn("não confirmou ativação",engine.report["status"])
        self.assertEqual(sum(p.get("enable_repair",False) for _,p in session.calls),1)

    def test_pause_never_starts_recovery(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="attack":stop.set()
            return result
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,repair_portal=True)
        engine.run()
        self.assertFalse(any(p["action"]=="retreat" for _,p in session.calls))

    def test_selected_moving_npc_starts_attack_before_more_approach(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="select":session.state["npc_candidates"][0]["x"]=650
            return result
        session.request=request
        engine=self.engine(session,stop);engine.run()
        actions=[p["action"] for _,p in session.calls]
        self.assertEqual(actions[:2],["select","attack"])
        self.assertIn("approach",actions)
        self.assertEqual(actions.count("attack"),1)
        self.assertTrue(engine.report["kill_confirmed"])

    def test_multiple_types_select_nearest_allowed_not_unchecked_npc(self):
        stop=Stop();session=Session(stop)
        session.state["npc_candidates"].extend([
            dict(id="far",kind="lordakia",respawnRevision=1,x=900,y=0,hp=2000,shield=0),
            dict(id="unchecked",kind="boss",respawnRevision=1,x=10,y=0,hp=5000,shield=0)])
        engine=NpcTestWorker(session,stop,lambda *e:None,kind=["lordakia","mordon"],clock=lambda:stop.now)
        engine.run()
        self.assertEqual(engine.report["target_id"],"mordon")
        self.assertEqual(engine.report["allowed_kinds"],["lordakia","mordon"])
        self.assertTrue(engine.report["kill_confirmed"])

    def test_visible_distant_acquisition_before_pursuing_same_npc_at_radius(self):
        stop=Stop();session=Session(stop);original=session.request
        session.state["npc_candidates"][0]["x"]=1200
        def request(op,payload,allowed):
            if payload["action"]=="approach":
                result=original(op,payload,allowed)
                npc=session.state["npc_candidates"][0]
                if payload.get("close_approach"):
                    session.state["position"]=(npc["x"]-100,0)
                else:
                    self.assertTrue(session.state["combat"]["attacking"])
                    self.assertEqual(payload["radius"],450)
                    session.state["position"]=(npc["x"]-450,0)
                return result
            result=original(op,payload,allowed)
            if payload["action"]=="attack":
                session.state["npc_candidates"][0]["x"]+=700
            return result
        session.request=request
        engine=self.engine(session,stop);engine.run()
        moves=[p for _,p in session.calls if p["action"]=="approach"]
        self.assertEqual(session.calls[0][1]["action"],"select")
        self.assertFalse(any(p.get("close_approach") for p in moves))
        self.assertFalse(moves[-1]["close_approach"])
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertEqual({p["id"] for _,p in session.calls},{"mordon"})
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_unconfirmed_stop_does_not_prevent_moving_to_portal(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="retreat":
                session.calls.append((op,dict(payload)))
                self.assertFalse(payload["enable_repair"])
                stop.set()
                return {"action":"retreating","gate":"near","distance":500,"repair":"waiting"}
            result=original(op,payload,allowed)
            if payload["action"]=="attack":session.state["hp_percent"]=39
            return result
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,repair_portal=True)
        engine.run()
        actions=[p["action"] for _,p in session.calls]
        self.assertLess(actions.index("retreat"),actions.index("stop"))

    def test_portal_fight_retains_gate_and_target_after_attack(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="portal_lure":
                self.assertTrue(session.state["combat"]["attacking"])
                session.calls.append((op,dict(payload)))
                return {"action":"luring","gate":"near","distance":100}
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,portal_fight=True)
        engine.run()
        self.assertEqual(engine.report["combat_gate"],"near")
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertFalse(any(p["action"]=="orbit" for _,p in session.calls))

    def test_client_low_hp_between_snapshot_and_orbit_triggers_recovery(self):
        for enabled in (True,False):
            stop=Stop();session=Session(stop,damage=False);original=session.request
            def request(op,payload,allowed):
                if payload["action"]=="orbit":
                    session.calls.append((op,dict(payload)))
                    return {"action":"low_hp"}
                return original(op,payload,allowed)
            session.request=request
            engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True,repair_portal=enabled)
            engine.recover_at_portal=Mock()
            engine.run()
            self.assertEqual(engine.recover_at_portal.call_count,1 if enabled else 0)
            self.assertTrue(engine.report["stop_confirmed"])
            self.assertTrue(any(a["result"]=="low_hp" for a in engine.report["actions"]))

    def test_gone_during_command_waits_for_reward_without_more_attack(self):
        for reward in (True,False):
            stop=Stop();session=Session(stop,damage=False);original=session.request
            def request(op,payload,allowed):
                if payload["action"]=="orbit":
                    session.calls.append((op,dict(payload)))
                    engine.damage=True
                    session.state["npc_candidates"]=[]
                    session.state["combat"]["attacking"]=False
                    if reward:session.state["account"]["xp"]+=100
                    return {"action":"gone"}
                return original(op,payload,allowed)
            session.request=request
            engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True)
            engine.run()
            self.assertEqual(engine.report["kill_confirmed"],reward)
            self.assertNotIn("não aceito",engine.report["status"])
            self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_custom_ammo_selection_confirmed_then_missile_uses_choice(self):
        stop=Stop();session=Session(stop);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="attack" and session.state["combat"]["selectedAmmo"]!="mcb50":
                session.calls.append((op,dict(payload)))
                session.state["combat"].update(selectedAmmo="mcb50",attacking=True)
                return {"action":"ammo_sent"}
            if payload["action"]=="rocket":
                self.assertEqual(payload["rocket"],"plt2021")
                self.assertEqual(session.state["combat"]["selectedAmmo"],"mcb50")
                session.calls.append((op,dict(payload)));return {"action":"rocket_sent"}
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,ammo="mcb50",rocket="plt2021")
        engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertTrue(any(p["action"]=="rocket" for _,p in session.calls))
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_ammo_selection_without_echo_is_not_repeated(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="attack":
                session.calls.append((op,dict(payload)));return {"action":"ammo_sent"}
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,ammo="mcb50")
        engine.run()
        self.assertIn("não foi confirmado",engine.report["status"])
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_farm_continues_after_kill_with_75_percent_life(self):
        stop=Stop();session=Session(stop);original=session.request;spawned=[0]
        def request(op,payload,allowed):
            result=original(op,payload,allowed)
            if payload["action"]=="stop" and not session.state["npc_candidates"] and spawned[0]<1:
                spawned[0]+=1
                session.state["hp_percent"]=75
                session.state["npc_candidates"]=[dict(id="mordon",respawnRevision=2,kind="mordon",x=100,y=0,hp=1000,shield=0)]
            return result
        session.request=request
        def emit(event,data):
            if event=="npc_report" and data.get("kills")==2:stop.set()
        engine=NpcFarmWorker(session,stop,emit,kind=["mordon"],clock=lambda:stop.now)
        engine.run()
        self.assertEqual(engine.kills,2)
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),2)

    def test_farm_does_not_restart_after_unconfirmed_attack(self):
        stop=Stop();session=Session(stop,ack=False)
        engine=NpcFarmWorker(session,stop,lambda *e:None,clock=lambda:stop.now)
        engine.run()
        self.assertEqual(engine.kills,0)
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)


    def test_low_health_start_repairs_without_previous_target(self):
        from unittest.mock import patch
        stop=Stop();session=Session(stop);session.state["hp_percent"]=35
        engine=NpcFarmWorker(session,stop,lambda *e:None,clock=lambda:stop.now)
        def recover(worker):
            self.assertEqual(worker.context["map"],"3-4")
            worker.report["recovered"]=True
            session.state["hp_percent"]=95
            stop.set()
        with patch.object(NpcTestWorker,"recover_at_portal",recover):
            engine.run()
        self.assertIsNotNone(engine.last)
        self.assertTrue(engine.last.report["recovered"])
        self.assertFalse(any(p["action"]=="attack" for _,p in session.calls))

    def test_farm_recovers_before_next_target(self):
        stop=Stop();session=Session(stop);session.state["hp_percent"]=39
        engine=NpcFarmWorker(session,stop,lambda *e:None,repair_portal=True,clock=lambda:stop.now)
        previous=Mock();previous.report={}
        def recover():
            previous.report["recovered"]=True
            session.state["hp_percent"]=90
            stop.set()
        previous.recover_at_portal.side_effect=recover;engine.last=previous
        engine.run()
        previous.recover_at_portal.assert_called_once()
        self.assertEqual(session.calls,[])

    def test_long_fight_can_continue_past_three_minutes_with_damage(self):
        stop=Stop();session=Session(stop,damage=False);original=session.get_world_snapshot
        def snapshot():
            if session.state["combat"].get("attacking") and session.state["npc_candidates"]:
                stop.now+=10
                session.state["npc_candidates"][0]["hp"]-=20
                if session.state["npc_candidates"][0]["hp"]<=0:
                    session.state["npc_candidates"]=[]
                    session.state["account"]["xp"]+=100
                    session.state["combat"]["attacking"]=False
            return original()
        session.get_world_snapshot=snapshot
        engine=self.engine(session,stop);engine.max_fight_seconds=900
        engine.run()
        self.assertGreater(stop.now,180)
        self.assertTrue(engine.report["kill_confirmed"])

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
        for changes in ({"hp_percent":55},):
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
        self.assertEqual([p["action"] for _,p in session.calls if p["action"]!="orbit"],["select","attack","stop"])
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
