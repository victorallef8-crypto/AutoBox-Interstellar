import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import CloakKeeper,DataCollector
from test_skylab import Stop
class CloakTests(unittest.TestCase):
    def make(self,results):
        stop=Stop();session=Mock();session.request.side_effect=results;events=[]
        engine=CloakKeeper(session,stop,lambda e,d:events.append((e,d)),clock=lambda:stop.now)
        return engine,session,stop,events
    def test_confirm_then_reactivate_after_loss(self):
        engine,session,stop,events=self.make([dict(action="sent",owner="p",life=1),dict(action="active"),dict(action="sent",owner="p",life=1)])
        engine.step();stop.now=1;engine.step()
        self.assertIsNone(engine.pending)
        stop.now=2;engine.step();self.assertEqual(session.request.call_count,2)
        stop.now=6;engine.step();self.assertIsNotNone(engine.pending)
        self.assertEqual(session.request.call_args_list[1].args[1],dict(action="inspect",owner="p",life=1))
    def test_unconfirmed_never_resends(self):
        engine,session,stop,_=self.make([dict(action="sent",owner="p",life=1)]+[dict(action="inactive")]*21)
        engine.step()
        for t in range(1,20):stop.now=t;engine.step()
        stop.now=20
        with self.assertRaisesRegex(ValueError,"sem confirmação"):engine.step()
        self.assertEqual(sum(c.args[1]["action"]=="ensure" for c in session.request.call_args_list),1)
    def test_unavailable_deduplicates_and_throttles(self):
        for action in ("empty","unequipped","wait"):
            engine,session,stop,events=self.make([dict(action=action)]*3)
            engine.step();stop.now=1;engine.step();stop.now=5;engine.step()
            self.assertEqual(session.request.call_count,2);self.assertEqual(len(events),1)
    def test_stop_prevents_request(self):
        engine,session,stop,_=self.make([]);stop.set();engine.step();session.request.assert_not_called()
    def test_read_failure_propagates_without_retry(self):
        engine,session,stop,_=self.make([ValueError("Dados perdidos")])
        with self.assertRaisesRegex(ValueError,"Dados perdidos"):engine.step()
        self.assertEqual(session.request.call_count,1)
    def test_default_collection_has_no_cloak_actions(self):
        stop=Stop();session=Mock()
        self.assertIsNone(DataCollector(session,stop,lambda *args:None).cloak)
        self.assertIsNotNone(DataCollector(session,stop,lambda *args:None,settings={"cloak":True}).cloak)
    def test_attack_and_jump_only_wait(self):
        for action in ("combat","jump","active","dead"):
            engine,session,stop,events=self.make([dict(action=action)])
            engine.step();self.assertIsNone(engine.pending);self.assertEqual(len(events),1)
