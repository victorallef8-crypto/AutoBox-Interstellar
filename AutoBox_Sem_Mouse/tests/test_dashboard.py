import json
import threading
import time
import types
import unittest
from unittest.mock import Mock,patch
import test_app
from browser_session import WorldFeed
from test_world_feed import snapshot
from controller import SessionEarnings

class DashboardTests(unittest.TestCase):
    setUpClass=classmethod(test_app.AppTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.AppTests.tearDownClass.__func__)
    def test_tabs_and_vitals_missing_zero_and_live(self):
        for key in ("dashboard","data","combat","galaxy","skylab","advanced"):
            self.app.notebook.select(self.app.pages[key]);self.root.update_idletasks()
        self.app._update_vitals(dict(fresh=True,hp_percent=75,shield_percent=25,map="3-2",boxes=4,position=(1,2)))
        self.assertEqual(self.app.vitals_bars["hp"]["value"],75)
        self.assertEqual(self.app.vitals_bars["shield"]["value"],25)
        self.app._update_vitals(dict(fresh=True,hp_percent=0,shield_percent=None))
        self.assertEqual(self.app.vitals_text["hp"].get(),"0.0%")
        self.assertEqual(self.app.vitals_text["shield"].get(),"Indisponível")
        self.app._update_vitals(dict(fresh=False))
        self.assertEqual(self.app.vitals_text["hp"].get(),"Indisponível")
    def test_finishing_pursuit_has_only_a_checkbox(self):
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        section=next(w for w in children(self.root) if w.winfo_class()=="TLabelframe" and w.cget("text")=="Perseguição para finalização")
        widgets=list(children(section))
        self.assertEqual(sum(w.winfo_class()=="TCheckbutton" for w in widgets),1)
        self.assertFalse(any(w.winfo_class() in ("TEntry","TSpinbox") for w in widgets))
        self.assertFalse(hasattr(self.app,"pursuit_fields"))

    def test_all_quick_buttons_are_bound(self):
        self.assertEqual(len(self.app.quick_buttons),6)
        for button in self.app.quick_buttons.values():self.assertTrue(button["command"])
    def test_repeated_start_during_shutdown_is_not_queued(self):
        old=self.app.worker;self.app.worker=Mock();self.app.worker.is_alive.return_value=True
        self.app.stop_event.set()
        try:
            with patch.object(self.root,"after") as after:
                self.app.quick_buttons[("collect","Iniciar")].invoke()
                self.app.quick_buttons[("collect","Iniciar")].invoke()
                after.assert_not_called()
        finally:self.app.worker=old
    def test_quick_pause_and_stop_preserve_independence(self):
        app=self.app;state=app.npc_state
        try:
            app.npc_state="running";app.npc_stop_event.clear();app.stop_event.clear()
            app.quick_buttons[("collect","Pausar")].invoke()
            self.assertTrue(app.stop_event.is_set());self.assertFalse(app.npc_stop_event.is_set())
            app.stop_event.clear();app.quick_buttons[("npc","Pausar")].invoke()
            self.assertFalse(app.stop_event.is_set());self.assertTrue(app.npc_stop_event.is_set())
            self.assertEqual(app.npc_state,"paused")
            app.quick_buttons[("npc","Parar")].invoke()
            self.assertEqual(app.npc_state,"stopped")
        finally:
            app.stop_event.set();app.npc_stop_event.set();app.npc_state=state
    def test_recent_activity_is_bounded(self):
        for i in range(50):self.app.say("Evento "+str(i))
        text=self.app.log.get("1.0","end")
        self.assertLessEqual(len(text.strip().splitlines()),20)
        self.assertIn("Evento 49",text)
    def test_tk_heartbeat_remains_responsive_with_background_worker(self):
        done=threading.Event();worker=threading.Thread(target=lambda:done.wait(2),daemon=True);worker.start()
        heartbeat=[];self.root.after(10,lambda:heartbeat.append(True))
        try:
            deadline=time.monotonic()+.2
            while not heartbeat and time.monotonic()<deadline:self.root.update();time.sleep(.005)
            self.assertTrue(heartbeat);self.assertTrue(worker.is_alive())
        finally:done.set();worker.join()
    def test_function_keys_pause_only_collection(self):
        with patch.object(self.app,"pause") as pause,patch.object(self.app,"pause_npc") as npc,patch.object(self.app,"_update_panel"):
            self.app.events.put(("command","pause"));self.app._drain()
            pause.assert_called_once();npc.assert_not_called()

class DashboardDataTests(unittest.TestCase):
    def test_shield_percentage_uses_independent_maximum(self):
        feed=WorldFeed();feed.begin("s")
        for i,(shield,maximum,expected) in enumerate(((125,500,25),(0,500,0),(None,500,None),(100,0,None)),1):
            s=snapshot();s["me"].update(shield=shield,maxShield=maximum)
            feed.ingest("s",json.dumps(dict(transport="delta1",epoch="e",sequence=i,full=s)))
            self.assertEqual(feed.summary()["shield_percent"],expected)
            self.assertEqual(feed.summary()["hp_percent"],60)
    def test_rolling_hour_expires_during_pause_but_mean_uses_active_seconds(self):
        now=[0];e=SessionEarnings(clock=lambda:now[0]);e.observe(dict(fresh=True,rewards=[]),False)
        for t,key,kind in ((10,1,"box-collected"),(100,2,"kill")):
            now[0]=t;e.observe(dict(fresh=True,rewards=[dict(id=key,time=t,type=kind,field="uridium",amount=10,uridium=20)]),True)
        self.assertEqual(e.last_hour(),30)
        self.assertEqual(e.hourly(60),1800)
        now[0]=3610;self.assertEqual(e.last_hour(),20)
        now[0]=3700;self.assertEqual(e.last_hour(),0)
        self.assertEqual(e.hourly(60),1800)
