import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pet_collection import PetCollector,approach_point

class PetCollectionTests(unittest.TestCase):
    def make(self):
        session=Mock();stop=Mock();stop.is_set.return_value=False
        session.request.return_value=dict(action='ready',owner='p',life=1,map='1-1',configuration=1,active=True,mode='petal1')
        engine=PetCollector(session,stop,Mock())
        snap=dict(fresh=True,dead=False,hp_percent=100,map='1-1',respawn_revision=1,position=(100,100),map_size=(2000,2000),
                  candidates=[dict(id='b',revision=1,x=1000,y=100,kind='bonus')])
        return engine,session,snap
    def test_approaches_without_ship_collection_and_stops_for_pet(self):
        e,s,snap=self.make();e.step(snap,0)
        moves=[c.args[1] for c in s.request.call_args_list if c.args[1]['action']=='move']
        self.assertEqual(len(moves),1);self.assertEqual((moves[0]['x'],moves[0]['y']),(650,100))
        self.assertTrue(all(c.args[0]=='pet_collect' for c in s.request.call_args_list))
        snap['position']=(600,100);e.step(snap,1)
        self.assertEqual(s.request.call_args.args[1]['action'],'stop')
        e.step(snap,22);self.assertIsNone(e.target);self.assertIn(('b',1),e.deferred)
    def test_disappearance_is_not_claimed_as_pet_reward(self):
        e,s,snap=self.make();e.step(snap,0);snap['candidates']=[];e.step(snap,1)
        self.assertIsNone(e.target)
        self.assertFalse(any(c.args[0]=='confirmed' for c in e.emit.call_args_list))
    def test_no_green_and_no_stale_or_dead_flight(self):
        e,s,snap=self.make();snap['candidates'][0]['kind']='booty';e.step(snap,0)
        self.assertFalse(any(c.args[1]['action']=='move' for c in s.request.call_args_list))
        for change in (dict(fresh=False),dict(dead=True),dict(hp_percent=25)):
            with self.assertRaises(ValueError):e.step(dict(snap,**change),1)
    def test_pending_launch_is_never_repeated(self):
        e,s,snap=self.make();s.request.return_value=dict(action='sent',owner='p',life=1,map='1-1',configuration=1,expected_active=True)
        e.step(snap,0);s.request.return_value=dict(action='snapshot',active=False)
        e.step(snap,1)
        self.assertEqual(s.request.call_args.args[1]['action'],'inspect')
        with self.assertRaisesRegex(ValueError,'sem confirmação'):e.step(snap,15)
    def test_changed_life_blocks_before_browser_request(self):
        e,s,snap=self.make();e.step(snap,0);s.reset_mock()
        with self.assertRaises(ValueError):e.step(dict(snap,respawn_revision=2),1)
        s.request.assert_not_called()
    def test_edge_waypoint_and_unknown_bounds(self):
        p=approach_point((0,100),dict(x=10,y=100),(0,0,1000,1000))
        self.assertAlmostEqual(__import__('math').dist(p,(10,100)),350)
        self.assertTrue(0<=p[0]<=1000 and 0<=p[1]<=1000)
        with self.assertRaises(ValueError):approach_point((0,0),dict(x=10,y=10),None)
