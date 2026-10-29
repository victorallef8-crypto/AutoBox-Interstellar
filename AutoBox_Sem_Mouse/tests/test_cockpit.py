import copy
import unittest
from unittest.mock import Mock, patch
import test_app
from cockpit import MapModel
from controller import BudgetStop, DataFarmPlanner, NpcTestWorker, NpcFarmWorker
from test_npc_test import Stop, Session
from browser_session import BrowserSession
from browser_session import WorldFeed
from test_world_feed import snapshot
import json


def live():
    return dict(fresh=True,map="3-2",respawn_revision=1,map_size=(20000,12000),position=(2000,3000),
                npc_candidates=[dict(id="a",x=3000,y=3000)],candidates=[],gates=[])


class MapTests(unittest.TestCase):
    def test_live_feed_exports_map_size_and_selected_ammunition_only(self):
        state=snapshot();state["me"].update(selectedAmmo="ucb100",ammunitionStock={"ucb100":123,"private":"ignore"})
        feed=WorldFeed();feed.begin("s")
        feed.ingest("s",json.dumps(dict(transport="delta1",epoch="e",sequence=1,full=state)))
        data=feed.navigation_snapshot()
        self.assertEqual(data["combat"]["selected_stock"],123)
        self.assertEqual(data["map_size"],(state["map"]["width"],state["map"]["height"]))
        self.assertNotIn("private",feed.state["me"]["ammunitionStock"])
    def test_stale_feed_removes_entities_and_history(self):
        model=MapModel();self.assertEqual(len(model.update(live())["npcs"]),1)
        self.assertIsNone(model.update(dict(fresh=False)))
        self.assertFalse(model.trail)

    def test_map_life_changes_clear_trail_and_length_is_bounded(self):
        model=MapModel();s=live()
        for i in range(100):s["position"]=(i,3000);model.update(s)
        self.assertEqual(len(model.trail),80)
        s["respawn_revision"]=2;model.update(s);self.assertEqual(len(model.trail),1)
        s["map"]="1-1";model.update(s);self.assertEqual(len(model.trail),1)

    def test_invalid_dimensions_and_coordinates_never_draw(self):
        for size in ((0,1),(float("nan"),2),12):
            self.assertIsNone(MapModel().update(dict(live(),map_size=size)))
        s=live();s["npc_candidates"].extend([dict(x=float("nan"),y=2),dict(x=-10,y=2)])
        self.assertEqual(len(MapModel().update(s)["npcs"]),1)


