"""Recovery/roaming integration without a live client or paid actions."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import FarmRecovery, NpcFarmWorker, NpcTestWorker
from test_npc_test import Session, Stop

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stop=Stop(); self.session=Mock();self.emit=Mock()
        self.settings=dict(reconnect=True,respawn='portal',max_deaths=3,max_cost=50,
                           death_state={'ids':set(),'count':0})
        self.recovery=FarmRecovery(self.session,self.stop,self.emit,self.settings,lambda:self.stop.now)
    def test_disconnect_backoff_and_revalidate_once(self):
        self.session.request.return_value={'action':'wait'}
        self.assertEqual(self.recovery.step({'fresh':False}),'waiting')
        self.stop.now=1;self.recovery.step({'fresh':False})
        self.assertEqual(self.session.request.call_count,1)
        self.stop.now=35;self.recovery.step({'fresh':False})
        self.assertTrue(self.session.request.call_args.args[1]['reload'])
        self.assertEqual(self.recovery.step({'fresh':True}),'restored')
        self.assertEqual(self.recovery.step({'fresh':True}),'ready')
    def test_login_or_timeout_stops(self):
        self.session.request.return_value={'action':'login'}
        with self.assertRaisesRegex(ValueError,'login'):self.recovery.step({'fresh':False})
        self.session.request.return_value={'action':'wait'};self.stop.now=601
        with self.assertRaisesRegex(ValueError,'10 minutos'):self.recovery.step({'fresh':False})
    def test_one_paid_respawn_until_acknowledged(self):
        snap={'fresh':True,'dead':True,'repair':{'id':'death'}}
        self.session.request.return_value={'action':'respawn'}
        self.recovery.step(snap);self.stop.now=1;self.recovery.step(snap)
        self.assertEqual(self.session.request.call_count,1)
        self.assertEqual(self.settings['death_state']['count'],1)
        payload=self.session.request.call_args.args[1]
        self.assertEqual((payload['option'],payload['max_cost']),('portal',50))
        self.assertEqual(self.recovery.step({'fresh':True,'dead':False}),'restored')
    def test_unconfirmed_respawn_never_repeated(self):
        self.session.request.return_value={'action':'respawn'}
        snap={'fresh':True,'dead':True,'repair':{'id':'death'}}
        self.recovery.step(snap);self.stop.now=31
        with self.assertRaisesRegex(ValueError,'sem confirmação'):self.recovery.step(snap)
        self.assertEqual(self.session.request.call_count,1)
    def test_limits_disabled_and_unaffordable(self):
        snap={'fresh':True,'dead':True,'repair':{'id':'death'}}
        self.settings['max_deaths']=1
        with self.assertRaisesRegex(ValueError,'Limite'):self.recovery.step(snap)
        self.session.request.assert_not_called()
        self.settings['max_deaths']=3;self.settings['respawn']='Desativado'
        with self.assertRaisesRegex(ValueError,'desativado'):self.recovery.step(snap)
        self.session.request.assert_not_called()
        self.settings['respawn']='portal';self.session.request.return_value={'action':'blocked'}
        with self.assertRaisesRegex(ValueError,'custo'):self.recovery.step(snap)
    def test_cancel_prevents_all_requests(self):
        self.stop.set();self.recovery.step({'fresh':False});self.session.request.assert_not_called()
    def test_transient_overlay_wait_is_not_counted_as_a_sent_respawn(self):
        snap={'fresh':True,'dead':True,'repair':{'id':'death'}}
        self.session.request.side_effect=[{'action':'wait'},{'action':'respawn'}]
        self.recovery.step(snap);self.assertIsNone(self.recovery.pending)
        self.recovery.step(snap);self.assertIsNotNone(self.recovery.pending)

class RoamingTests(unittest.TestCase):
    def test_idle_explores_then_stops_when_a_target_appears(self):
        stop=Stop();session=Mock();session.request.return_value={'action':'move_sent'}
        engine=NpcFarmWorker(session,stop,lambda *e:None)
        snap=dict(map='1-1',respawn_revision=1,map_size=(2000,1000),position=(500,250),combat={})
        engine.roam_step(snap,0)
        p=session.request.call_args.args[1]
        self.assertEqual((p['x'],p['y']),(500,250))
        engine.roam_step(snap,1)
        # Reached waypoint: progress to next interior point immediately.
        self.assertEqual(session.request.call_args.args[1]['x'],1500)
        count=session.request.call_count
        engine.roam_step(dict(snap,combat={'attacking':True}),4)
        self.assertEqual(session.request.call_count,count)
    def test_invalid_or_disabled_roam_does_not_send(self):
        for settings,snap in (({'roam':False},{'map_size':(1000,1000),'position':(0,0)}),
                              ({},{'map_size':(float('nan'),1000),'position':(0,0)})):
            session=Mock();engine=NpcFarmWorker(session,Stop(),lambda *e:None,**settings)
            engine.roam_step(snap,0);session.request.assert_not_called()
    def test_roaming_map_change_discards_old_destination(self):
        session=Mock();session.request.return_value={'action':'move_sent'}
        engine=NpcFarmWorker(session,Stop(),lambda *e:None)
        snap=dict(map='1-1',respawn_revision=1,map_size=(1000,1000),position=(500,500))
        engine.roam_step(snap,0)
        engine.roam_step(dict(snap,map='2-1',map_size=(2000,2000)),.1)
        self.assertEqual(session.request.call_args.args[1]['map'],'2-1')
        self.assertEqual(engine.roam_context[2],(2000,2000))
    def test_farm_reconnects_after_interrupted_fight(self):
        stop=Stop();session=Session(stop)
        engine=NpcFarmWorker(session,stop,lambda *e:None,clock=lambda:stop.now,
                             recovery_settings={'reconnect':True})
        runs=[]
        def fight(worker):
            runs.append(worker)
            if len(runs)==1:session.state['fresh']=False
            else:stop.set()
        original=session.request
        def request(op,payload,allowed):
            if op=='reconnect':session.state['fresh']=True;return {'action':'ready'}
            return original(op,payload,allowed)
        session.request=request
        with patch.object(NpcTestWorker,'run',fight):engine.run()
        self.assertEqual(len(runs),2)
    def test_repair_percentage_validated(self):
        for value in (79,101,float('nan')):
            with self.assertRaises(ValueError):NpcTestWorker(Mock(),Stop(),lambda *e:None,repair_to=value)

if __name__=='__main__':unittest.main()

class SelectionAndSettingsTests(unittest.TestCase):
    def test_portuguese_respawn_choices_from_app(self):
        for label,expected in (('Base','base'),('Portal','portal'),('Local','spot')):
            session=Mock();session.request.return_value={'action':'respawn'}
            recovery=FarmRecovery(session,Stop(),lambda *e:None,dict(respawn=label))
            recovery.step({'fresh':True,'dead':True,'repair':{'id':'d'}})
            self.assertEqual(session.request.call_args.args[1]['option'],expected)
    def test_next_target_uses_priority_then_health_then_distance(self):
        for prioritize_full,expected in ((False,'injured'),(True,'full')):
            stop=Stop();session=Session(stop,damage=False)
            session.state['npc_candidates']=[
                dict(id='full',kind='full',respawnRevision=1,x=100,y=0,hp=1000,maxHp=1000),
                dict(id='injured',kind='injured',respawnRevision=1,x=500,y=0,hp=200,maxHp=1000)]
            profile=dict(priority=-1,radius=450,ammo='lcb10',orbit=True)
            worker=NpcTestWorker(session,stop,lambda *e:None,kind=['full','injured'],clock=lambda:stop.now,
                                 npc_profiles={'full':profile} if prioritize_full else {})
            original=session.request
            def request(op,payload,allowed):
                if payload['action']=='select':stop.set()
                return original(op,payload,allowed)
            session.request=request;worker.run()
            self.assertEqual(worker.target['id'],expected)
    def test_overlay_wait_has_a_deadline(self):
        stop=Stop();session=Mock();session.request.return_value={'action':'wait'}
        recovery=FarmRecovery(session,stop,lambda *e:None,dict(respawn='portal'),lambda:stop.now)
        snap={'fresh':True,'dead':True,'repair':{'id':'d'}}
        recovery.step(snap);stop.now=31
        with self.assertRaisesRegex(ValueError,'sem confirmação'):recovery.step(snap)
        self.assertEqual(session.request.call_count,1)
