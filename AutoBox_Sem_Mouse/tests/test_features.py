import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import DataFarmPlanner, DataCollector, SessionEarnings
from browser_session import WorldFeed, BrowserSession
from test_world_feed import snapshot

class NewFeatures(unittest.TestCase):
    def test_account_rewards_and_repair_projection(self):
        state=snapshot()
        state["time"]=100
        state["me"].update(credits=123,uridium=500,xp=40000,honor=88,
            galaxyGates={"bootyKeys":2,"private":"secret"},
            repairChoices={"id":"death1","readyAt":90,"baseMap":"1-1","killer":"private killer",
                "options":[{"id":"base","cost":0,"available":True,"affordable":True}]})
        state["events"]=[{"id":"reward1","time":100,"type":"box-collected","field":"uridium","amount":5,"message":"private"}]
        feed=WorldFeed(); feed.begin("s")
        self.assertTrue(feed.ingest("s",json.dumps({"transport":"delta1","epoch":"e","sequence":1,"full":state})))
        data=feed.navigation_snapshot()
        self.assertEqual(data["account"],dict(credits=123,uridium=500,xp=40000,honor=88,level=4))
        self.assertEqual(data["booty_keys"],2)
        self.assertEqual(data["repair"]["options"][0]["cost"],0)
        self.assertNotIn("private",repr(data))
        self.assertTrue(feed.ingest("s",json.dumps({"transport":"delta1","epoch":"e","sequence":2,"base":1,
            "patch":["o",[["events",["a",1,[[0,["o",[["amount",["v",10]]],[]]]]]]],[]]})))
        self.assertEqual(feed.navigation_snapshot()["rewards"][0]["amount"],10)

    def test_earnings_ignore_history_pause_duplicates_pet_and_other_income(self):
        earnings=SessionEarnings()
        def snap(i,**kw):
            e=dict(id=i,time=i,type="box-collected",field="uridium",amount=10); e.update(kw)
            return dict(fresh=True,rewards=[e])
        earnings.observe(snap(1),True)
        earnings.observe(snap(2),True)
        earnings.observe(snap(2),True)
        earnings.observe(snap(3),False)
        earnings.observe(snap(3),True)
        earnings.observe(snap(4,petCollected=True),True)
        earnings.observe(snap(5,type="npc-killed"),True)
        self.assertEqual(earnings.total,10)
        self.assertIsNone(earnings.hourly(59))
        self.assertEqual(earnings.hourly(120),300)

    def test_green_needs_option_and_keys_then_confirms_key_consumption(self):
        data=dict(fresh=True,map="4-3",position=(0,0),hp_percent=100,booty_keys=1,box_counter=0,
            candidates=[dict(id="green",kind="booty",revision=1,x=10,y=0),
                        dict(id="normal",kind="box",revision=1,x=80,y=0)])
        self.assertEqual(DataFarmPlanner().step(data,0)["target_id"],"normal")
        planner=DataFarmPlanner(include_green=True)
        self.assertEqual(planner.step(data,0)["target_id"],"green")
        data["booty_keys"]=0; data["candidates"]=data["candidates"][1:]
        self.assertEqual(planner.step(data,1)["phase"],"confirmed")
        self.assertEqual(DataFarmPlanner(include_green=True).step(data,1)["target_id"],"normal")

    def test_respawn_rejects_cost_and_cancelled_operations(self):
        session=BrowserSession(Path("unused"),{"width":1280,"height":720})
        session.world_feed=Mock()
        snap=dict(fresh=True,dead=True,repair={"id":"d","options":[dict(id="portal",cost=500,available=True,affordable=True)]})
        session.world_feed.navigation_snapshot.return_value=snap
        session.world_feed._number=lambda v:type(v) in (int,float)
        page=Mock()
        self.assertEqual(session._respawn(page,dict(death_id="d",option="portal",max_cost=0),lambda:True)["action"],"blocked")
        self.assertEqual(session._respawn(page,dict(death_id="d",option="portal",max_cost=500),lambda:False)["action"],"cancelled")
        page.evaluate.assert_not_called()
        session._respawn(page,dict(death_id="d",option="portal",max_cost=500),lambda:True)
        page.evaluate.assert_called_once()

    def test_reconnect_does_not_touch_browser_after_pause(self):
        session=BrowserSession(Path("unused"),{"width":1280,"height":720})
        context=Mock()
        self.assertEqual(session._reconnect(context,{},lambda:False)["action"],"cancelled")
        self.assertEqual(context.mock_calls,[])

    def test_reconnect_uses_existing_game_button(self):
        session=BrowserSession(Path("unused"),{"width":1280,"height":720})
        session.world_feed=Mock()
        session.world_feed.navigation_snapshot.return_value={"fresh":False}
        page=Mock(); page.url="https://interstellar-verse.com/play/"
        page.evaluate.return_value="flightStart"
        context=Mock(pages=[page])
        self.assertEqual(session._reconnect(context,{},lambda:True)["action"],"flightStart")
        page.locator.assert_called_once_with("#flightStart")
        page.reload.assert_not_called()

    def test_death_limit_prevents_respawn(self):
        session=Mock()
        session.get_world_snapshot.return_value=dict(fresh=True,dead=True,repair={"id":"d"})
        events=[]
        engine=DataCollector(session,threading.Event(),lambda *e:events.append(e),
            settings={"respawn":"base","max_deaths":1})
        engine.run()
        session.request.assert_not_called()
        self.assertEqual(engine.deaths["count"],1)
        self.assertTrue(any("Limite de mortes" in str(e) for e in events))

    def test_reconnect_can_be_cancelled_without_resuming(self):
        session=Mock(); stop=threading.Event(); events=[]
        session.get_world_snapshot.return_value={"fresh":False}
        session.ready.is_set.return_value=True
        def reconnect(*a,**kw):
            stop.set()
            return {"action":"wait"}
        session.request.side_effect=reconnect
        DataCollector(session,stop,lambda *e:events.append(e),settings={"reconnect":True}).run()
        self.assertEqual(session.request.call_count,1)
        self.assertEqual([v for k,v in events if k=="running"],[True,False,False])

    def test_reconnect_resumes_only_after_fresh_data(self):
        session=Mock(); stop=threading.Event(); events=[]
        session.ready.is_set.return_value=True
        data=dict(fresh=True,map="4-3",position=(0,0),hp_percent=100,
                  candidates=[dict(id="box",kind="box",revision=1,x=10,y=0)])
        session.get_world_snapshot.side_effect=[{"fresh":False},data]
        def request(op,*args,**kwargs):
            if op=="data_target": stop.set()
            return {"action":"wait"}
        session.request.side_effect=request
        DataCollector(session,stop,lambda *e:events.append(e),settings={"reconnect":True}).run()
        self.assertEqual([c.args[0] for c in session.request.call_args_list],["reconnect","data_target"])
        self.assertEqual([v for k,v in events if k=="running"],[True,False,True,False])
