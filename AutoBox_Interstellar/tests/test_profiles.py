"""Abas reais de Tk com captura, mouse e atalhos substituidos por simulacoes."""
import ast
import json
import os
import queue
import random
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / "AutoBox_Interstellar.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
NODES = [n for n in TREE.body if
         (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROFILES"
                                           for t in n.targets)) or
         (isinstance(n, ast.FunctionDef) and n.name == "profile_paths") or
         (isinstance(n, ast.ClassDef) and n.name in ("AutoBoxApp", "AutoBoxWindow"))]

class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[4])
        cls.folder = Path(cls.temp.name)
        old_config = {"title": "Interstellar Verse", "wait": 6.5, "region": {
            "left": 10, "top": 20, "width": 500, "height": 400}}
        (cls.folder / "config.json").write_text(json.dumps(old_config), encoding="utf-8")
        (cls.folder / "box_modelo.png").write_bytes(b"existing-template")
        cls.mouse = SimpleNamespace(click=Mock(), moveTo=Mock(), mouseDown=Mock(), mouseUp=Mock(), failSafeCheck=Mock())
        cls.listener = Mock()
        cls.keyboard = SimpleNamespace(Key=SimpleNamespace(f8="f8", f9="f9", f10="f10"),
                                       Listener=Mock(return_value=cls.listener))
        cls.ns = dict(tk=tk, ttk=ttk, Path=Path, APP_NAME="AutoBox", APP_DIR=cls.folder,
                      json=json, os=os, queue=queue, random=random, threading=threading,
                      time=time, pyautogui=cls.mouse, keyboard=cls.keyboard,
                      messagebox=Mock(), REPAIR_COSTS={"base": 0, "portal": 250, "same_place": 500},
                      REPAIR_LABELS={"base": "base", "portal": "portal", "same_place": "mesmo lugar"},
                      active_window_title=lambda: "Krypton",
                      updater=SimpleNamespace(check_for_update=lambda: None),
                      send_windows_click=Mock(return_value=True))
        exec(compile(ast.fix_missing_locations(ast.Module(body=NODES, type_ignores=[])),
                     str(SOURCE), "exec"), cls.ns)
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.window = cls.ns["AutoBoxWindow"](cls.root)
        cls.root.update()
        cls.interstellar, cls.krypton = cls.window.apps.values()

    @classmethod
    def tearDownClass(cls):
        cls.window._close()
        cls.temp.cleanup()

    def setUp(self):
        self.window.stop_all()
        self.krypton.input_method = "windows"
        self.ns["send_windows_click"].reset_mock()
        self.window.notebook.select(0)
        self.root.update()
        for name in ("click", "moveTo", "mouseDown", "mouseUp"):
            getattr(self.mouse, name).reset_mock()

    def test_two_real_tabs_and_one_keyboard_listener(self):
        tabs = self.window.notebook.tabs()
        self.assertEqual([self.window.notebook.tab(t, "text") for t in tabs], ["Interstellar", "Krypton"])
        self.keyboard.Listener.assert_called_once()

    def test_legacy_interstellar_config_and_template_preserved(self):
        self.assertEqual(self.interstellar.settings_path, self.folder / "config.json")
        self.assertEqual(self.interstellar.wait_seconds, 6.5)
        self.assertEqual(self.interstellar.template_path.read_bytes(), b"existing-template")
        self.assertIsNotNone(self.interstellar.region)

    def test_krypton_starts_without_interstellar_calibration(self):
        self.assertIsNone(self.krypton.region)
        self.assertFalse(self.krypton.template_path.exists())
        self.assertEqual(self.krypton.title_required, "krypton")
        self.assertEqual(self.krypton.click_hold, .12)
        self.assertFalse(self.krypton.auto_revive)

    def test_saving_krypton_does_not_overwrite_interstellar(self):
        original = self.interstellar.settings_path.read_bytes()
        self.krypton.wait_var.set("4.5")
        self.assertTrue(self.krypton.apply_settings(silent=True))
        saved = json.loads(self.krypton.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["wait"], 4.5)
        self.assertEqual(self.interstellar.settings_path.read_bytes(), original)
        self.assertNotEqual(self.krypton.template_path, self.interstellar.template_path)

    def test_tab_change_stops_both_profiles(self):
        self.interstellar.running = True
        self.window.notebook.select(1)
        self.root.update()
        self.assertIs(self.window.active_app, self.krypton)
        self.assertFalse(self.interstellar.running)
        self.assertFalse(self.krypton.running)
        self.assertTrue(self.interstellar.exit_event.is_set())

    def test_inactive_profile_cannot_click(self):
        self.interstellar.running = True
        self.interstellar.stopped = False
        self.window.notebook.select(1)
        self.root.update()
        self.interstellar.running = True
        self.assertFalse(self.interstellar._ready_to_click())
        self.assertFalse(self.interstellar._game_click(200, 300))
        self.mouse.click.assert_not_called()

    def test_krypton_sends_one_left_press_and_release(self):
        self.krypton.input_method = "standard"
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.running = True
        self.krypton.stopped = False
        self.krypton.exit_event.clear()
        self.assertTrue(self.krypton._game_click(200, 300))
        self.mouse.mouseDown.assert_called_once_with(button="left")
        self.mouse.mouseUp.assert_called_once_with(button="left")
        self.mouse.click.assert_not_called()
        self.assertGreaterEqual(self.krypton.click_hold, .1)

    def test_mouse_released_when_wait_raises(self):
        self.krypton.input_method = "standard"
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.running = True
        self.krypton.stopped = False
        original = self.krypton._sleep_interruptible
        self.krypton._sleep_interruptible = Mock(side_effect=RuntimeError("interrupted"))
        try:
            with self.assertRaises(RuntimeError):
                self.krypton._game_click(200, 300)
            self.mouse.mouseUp.assert_called_once_with(button="left")
        finally:
            self.krypton._sleep_interruptible = original

    def test_restart_waits_for_other_worker_to_exit(self):
        self.interstellar.worker = Mock(is_alive=Mock(return_value=True))
        self.window.notebook.select(1)
        self.root.update()
        try:
            self.assertFalse(self.window.prepare_start(self.krypton))
            self.assertTrue(self.interstellar.exit_event.is_set())
        finally:
            self.interstellar.worker = None

    def test_hotkeys_only_queue_command_on_selected_tab(self):
        for app in self.window.apps.values():
            while not app.events.empty():
                app.events.get_nowait()
        self.window.notebook.select(1)
        self.root.update()
        callback = self.keyboard.Listener.call_args.kwargs["on_press"]
        callback("f8")
        self.assertEqual(self.krypton.events.get_nowait(), ("command", "start"))
        self.assertTrue(self.interstellar.events.empty())

    def test_interstellar_uses_existing_immediate_click(self):
        original = self.ns["active_window_title"]
        self.ns["active_window_title"] = lambda: "Interstellar Verse"
        try:
            self.interstellar.running = True
            self.interstellar.stopped = False
            self.assertTrue(self.interstellar._game_click(200, 300))
            self.mouse.click.assert_called_once_with(200, 300)
            self.mouse.mouseDown.assert_not_called()
        finally:
            self.ns["active_window_title"] = original

    def test_krypton_uses_windows_method_by_default(self):
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.running = True
        self.krypton.stopped = False
        self.krypton.exit_event.clear()
        self.assertTrue(self.krypton._game_click(200, 300))
        self.ns["send_windows_click"].assert_called_once()
        self.assertEqual(self.ns["send_windows_click"].call_args.args[:3], (200, 300, .12))
        self.mouse.click.assert_not_called()
        self.mouse.mouseDown.assert_not_called()

    def test_test_mode_checks_title_and_stays_stopped(self):
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.input_test_cancel.clear()
        self.assertFalse(self.krypton.running)
        self.assertTrue(self.krypton._game_click(200, 300, test=True))
        self.assertFalse(self.krypton.running)
        self.ns["send_windows_click"].assert_called_once()

    def test_pause_cancels_pending_click_test(self):
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.input_test_cancel.clear()
        self.krypton.pause()
        self.assertFalse(self.krypton._game_click(200, 300, test=True))
        self.ns["send_windows_click"].assert_not_called()

    def test_wrong_window_blocks_click_test(self):
        self.window.notebook.select(1)
        self.root.update()
        self.krypton.input_test_cancel.clear()
        original = self.ns["active_window_title"]
        self.ns["active_window_title"] = lambda: "Outro aplicativo"
        try:
            self.assertFalse(self.krypton._game_click(200, 300, test=True))
            self.ns["send_windows_click"].assert_not_called()
        finally:
            self.ns["active_window_title"] = original

    def test_krypton_requires_ship_calibration_before_start(self):
        self.window.notebook.select(1)
        self.root.update()
        old_region, old_template, old_ship = self.krypton.region, self.krypton.template_path, self.krypton.ship_region
        self.krypton.region = {"left": 0, "top": 0, "width": 500, "height": 400}
        self.krypton.template_path = Mock(exists=Mock(return_value=True))
        self.krypton.ship_region = None
        self.ns["messagebox"].reset_mock()
        try:
            self.krypton.start()
            self.assertFalse(self.krypton.running)
            self.ns["messagebox"].showinfo.assert_called_once()
            self.assertEqual(self.ns["messagebox"].showinfo.call_args.args[0], "Marcar a nave")
        finally:
            self.krypton.region, self.krypton.template_path, self.krypton.ship_region = old_region, old_template, old_ship

    def test_ship_calibration_is_saved_only_in_krypton_profile(self):
        old_ship, old_region = self.krypton.ship_region, self.krypton.region
        original = self.interstellar.settings_path.read_bytes()
        try:
            self.krypton.region = {"left": 0, "top": 0, "width": 500, "height": 400}
            self.krypton.ship_region = {"left": 80, "top": 60, "width": 60, "height": 60}
            self.assertTrue(self.krypton._ship_area_valid(self.krypton.region))
            self.assertEqual(self.krypton._ship_center(self.krypton.region), (110, 90))
            self.krypton._save_config()
            saved = json.loads(self.krypton.settings_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["ship_region"], self.krypton.ship_region)
            self.assertEqual(self.interstellar.settings_path.read_bytes(), original)
        finally:
            self.krypton.ship_region, self.krypton.region = old_ship, old_region

    def test_invalid_profile_path_rejected(self):
        with self.assertRaises(ValueError):
            self.ns["profile_paths"]("../other")

    def test_krypton_never_enables_interstellar_paid_revive(self):
        self.krypton.auto_revive_var.set(True)
        self.krypton.revive_target_var.set("portal")
        self.assertTrue(self.krypton.apply_settings(silent=True))
        self.assertFalse(self.krypton.auto_revive)

if __name__ == "__main__":
    unittest.main()
