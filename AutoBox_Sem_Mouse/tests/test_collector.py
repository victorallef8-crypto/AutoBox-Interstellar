import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class Clock:
    def __init__(self): self.now=0
    def monotonic(self): return self.now

class Stop:
    def __init__(self,clock): self.clock=clock; self.value=False; self.steps=0
    def is_set(self): return self.value
    def set(self): self.value=True
    def wait(self,seconds):
        self.clock.now+=seconds; self.steps+=1
        if self.steps>65: self.value=True

class Frame:
    def __init__(self,w=1280,h=720,left=0,top=0): self.shape=(h,w,3); self.left=left; self.top=top
    def __getitem__(self,slices):
        ys,xs=slices
        return Frame(xs.stop-xs.start,ys.stop-ys.start,self.left+xs.start,self.top+ys.start)
    def copy(self): return self

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock(); self.stop=Stop(self.clock); self.events=[]; self.clicks=[]
        self.point=lambda: ((900-min(self.clock.now,4)*100,300) if self.clock.now<4.3 else None)
        def locate(frame,sample,threshold):
            point=self.point()
            if point and frame.left<=point[0]<frame.left+frame.shape[1] and frame.top<=point[1]<frame.top+frame.shape[0]:
                return [(point[0]-frame.left,point[1]-frame.top,.99)]
            return []
        vision=types.ModuleType("vision")
        vision.locate_boxes=locate
        vision.new_reward_message=Mock(return_value=False)
        vision.radiation_visible=Mock(return_value=False)
        vision.find_death_panel=Mock(return_value=None)
        self.vision=vision
        spec=importlib.util.spec_from_file_location("isolated_collector",Path(__file__).resolve().parents[1]/"collector.py")
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{"vision":vision}):
            spec.loader.exec_module(self.module)
        self.module.time=self.clock
        def request(operation,payload=None,allowed=None):
            if operation=="screenshot": return b"frame"
            if allowed is not None and not allowed(): return False
            self.clicks.append(payload); return True
        self.session=types.SimpleNamespace(ready=types.SimpleNamespace(is_set=lambda:True),
            viewport={"width":1280,"height":720},request=Mock(side_effect=request))
        self.config={"map":{"left":0,"top":0,"width":1000,"height":600},
                     "ship":{"left":480,"top":280,"width":40,"height":40},"threshold":.9}
        self.bot=self.module.Collector(self.session,self.config,object(),self.stop,
            lambda event,data:self.events.append((event,data)),lambda data:Frame())
    def test_full_cycle_keeps_same_target_and_releases_near_ship(self):
        self.bot.run()
        attempts=[event for event,data in self.events if event=="attempt"]
        self.assertEqual(len(attempts),1)
        self.assertTrue(any(event=="departed" for event,data in self.events))
        self.assertTrue(all(point[1]==300 for point in self.clicks))
        self.assertTrue(all(a[0]>=b[0] for a,b in zip(self.clicks,self.clicks[1:])))
        self.assertLessEqual(len(self.clicks),6)
    def test_pause_prevents_any_click(self):
        self.stop.set(); self.bot.run()
        self.assertEqual(self.clicks,[])
    def test_failed_browser_stops_cleanly(self):
        self.session.request.side_effect=RuntimeError("browser closed")
        self.bot.run()
        self.assertTrue(self.stop.is_set())
        self.assertTrue(any(event=="status" and "browser closed" in data for event,data in self.events))
    def test_danger_pauses_without_navigation(self):
        self.vision.radiation_visible.return_value=True
        self.bot.run()
        self.assertEqual(self.clicks,[])
    def test_reward_counts_separately_from_attempt(self):
        self.config["notice"]={"left":0,"top":0,"width":120,"height":30}
        self.point=lambda: ((900-min(self.clock.now,3)*100,300) if self.clock.now<3.3 else None)
        self.vision.new_reward_message.side_effect=lambda before,after:self.clock.now>=3
        self.bot=self.module.Collector(self.session,self.config,object(),self.stop,
            lambda event,data:self.events.append((event,data)),lambda data:Frame())
        self.bot.run()
        self.assertEqual(sum(event=="confirmed" for event,data in self.events),1)
    def test_no_minimap_config_never_sends_patrol_click(self):
        self.point=lambda:None; self.bot.run()
        self.assertEqual(self.clicks,[])
    def test_bad_calibration_stops_before_click(self):
        self.bot.config["map"]={"left":1200,"top":0,"width":1000,"height":600}
        self.bot.run()
        self.assertEqual(self.clicks,[])
        self.assertTrue(any(event=="status" and "fora da imagem" in data for event,data in self.events))

if __name__=="__main__": unittest.main()
