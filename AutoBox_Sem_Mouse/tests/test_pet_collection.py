import sys
import random
import math
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pet_collection import PetCollector,approach_point,random_patrol_point

class PetCollectionTests(unittest.TestCase):
    def make(self):
        session=Mock();stop=Mock();stop.is_set.return_value=False
        session.request.return_value=dict(action='ready',owner='p',life=1,map='1-1',configuration=1,active=True,mode='petal1')
        engine=PetCollector(session,stop,Mock(),rng=random.Random(1234))
        snap=dict(fresh=True,dead=False,hp_percent=100,map='1-1',respawn_revision=1,position=(100,100),map_size=(2000,2000),
                  candidates=[dict(id='b',revision=1,x=1000,y=100,kind='bonus')])
        return engine,session,snap
    def test_passes_box_without_stop_or_ship_collection(self):
        e,s,snap=self.make();e.step(snap,0)
        moves=[c.args[1] for c in s.request.call_args_list if c.args[1]['action']=='move']
        self.assertGreater(moves[0]['x'],1000)
        self.assertEqual(moves[0]['y'],100)
        snap['position']=(600,100);e.step(snap,1)
        self.assertEqual(e.target['id'],'b')
        snap['position']=(1050,100);e.step(snap,2)
        self.assertEqual(s.request.call_args.args[1]['action'],'cruise')
        self.assertFalse(any(c.args[1]['action']=='stop' for c in s.request.call_args_list))
        self.assertTrue(all(c.args[0]=='pet_collect' for c in s.request.call_args_list))
        waypoint=e.waypoint;snap['position']=waypoint;e.step(snap,1.5)
        self.assertNotEqual(e.waypoint,waypoint)
    def test_chooses_next_box_without_waiting(self):
        e,s,snap=self.make();snap['position']=(600,100)
        snap['candidates'].append(dict(id='c',revision=1,x=1400,y=100,kind='bonus'))
        e.step(snap,0);snap['position']=(1050,100);e.step(snap,1)
        self.assertEqual(e.target['id'],'c')
        self.assertFalse(any(c.args[1]['action']=='stop' for c in s.request.call_args_list))
    def test_visible_uncollected_box_never_becomes_orbit_or_wait(self):
        e,s,snap=self.make();snap['position']=(600,100);e.step(snap,0)
        snap['position']=(1050,100);s.reset_mock()
        for now in (0,1,8,30,120):
            e.step(snap,now)
            self.assertIsNone(e.target)
        commands=[c.args[1] for c in s.request.call_args_list if c.args[1]['action']!='ensure']
        self.assertTrue(commands)
        self.assertTrue(all(c['action']=='cruise' for c in commands))
        self.assertIn(('b',1),e.passed)
    def test_patrol_destination_changes_after_arrival(self):
        e,s,snap=self.make();snap['candidates']=[];snap['position']=(1000,100)
        e.step(snap,0)
        previous=e.patrol_goal;snap['position']=previous;e.step(snap,1)
        self.assertNotEqual(e.patrol_goal,previous)
        self.assertGreater(math.dist(previous,e.patrol_goal),500)
    def test_same_box_new_revision_can_be_considered_on_next_pass(self):
        e,s,snap=self.make();snap['position']=(600,100);e.step(snap,0)
        snap['position']=(1050,100);e.step(snap,.5)
        snap['position']=(100,100);snap['candidates'][0]['revision']=2;e.step(snap,1)
        self.assertEqual(e.target['revision'],2)
    def test_empty_area_keeps_flying_inside_map(self):
        e,s,snap=self.make();snap['candidates']=[];e.step(snap,0)
        self.assertEqual(s.request.call_args.args[1]['action'],'cruise')
        self.assertTrue(all(0<=v<=2000 for v in e.waypoint))
        previous=e.waypoint;snap['position']=previous;e.step(snap,.25)
        self.assertNotEqual(previous,e.waypoint)
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
    def test_border_box_is_skipped_without_turning_or_stopping(self):
        with self.assertRaises(ValueError):approach_point((1000,100),dict(x=1990,y=100),(0,0,2000,2000))
        e,session,snap=self.make();snap['position']=(1000,100);snap['candidates'][0]['x']=1990
        e.step(snap,0)
        self.assertIsNone(e.target)
        self.assertEqual(session.request.call_args.args[1]['action'],'cruise')
        with self.assertRaises(ValueError):approach_point((0,0),dict(x=10,y=10),None)
    def test_lookahead_accounts_for_reading_delay_and_speed(self):
        e,session,snap=self.make();snap['candidates']=[];snap['speed']=800;snap['age']=.4
        e.patrol_goal=(3500,100);e.patrol_size=(4000,4000)
        snap['map_size']=(4000,4000);snap['position']=(400,100)
        e.step(snap,0)
        self.assertGreater(e.waypoint[0],800)

    def test_flight_simulation_crosses_box_without_stopping_with_latency(self):
        import math
        e,session,snap=self.make();now=[0.0];e.clock=lambda:now[0]
        position=[200.0,1000.0];destination=[None];pending=[];history=[(0,tuple(position))]
        snap.update(map_size=(6000,4000),speed=600,age=.3)
        snap['candidates']=[dict(id='box',revision=1,x=1500,y=1000,kind='bonus')]
        def request(operation,payload,**kwargs):
            if payload['action'] in ('move','cruise'):
                pending.append((now[0]+.3,(payload['x'],payload['y'])))
            self.assertNotEqual(payload['action'],'stop')
            return dict(action='ready',owner='p',life=1,map='1-1',configuration=1,active=True,mode='petal1')
        session.request.side_effect=request
        stops=[];nearest=float('inf')
        for tick in range(251):
            now[0]=tick*.1
            for due,point in list(pending):
                if due<=now[0]+1e-8:destination[0]=point;pending.remove((due,point))
            if destination[0]:
                d=math.dist(position,destination[0]);step=min(d,60)
                if d>0:
                    position[:]=[position[i]+(destination[0][i]-position[i])*step/d for i in range(2)]
                if tick>10 and d<=60:stops.append(tick)
            history.append((now[0],tuple(position)))
            snap['position']=next(point for time,point in reversed(history) if time<=max(0,now[0]-.3)+1e-8)
            nearest=min(nearest,math.dist(position,(1500,1000)))
            e.step(snap,now[0])
        self.assertLess(nearest,61)
        self.assertEqual(stops,[])
        self.assertIn(('box',1),e.passed)

    def test_nearby_box_behind_map_heading_is_not_marked_as_passed(self):
        e,session,snap=self.make();snap['position']=(1000,1000)
        snap['candidates']=[dict(id='near',revision=1,x=800,y=1000,kind='bonus')]
        e.route=[(1000,1000),(1700,1000),(1700,1700)];e.route_size=(2000,2000)
        e.step(snap,0)
        self.assertEqual(e.target['id'],'near')
        self.assertNotIn(('near',1),e.passed)
    def test_gone_or_blocked_live_box_falls_back_to_route_immediately(self):
        for result in ('gone','blocked','passed'):
            e,session,snap=self.make()
            def reply(operation,payload,**kwargs):
                if payload['action']=='move':return dict(action=result)
                return dict(action='ready',owner='p',life=1,map='1-1',configuration=1)
            session.request.side_effect=reply
            e.step(snap,0)
            self.assertIsNone(e.target)
            self.assertEqual(session.request.call_args.args[1]['action'],'cruise')
    def test_diagnostic_retains_failure_after_worker_ends(self):
        from browser_session import BrowserSession
        session=BrowserSession('.',dict(width=800,height=600))
        session.record_pet_diagnostic('start')
        session.record_pet_diagnostic('move',result=dict(action='move'))
        session.record_pet_diagnostic('move',error='falha reproduzida')
        session.record_pet_diagnostic('end',result=dict(action='error'))
        report=session.get_manual_probe_report()['pet_collection']
        self.assertEqual(report['failure'],'falha reproduzida')
        self.assertEqual(report['movements'],1)
        self.assertEqual(report['last_result'],'error')

    def test_reported_boxes_beyond_old_range_override_patrol_nearest_first(self):
        e,session,snap=self.make()
        snap['map_size']=(6000,4000)
        snap['candidates']=[dict(id='far',revision=1,x=4500,y=1000,kind='bonus'),
                            dict(id='nearest',revision=1,x=3000,y=1000,kind='bonus')]
        e.step(snap,0)
        self.assertEqual(e.target['id'],'nearest')
        self.assertEqual(session.request.call_args.args[1]['action'],'cruise')
        self.assertEqual(e.flight_goal,(3000,1000))
        self.assertIsNone(e.patrol_goal)

    def test_crossing_heading_plane_far_to_side_does_not_discard_box(self):
        e,session,snap=self.make();snap['position']=(100,1000)
        snap['candidates'][0]['y']=1000;e.step(snap,0)
        snap['position']=(1100,1500);e.step(snap,1)
        self.assertNotIn(('b',1),e.passed)
        self.assertEqual(e.target['id'],'b')
        self.assertEqual(session.request.call_args.args[1]['action'],'move')

    def test_crossing_between_readings_counts_without_needing_sample_at_box(self):
        e,session,snap=self.make();snap['position']=(600,100);e.step(snap,0)
        snap['position']=(1400,100);e.step(snap,1)
        self.assertIn(('b',1),e.passed)
        self.assertIsNone(e.target)

    def test_blocked_nearest_box_does_not_hide_other_viable_boxes(self):
        e,session,snap=self.make();snap['position']=(1800,1000)
        snap['candidates']=[dict(id='edge',revision=1,x=1990,y=1000,kind='bonus'),
                            dict(id='safe',revision=1,x=1000,y=1000,kind='bonus')]
        e.step(snap,0)
        self.assertEqual(e.target['id'],'safe')
        self.assertEqual(session.request.call_args.args[1]['action'],'move')
        self.assertNotIn(('edge',1),e.passed)

    def test_known_target_stays_locked_when_closer_box_appears(self):
        e,session,snap=self.make();e.step(snap,0)
        snap['candidates'].append(dict(id='new',revision=1,x=200,y=100,kind='bonus'))
        snap['position']=(150,100);e.step(snap,1)
        self.assertEqual(e.target['id'],'b')

    def test_random_patrol_points_vary_in_both_axes_and_stay_inside_map(self):
        import math
        rng=random.Random(25);position=(3000,2000);points=[]
        for _ in range(30):
            point=random_patrol_point(position,(6000,4000),rng)
            self.assertTrue(250<=point[0]<=5750 and 250<=point[1]<=3750)
            self.assertGreater(math.dist(position,point),1500)
            points.append(point);position=point
        self.assertGreater(len({round(p[0]) for p in points}),25)
        self.assertGreater(len({round(p[1]) for p in points}),25)
        self.assertNotEqual(points[0],random_patrol_point((3000,2000),(6000,4000),random.Random(26)))
        for size in ((0,100),(100,float('nan')),(-1,100)):
            with self.assertRaises(ValueError):random_patrol_point(position,size,rng)

    def test_wave_is_stable_curved_and_returns_to_direct_final_approach(self):
        e,session,snap=self.make();size=(10000,6000);goal=(8500,3000)
        points=[e.flight_point((x,3000),goal,size,350) for x in range(500,7001,500)]
        offsets=[point[1]-3000 for point in points]
        self.assertGreater(max(offsets),20)
        self.assertLess(min(offsets),-20)
        self.assertEqual(e.flight_point((7000,3000),goal,size,350)[1],3000)
        self.assertTrue(all(40<=p[0]<=9960 and 40<=p[1]<=5960 for p in points))
        point=e.flight_point((7000,3000),goal,size,350)
        self.assertEqual(point,e.flight_point((7000,3000),goal,size,350))

    def test_curved_flight_with_delayed_readings_still_crosses_box_without_stops(self):
        import math
        e,session,snap=self.make();now=[0.0];e.clock=lambda:now[0]
        position=[500.0,3000.0];destination=[None];pending=[];history=[(0,tuple(position))]
        snap.update(map_size=(10000,6000),speed=600,age=.3)
        snap['candidates']=[dict(id='box',revision=1,x=6500,y=3000,kind='bonus')]
        commands=[]
        def request(operation,payload,**kwargs):
            if payload['action'] in ('move','cruise'):
                commands.append(dict(payload));pending.append((now[0]+.3,(payload['x'],payload['y'])))
            self.assertNotEqual(payload['action'],'stop')
            return dict(action='ready',owner='p',life=1,map='1-1',configuration=1,active=True,mode='petal1')
        session.request.side_effect=request;stops=[];nearest=float('inf');positions=[]
        for tick in range(251):
            now[0]=tick*.1
            for due,point in list(pending):
                if due<=now[0]+1e-8:destination[0]=point;pending.remove((due,point))
            if destination[0]:
                d=math.dist(position,destination[0]);step=min(d,60)
                if d>0:position[:]=[position[i]+(destination[0][i]-position[i])*step/d for i in range(2)]
                if tick>10 and d<=60:stops.append(tick)
            positions.append(tuple(position));history.append((now[0],tuple(position)))
            snap['position']=next(point for time,point in reversed(history) if time<=max(0,now[0]-.3)+1e-8)
            nearest=min(nearest,math.dist(position,(6500,3000)))
            e.step(snap,now[0])
        self.assertGreater(max(abs(p[1]-3000) for p in positions if p[0]<4500),20)
        self.assertLess(nearest,121)
        self.assertEqual(stops,[])
        self.assertIn(('box',1),e.passed)
        self.assertTrue(any(c['action']=='move' for c in commands))
        self.assertTrue(all(0<=c['x']<=10000 and 0<=c['y']<=6000 for c in commands))

    def test_small_map_patrol_keeps_all_destinations_inside_bounds(self):
        e,session,snap=self.make();snap.update(candidates=[],map_size=(200,150),position=(100,75))
        for now in range(10):
            e.step(snap,now)
            self.assertTrue(0<e.waypoint[0]<200 and 0<e.waypoint[1]<150)
            snap['position']=e.waypoint

