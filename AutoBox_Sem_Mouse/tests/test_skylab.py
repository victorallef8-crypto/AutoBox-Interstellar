import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import SkylabWorker
import test_app

def snapshot(level=1,reason="pronto",revision=1,job=None):
    return dict(action="snapshot",owner="test",life=1,revision=revision,rows=[
        dict(id="basic",name="Básico",level=level,max=20,reason=reason,job=job,remaining=10 if job else 0)])
class Stop:
    def __init__(self):self.now=0;self.stopped=False
    def is_set(self):return self.stopped
    def set(self):self.stopped=True
    def wait(self,seconds):self.now+=seconds;return self.stopped
class Session:
    def __init__(self,stop,snapshots):
        self.stop=stop;self.snapshots=list(snapshots);self.calls=[]
    def request(self,op,payload,allowed):
        if not allowed():return False
        self.calls.append((op,payload))
        if payload["action"]=="upgrade":return dict(action="sent")
        if not self.snapshots:self.stop.set();return snapshot()
        return copy.deepcopy(self.snapshots.pop(0))
class SkylabTests(unittest.TestCase):
    def run_worker(self,frames):
        stop=Stop();session=Session(stop,frames);events=[]
        worker=SkylabWorker(session,stop,lambda e,d:events.append((e,d)),clock=lambda:stop.now)
        worker.run()
        return session,events
    def test_confirmed_job_waits_and_completed_levels_finish(self):
        session,events=self.run_worker([snapshot(),snapshot(revision=2,job=dict(level=2)),snapshot(reason="construindo",revision=2,job=dict(level=2)),snapshot(level=20,reason="concluido",revision=3)])
        upgrades=[p for _,p in session.calls if p["action"]=="upgrade"]
        self.assertEqual(len(upgrades),1)
        self.assertTrue(any("Construção confirmada" in d for e,d in events if e=="skylab_status"))
        self.assertIn("atingiram",events[-1][1])
    def test_no_resources_or_active_job_never_sends(self):
        for frame in (snapshot(reason="creditos"),snapshot(reason="minerios"),snapshot(reason="energia"),snapshot(reason="modulo_basico"),snapshot(reason="construindo",job=dict(level=2))):
            session,_=self.run_worker([frame])
            self.assertFalse(any(p["action"]=="upgrade" for _,p in session.calls))
    def test_unknown_outcome_stops_without_repeating(self):
        session,events=self.run_worker([snapshot() for _ in range(25)])
        self.assertEqual(sum(p["action"]=="upgrade" for _,p in session.calls),1)
        self.assertIn("sem confirmação",events[-1][1])
    def test_other_revision_does_not_confirm_purchase(self):
        session,events=self.run_worker([snapshot()]+[snapshot(revision=2) for _ in range(25)])
        self.assertEqual(sum(p["action"]=="upgrade" for _,p in session.calls),1)
        self.assertIn("sem confirmação",events[-1][1])
    def test_account_change_stops(self):
        changed=snapshot();changed["owner"]="other"
        _,events=self.run_worker([snapshot(reason="creditos"),changed])
        self.assertIn("Conta ou vida mudou",events[-1][1])
    def test_disconnection_stops(self):
        stop=Stop();events=[];session=Mock();session.request.side_effect=ValueError("Dados desconectados")
        SkylabWorker(session,stop,lambda e,d:events.append(d)).run()
        self.assertTrue(stop.is_set());self.assertIn("Dados desconectados",events[-1])
    def test_cancelled_before_start_never_sends(self):
        stop=Stop();stop.set();session=Mock()
        SkylabWorker(session,stop,lambda *args:None).run()
        session.request.assert_not_called()
    def test_invalid_settings(self):
        for kwargs in (dict(target=21),dict(reserve=-1),dict(target=True)):
            with self.assertRaises(ValueError):SkylabWorker(None,None,None,**kwargs)

class SkylabUiTests(unittest.TestCase):
    setUpClass=classmethod(test_app.AppTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.AppTests.tearDownClass.__func__)
    def test_start_disconnected_and_stop_all(self):
        self.app.start_skylab()
        self.assertIn("Abra o jogo",self.app.skylab_status.get())
        self.assertIsNone(self.app.skylab_worker)
        self.app.skylab_stop.clear();self.app.stop_all();self.assertTrue(self.app.skylab_stop.is_set())
    def test_rows_and_countdown(self):
        self.app.update_skylab_rows(snapshot(job=dict(level=2))["rows"])
        values=self.app.skylab_table.item("basic","values")
        self.assertEqual(values[1],"1/20");self.assertIn("10s",values[-1])
    def test_repeated_start_keeps_one_worker(self):
        old=self.app.skylab_worker
        self.app.skylab_worker=Mock();self.app.skylab_worker.is_alive.return_value=True
        try:
            with patch.object(self.module.threading,"Thread") as thread:
                self.app.start_skylab();self.app.start_skylab();thread.assert_not_called()
        finally:self.app.skylab_worker=old
