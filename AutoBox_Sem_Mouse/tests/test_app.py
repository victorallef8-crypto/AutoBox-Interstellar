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
        modules={"cv2":types.ModuleType("cv2"),"numpy":types.ModuleType("numpy"),
                 "PIL":types.ModuleType("PIL"),"pynput":types.ModuleType("pynput"),
                 "collector":types.ModuleType("collector")}
        modules["PIL"].Image=Mock(); modules["PIL"].ImageTk=Mock()
        modules["pynput"].keyboard=keyboard; modules["collector"].Collector=Mock()
        spec=importlib.util.spec_from_file_location("standalone_app",ROOT/"AutoBox_Sem_Mouse.py")
        cls.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,modules):
            spec.loader.exec_module(cls.module)
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT.parents[2])
        cls.module.APP_DIR=Path(cls.temp.name)
        cls.module.CONFIG_PATH=Path(cls.temp.name)/"config.json"
        cls.module.MODEL_PATH=Path(cls.temp.name)/"box.png"
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
    def test_calibration_labels_show_required_and_optional_steps(self):
        self.assertEqual(self.app.area_labels["map"].get(),"Falta calibrar")
        self.assertEqual(self.app.area_labels["ship"].get(),"Falta calibrar")
        self.assertEqual(self.app.area_labels["notice"].get(),"Opcional")
    def test_settings_persist_in_standalone_directory(self):
        self.app.threshold.set("0.91"); self.assertTrue(self.app.save())
        value=json.loads(self.module.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(value["threshold"],.91)
    def test_invalid_threshold_is_rejected(self):
        self.app.threshold.set("1.1"); self.assertFalse(self.app.save())
        self.app.threshold.set("0.9")
    def test_start_requires_dedicated_session(self):
        self.app.start()
        self.assertIn("Abra a sessao dedicada",self.app.status.get())
        self.assertIsNone(self.app.worker)
    def test_pause_cancels_clicks(self):
        self.app.stop_event.clear(); self.app.pause()
        self.assertTrue(self.app.stop_event.is_set())
    def test_area_bounds_validation(self):
        viewport={"width":1280,"height":720}
        self.assertTrue(self.module.valid_area({"left":0,"top":0,"width":500,"height":300},viewport))
        self.assertFalse(self.module.valid_area({"left":1200,"top":0,"width":500,"height":300},viewport))
        self.assertFalse(self.module.valid_area(None,viewport))

if __name__=="__main__": unittest.main()
