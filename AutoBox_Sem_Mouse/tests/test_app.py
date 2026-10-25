import importlib.util
import json
import sys
import tempfile
import tkinter as tk
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        keyboard=types.SimpleNamespace(Key=types.SimpleNamespace(f8="f8",f9="f9",f10="f10"),
                                       Listener=Mock(return_value=Mock()))
        modules={"pynput":types.ModuleType("pynput")}
        modules["pynput"].keyboard=keyboard
        spec=importlib.util.spec_from_file_location("standalone_app",ROOT/"AutoBox_Sem_Mouse.py")
        cls.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,modules):
            spec.loader.exec_module(cls.module)
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT.parents[2])
        cls.module.APP_DIR=Path(cls.temp.name)
        cls.module.CONFIG_PATH=Path(cls.temp.name)/"config.json"
        cls.root=tk.Tk(); cls.root.withdraw()
        cls.app=cls.module.AutoBoxSemMouse(cls.root); cls.root.update()
    @classmethod
    def tearDownClass(cls):
        cls.app.listener.stop()
        for timer in cls.root.tk.call("after","info"):
            cls.root.after_cancel(timer)
        cls.root.destroy(); cls.temp.cleanup()

    def test_standalone_starts_without_old_app_import(self):
        self.assertIn("AutoBox Sem Mouse",self.root.title())
        self.assertNotIn("AutoBox_Interstellar",sys.modules)
    def test_settings_persist_in_standalone_directory(self):
        self.app.max_deaths.set("5"); self.assertTrue(self.app.save())
        value=json.loads(self.module.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(value["max_deaths"],5)
        self.assertNotIn("collection_mode",value)
    def test_start_requires_dedicated_session(self):
        self.app.start()
        self.assertIn("Abra a sessao dedicada",self.app.status.get())
        self.assertIsNone(self.app.worker)
    def test_data_start_does_not_require_image_calibration(self):
        previous=self.app.worker
        self.app.session.ready.set()
        try:
            with patch.object(self.app.session,"get_world_snapshot",return_value={"fresh":True,"hp_percent":80}), patch.object(self.module,"DataCollector") as engine, patch.object(self.module.threading,"Thread") as thread:
                self.app.start()
                engine.assert_called_once()
                thread.return_value.start.assert_called_once()
                self.assertIn("Coleta por dados iniciada",self.app.status.get())
        finally:
            self.app.worker=previous
            self.app.stop_event.set(); self.app.session.ready.clear()

    def test_data_start_requires_live_reading(self):
        self.app.session.ready.set()
        try:
            with patch.object(self.app.session,"get_world_snapshot",return_value={"fresh":False}), patch.object(self.module,"DataCollector") as engine:
                self.app.start()
                engine.assert_not_called()
                self.assertIn("Aguarde a leitura ao vivo",self.app.status.get())
        finally:
            self.app.session.ready.clear()

    def test_legacy_configuration_cannot_enable_image_collection(self):
        self.app.cfg.update(collection_mode="Imagem (anterior)",threshold=.9,map={"left":0})
        self.assertTrue(self.app.save())
        self.assertNotIn("collection_mode",self.app.cfg)
        self.assertNotIn("map",self.app.cfg)
        self.assertFalse(hasattr(self.app,"calibrate"))
        self.assertNotIn("collection",self.app.pages)

    def test_pause_cancels_clicks(self):
        self.app.stop_event.clear(); self.app.pause()
        self.assertTrue(self.app.stop_event.is_set())
    def test_only_implemented_modes_are_available(self):
        self.assertEqual(len(self.app.notebook.tabs()),4)
        for key in ("dashboard","data","combat","advanced"):
            self.assertEqual(self.app.notebook.tab(self.app.pages[key],"state"),"normal")
        self.assertIn("combat",self.app.pages)

    def test_data_tab_contains_status_fields_and_diagnostic_buttons(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        widgets=list(descendants(self.app.pages["data"]))+list(descendants(self.app.pages["diagnostics"]))
        texts=[str(w.cget("text")) for w in widgets if "text" in w.keys()]
        self.assertIn("Registrar uma coleta manual (30 segundos)",texts)
        self.assertIn("Copiar diagnóstico da coleta",texts)
        self.assertIn("Exportar integração do cliente",texts)
        bindings=[str(w.cget("textvariable")) for w in widgets if "textvariable" in w.keys()]
        for variable in self.app.world_vars.values():
            self.assertIn(str(variable),bindings)

    def test_kill_npc_page_has_manual_recording_and_separate_destination(self):
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        texts=[str(w.cget("text")) for w in descendants(self.app.pages["combat"]) if "text" in w.keys()]
        self.assertIn("Registrar luta manual (90 segundos)",texts)
        self.assertIn("Copiar diagnóstico da luta",texts)
        self.assertIn("Ir ao mapa",texts)
        self.assertIsNot(self.app.collect_map,self.app.npc_map)
        self.assertFalse(any("Iniciar combate" in text for text in texts))

    def test_destination_settings_are_independent_and_invalid_map_is_rejected(self):
        previous=(self.app.collect_map.get(),self.app.npc_map.get())
        try:
            self.app.collect_map.set("1-2"); self.app.npc_map.set("4-3")
            self.assertTrue(self.app.save())
            self.assertEqual(self.app.cfg["collect_map"],"1-2")
            self.assertEqual(self.app.cfg["npc_map"],"4-3")
            self.app.npc_map.set("https://example.com")
            self.assertFalse(self.app.save())
        finally:
            self.app.collect_map.set(previous[0]); self.app.npc_map.set(previous[1])
            self.app.save()

    def test_active_time_excludes_pauses_and_repeated_start_events(self):
        previous=(self.app.running,self.app.active_started,self.app.active_elapsed)
        self.app.running=False; self.app.active_elapsed=0
        try:
            with patch.object(self.module.time,"monotonic",side_effect=[10,12,17.5,100,104]):
                self.app._set_running(True)
                self.app._set_running(True)
                self.app._set_running(False)
                self.app._set_running(True)
                self.app._set_running(False)
            self.assertEqual(self.app.active_elapsed,11.5)
            self.assertFalse(self.app.running)
        finally:
            self.app.running,self.app.active_started,self.app.active_elapsed=previous

    def test_dashboard_displays_event_counters(self):
        previous=(self.app.attempts,self.app.confirmed,self.app.failed)
        try:
            self.app.attempts=9; self.app.confirmed=3; self.app.failed=2
            self.app._update_panel()
            self.assertEqual(self.app.counter_vars["attempts"].get(),"9")
            self.assertEqual(self.app.counter_vars["confirmed"].get(),"3")
            self.assertEqual(self.app.counter_vars["failed"].get(),"2")
            self.assertEqual(self.app.session_label.get(),"Opera desconectado")
        finally:
            self.app.attempts,self.app.confirmed,self.app.failed=previous
            self.app._update_panel()

    def test_stale_world_data_clears_previous_target(self):
        previous=self.app.last_world_refresh
        self.app.world_vars["nearest"].set("old-target")
        self.app.last_world_refresh=-100
        self.app._update_world_panel()
        self.assertEqual(self.app.world_vars["nearest"].get(),"—")
        self.assertIn("Abra o Opera",self.app.world_vars["status"].get())
        self.app.last_world_refresh=previous

if __name__=="__main__": unittest.main()