class SmartFarmTests(unittest.TestCase):
    def test_hybrid_cloak_confirmation_survives_collection_slices(self):
        stop=Stop();session=Mock()
        session.get_world_snapshot.return_value=dict(fresh=True,hp_percent=100,map="3-2",position=(0,0),candidates=[])
        def request(op,payload,allowed):
            self.assertEqual(op,"cloak")
            return dict(action="sent",owner="p",life=1) if payload["action"]=="ensure" else dict(action="inactive")
        session.request.side_effect=request
        engine=NpcFarmWorker(session,stop,Mock(),hybrid=True,clock=lambda:stop.now,collect_settings=dict(cloak=True))
        engine.collect_interval()
        self.assertIsNotNone(engine.collection_cloak.pending)
        with self.assertRaisesRegex(ValueError,"sem confirmação"):
            for _ in range(3):engine.collect_interval()
        self.assertEqual(sum(c.args[1]["action"]=="ensure" for c in session.request.call_args_list),1)

    def test_hybrid_does_not_attack_before_pending_cloak_is_confirmed(self):
        stop=Stop();session=Session(stop,damage=False);original=session.request
        def request(op,payload,allowed):
            if op=="cloak":return dict(action="inactive")
            return original(op,payload,allowed)
        session.request=request
        engine=NpcFarmWorker(session,stop,Mock(),kind="mordon",hybrid=True,clock=lambda:stop.now,collect_settings=dict(cloak=True))
        engine.collection_cloak.pending=dict(owner="p",life=1,sent_at=0)
        engine.run()
        self.assertFalse(any(p["action"]=="attack" for _,p in session.calls))
        self.assertTrue(stop.is_set())
    def test_profiles_do_not_change_in_a_running_farm(self):
        profiles={"saimon":dict(priority=1,ammo="lcb10",radius=450,orbit=True)}
        engine=NpcFarmWorker(Mock(),Stop(),Mock(),npc_profiles=profiles)
        profiles["saimon"]["ammo"]="ucb100"
        self.assertEqual(engine.settings["npc_profiles"]["saimon"]["ammo"],"lcb10")
    def test_collection_deadline_and_local_stop_preserve_parent(self):
        parent=Stop();budget=BudgetStop(parent,2,lambda:parent.now)
        self.assertFalse(budget.wait(1));self.assertTrue(budget.wait(1))
        self.assertFalse(parent.is_set())
        budget=BudgetStop(parent,2,lambda:parent.now);budget.set()
        self.assertFalse(parent.is_set());self.assertTrue(budget.is_set())
        budget=BudgetStop(parent,2,lambda:parent.now);parent.set();self.assertTrue(budget.is_set())

    def test_deferred_resource_expires_and_new_revision_is_not_blocked(self):
        s=dict(fresh=True,map="1-1",position=(0,0),hp_percent=100,candidates=[
            dict(id="a",revision=1,x=10,y=0),dict(id="b",revision=1,x=100,y=0)])
        planner=DataFarmPlanner();self.assertEqual(planner.step(s,0)["target_id"],"a")
        planner.defer_target(1);self.assertEqual(planner.step(s,2)["target_id"],"b")
        planner.target=None;self.assertEqual(planner.step(s,32)["target_id"],"a")

    def test_priority_and_ammo_profile_apply_to_selected_kind(self):
        stop=Stop();session=Session(stop,damage=False)
        session.state["npc_candidates"].append(dict(id="saimon",kind="saimon",respawnRevision=1,x=700,y=0,hp=100))
        original=session.request
        def request(op,payload,allowed):
            if payload["action"]=="select":stop.set()
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *args:None,clock=lambda:stop.now,kind=["mordon","saimon"],
                             npc_profiles={"saimon":dict(priority=-1,ammo="ucb100",radius=600,orbit=True)})
        engine.run()
        self.assertEqual(engine.target["id"],"saimon")
        self.assertEqual(engine.ammo,"ucb100");self.assertEqual(engine.radius,600)

    def test_lost_selection_ack_is_retried_without_duplicate_attack(self):
        stop=Stop();session=Session(stop);original=session.request;count=[0]
        def request(op,payload,allowed):
            if payload["action"]=="select":
                count[0]+=1
                if count[0]==1:return dict(action="select_sent")
            return original(op,payload,allowed)
        session.request=request
        engine=NpcTestWorker(session,stop,lambda *args:None,clock=lambda:stop.now)
        engine.run()
        self.assertTrue(engine.report["kill_confirmed"])
        self.assertEqual(count[0],2)
        self.assertEqual(sum(p["action"]=="attack" for _,p in session.calls),1)

    def test_hybrid_waits_for_confirmed_stop_before_collecting(self):
        stop=Stop();session=Session(stop);events=[]
        engine=NpcFarmWorker(session,stop,lambda *e:events.append(e),kind="mordon",hybrid=True,clock=lambda:stop.now)
        def collect():
            self.assertTrue(engine.last.report["stop_confirmed"])
            self.assertFalse(session.state["combat"]["attacking"])
            stop.set()
        with patch.object(engine,"collect_interval",side_effect=collect) as callback:
            engine.run()
        callback.assert_called_once();self.assertEqual(engine.kills,1)
        self.assertEqual(engine.stats["mordon"]["kills"],1)
        self.assertEqual(engine.stats["mordon"]["ammo"],"lcb10")

    def test_unreachable_target_is_deferred_only_after_confirmed_stop(self):
        stop=Stop();session=Session(stop,damage=False);events=[]
        def emit(event,data):
            events.append((event,data))
            if event=="status" and "ignorado por 30" in str(data):stop.set()
        engine=NpcFarmWorker(session,stop,emit,kind="mordon",clock=lambda:stop.now)
        engine.run()
        self.assertTrue(engine.last.report["stop_confirmed"])
        self.assertEqual(engine.failed_targets,1)
        self.assertIn(("mordon",1),engine.skip_until)
        self.assertEqual(engine.kills,0)

    def test_window_state_uses_cdp_and_detaches(self):
        session=BrowserSession.__new__(BrowserSession);session._game_page=Mock(return_value="page")
        context=Mock();cdp=context.new_cdp_session.return_value
        cdp.send.side_effect=[dict(windowId=12),{}]
        result=session._window_state(context,dict(state="minimized"))
        self.assertEqual(result["state"],"minimized")
        cdp.send.assert_any_call("Browser.setWindowBounds",dict(windowId=12,bounds=dict(windowState="minimized")))
        cdp.detach.assert_called_once()
        with self.assertRaises(ValueError):session._window_state(context,dict(state="closed"))


class CockpitUiTests(unittest.TestCase):
    setUpClass=classmethod(test_app.AppTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.AppTests.tearDownClass.__func__)

    def test_compact_and_full_views_keep_same_workers_and_settings(self):
        worker=self.app.worker
        for compact in (False,True,False):
            self.app.set_compact(compact);self.root.update_idletasks()
            self.assertEqual(self.app.compact,compact)
            self.assertIs(self.app.worker,worker)
            self.assertEqual(self.app.cfg["compact_view"],compact)

    def test_cockpit_stale_map_is_cleared_and_controls_are_bound(self):
        self.app.cockpit.update(live())
        self.assertGreater(len(self.app.cockpit.canvas.find_all()),1)
        self.app.cockpit.update(dict(fresh=False))
        self.assertEqual(len(self.app.cockpit.canvas.find_all()),1)
        self.assertTrue(all(b["command"] for b in self.app.cockpit.buttons.values()))

    def test_profiles_persist_and_remove(self):
        self.app.profile_kind.set("saimon");self.app.profile_priority.set("-2")
        self.app.profile_ammo.set("ucb100");self.app.profile_radius.set("550")
        self.app.save_npc_profile()
        self.assertEqual(self.app.cfg["npc_profiles"]["saimon"]["ammo"],"ucb100")
        self.app.remove_npc_profile();self.assertNotIn("saimon",self.app.cfg["npc_profiles"])

    def test_compact_start_dispatches_one_mode_only(self):
        with patch.object(self.app,"start_npc_test") as npc,patch.object(self.app,"start") as collect:
            self.app.cockpit.mode.set("Matar + coletar");self.app.cockpit.start()
            npc.assert_called_once_with(hybrid=True);collect.assert_not_called()
