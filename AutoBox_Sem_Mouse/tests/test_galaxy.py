import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import GalaxyWorker
from test_npc_test import Stop

class GalaxyTests(unittest.TestCase):
    def test_one_batch_at_a_time_and_total_limit(self):
        stop=Stop(); calls=[]
        class Session:
            def request(self,op,payload,allowed):
                calls.append(payload)
                return {"action":"state","revision":2} if payload["action"]=="inspect" else {"action":"sent","revision":1,"count":5}
        worker=GalaxyWorker(Session(),stop,lambda *e:None,{"limit":5},clock=lambda:stop.now)
        worker.run()
        self.assertEqual(worker.used,5)
        self.assertEqual([c["action"] for c in calls],["spin","inspect"])
    def test_missing_ack_does_not_repeat_spending(self):
        stop=Stop();calls=[];messages=[]
        class Session:
            def request(self,op,payload,allowed):
                calls.append(payload)
                return {"action":"state","revision":1} if payload["action"]=="inspect" else {"action":"sent","revision":1,"count":5}
        worker=GalaxyWorker(Session(),stop,lambda e,d:messages.append(d),{"limit":10},clock=lambda:stop.now)
        worker.run()
        self.assertEqual(sum(c["action"]=="spin" for c in calls),1)
        self.assertTrue(any("sem confirmação" in m for m in messages))
