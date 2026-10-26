import copy
import unittest
from unittest.mock import patch
from controller import FinishPursuit, NpcTestWorker
from test_npc_test import Stop, Session

class FinishPursuitTests(unittest.TestCase):
    def npc(self,x=1000,y=100,hp=100,maxHp=1000):
        return dict(id="mordon",x=x,y=y,hp=hp,maxHp=maxHp,respawnRevision=1,kind="mordon",shield=0)
    def started(self,**settings):
        p=FinishPursuit(enabled=True,**settings)
        self.assertFalse(p.step(self.npc(),(0,100),0,True))
        self.assertTrue(p.step(self.npc(1100),(0,100),1,True))
        return p
    def test_stationary_or_healthy_npc_does_not_trigger(self):
        p=FinishPursuit(enabled=True)
        self.assertFalse(p.step(self.npc(),(0,100),0,True))
        self.assertFalse(p.step(self.npc(),(0,100),1,True))
        self.assertFalse(p.step(self.npc(1200,hp=600),(0,100),2,True))
    def test_disabled_or_unknown_max_hp_preserves_normal_mode(self):
        for enabled,maximum in ((False,1000),(True,None)):
            p=FinishPursuit(enabled=enabled)
            for t in range(5):self.assertFalse(p.step(self.npc(1000+t*100,maxHp=maximum),(0,100),t,True))
    def test_wounded_fugitive_stays_active_and_smooths_direction_changes(self):
        p=self.started()
        old=p.velocity
        self.assertTrue(p.step(self.npc(1050,180),(0,100),2,True))
        self.assertGreater(p.velocity[0],-50)
        self.assertLess(p.velocity[1],80)
        self.assertNotEqual(old,p.velocity)
    def test_time_and_absolute_distance_limits(self):
        for npc,now,message in ((self.npc(4000),2,"distância máxima"),(self.npc(1200),61,"tempo máximo")):
            p=self.started()
            with self.assertRaisesRegex(ValueError,message):p.step(npc,(0,100),now,True)
    def test_lost_lock_or_dead_target_ends_pursuit(self):
        p=self.started();self.assertFalse(p.step(self.npc(),(0,100),2,False))
        p=self.started();self.assertFalse(p.step(self.npc(hp=0),(0,100),2,True))
    def test_invalid_configuration(self):
        for settings in (dict(radius=0),dict(hp=101),dict(seconds=0),dict(max_distance=100)):
            with self.assertRaises(ValueError):FinishPursuit(**settings)

    def exercise(self,ending,seconds=10):
        stop=Stop();session=Session(stop,damage=False);events=[]
        n=self.npc(100);session.state["npc_candidates"]=[n]
        original=session.get_world_snapshot
        def snapshot():
            if session.state["combat"]["attacking"] and session.state["npc_candidates"]:
                current=session.state["npc_candidates"][0]
                current["x"]+=80
                if stop.now>2:
                    if ending=="death":
                        session.state["npc_candidates"]=[];session.state["account"]["xp"]+=50
                        session.state["combat"]["attacking"]=False
                    elif ending=="lost":session.state["npc_candidates"]=[]
                    elif ending=="low_hp":session.state["hp_percent"]=30
                    elif ending=="ship_dead":session.state["dead"]=True
                    elif ending=="map":session.state["map"]="1-1"
                    elif ending=="manual":stop.set()
                    elif ending=="unreachable":current["x"]=1800
                    elif ending=="max_distance":current["x"]=5000
            return original()
        session.get_world_snapshot=snapshot
        engine=NpcTestWorker(session,stop,lambda e,d:events.append((e,d)),clock=lambda:stop.now,
            pursuit_enabled=True,pursuit_seconds=seconds)
        engine.damage=True
        with patch("controller.time.sleep"):engine.run()
        return engine,session,events
    def test_worker_pursues_without_orbit_or_target_switch(self):
        engine,session,events=self.exercise("death")
        moves=[p for _,p in session.calls if p.get("pursuit")]
        self.assertTrue(moves)
        self.assertEqual({p["id"] for p in moves},{"mordon"})
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertFalse(engine.report["pursuit_active"])
    def test_worker_safety_exit_paths(self):
        for ending,message in (("lost","sem confirmação"),("low_hp","Vida no limite"),
            ("ship_dead","destruída"),("map","Mapa ou vida"),("manual","cancelado"),
            ("max_distance","distância máxima")):
            with self.subTest(ending=ending):
                engine,session,events=self.exercise(ending)
                self.assertIn(message,engine.report["status"])
                self.assertFalse(engine.report["pursuit_active"])
    def test_no_progress_guard_remains_active(self):
        engine,session,events=self.exercise("unreachable",seconds=180)
        self.assertIn("Sem aproximação ou dano",engine.report["status"])

    def test_unreachable_target_is_bounded(self):
        engine,session,events=self.exercise("unreachable")
        self.assertIn("tempo máximo",engine.report["status"])
        self.assertFalse(engine.report["kill_confirmed"])
