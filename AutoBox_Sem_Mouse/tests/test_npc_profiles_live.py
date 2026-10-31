import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controller import LiveNpcSettings, NpcTestWorker, normalize_npc_profiles
from test_npc_test import Stop, Session
import test_app


def profile(**kw):
    return dict(dict(priority=0,radius=450,ammo='lcb10',orbit=True,kill=True,rocket='none',portal=False,pursuit=False),**kw)

class LiveSettingsTests(unittest.TestCase):
    def test_changes_are_explicit_and_returned_snapshots_are_isolated(self):
        p={'mordon':profile()};runtime=LiveNpcSettings(p,['mordon']);v,read,_=runtime.read()
        p['mordon']['radius']=700;read['mordon']['radius']=150
        self.assertEqual(runtime.read()[1]['mordon']['radius'],450)
        runtime.update(p,['mordon']);self.assertGreater(runtime.read()[0],v)
        self.assertEqual(runtime.read()[1]['mordon']['radius'],700)

    def test_distance_changes_during_same_fight_without_restart(self):
        stop=Stop();session=Session(stop,damage=False);runtime=LiveNpcSettings({'mordon':profile()},['mordon'])
        seen=[];original=session.request
        def request(op,payload,allowed):
            if payload['action']=='orbit':
                seen.append(payload['radius'])
                if len(seen)==1:runtime.update({'mordon':profile(radius=650)},['mordon'])
                elif len(seen)==2:stop.set()
            return original(op,payload,allowed)
        session.request=request
        worker=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True,runtime=runtime)
        worker.run();self.assertEqual(seen,[450,650]);self.assertEqual(worker.report['radius'],650)
        self.assertEqual(sum(p['action']=='attack' for _,p in session.calls),1)

    def test_ammo_change_is_acknowledged_without_a_second_fire_toggle(self):
        stop=Stop();session=Session(stop,damage=False);runtime=LiveNpcSettings({'mordon':profile()},['mordon'])
        original=session.request;orbits=[];ammo=[]
        def request(op,payload,allowed):
            if payload['action']=='attack' and payload['ammo']!=session.state['combat']['selectedAmmo']:
                ammo.append(payload['ammo']);session.state['combat']['selectedAmmo']=payload['ammo']
                return {'action':'ammo_sent'}
            if payload['action']=='orbit':
                orbits.append(payload['radius'])
                if len(orbits)==1:runtime.update({'mordon':profile(ammo='mcb25')},['mordon'])
                else:stop.set()
            return original(op,payload,allowed)
        session.request=request
        worker=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True,runtime=runtime)
        worker.run();self.assertEqual(ammo,['mcb25']);self.assertEqual(worker.ammo,'mcb25')
        self.assertEqual(sum(p['action']=='attack' for _,p in session.calls),1)

    def test_unchecking_current_npc_stops_it_before_any_new_target(self):
        stop=Stop();session=Session(stop,damage=False);runtime=LiveNpcSettings({'mordon':profile()},['mordon'])
        original=session.request
        def request(op,payload,allowed):
            if payload['action']=='orbit':runtime.update({'mordon':profile(kill=False)},[])
            return original(op,payload,allowed)
        session.request=request
        worker=NpcTestWorker(session,stop,lambda *e:None,clock=lambda:stop.now,orbit=True,runtime=runtime)
        worker.run();self.assertTrue(worker.report['target_disabled']);self.assertTrue(worker.report['stop_confirmed'])

    def test_per_npc_extras_apply_together(self):
        stop=Stop();worker=NpcTestWorker(Session(stop),stop,lambda *e:None,
            npc_profiles={'mordon':profile(radius=700,rocket='plt2026',portal=True,pursuit=True,orbit=False)})
        worker.kind='mordon';worker.apply_profile()
        self.assertEqual(worker.radius,700);self.assertEqual(worker.rocket,'plt2026')
        self.assertTrue(worker.portal_fight);self.assertTrue(worker.pursuit.enabled);self.assertFalse(worker.orbit)
        self.assertEqual(normalize_npc_profiles({'mordon':profile()})['mordon']['kill'],True)

class NpcTableUiTests(unittest.TestCase):
    setUpClass=classmethod(test_app.AppTests.setUpClass.__func__)
    tearDownClass=classmethod(test_app.AppTests.tearDownClass.__func__)

    def setUp(self):
        app=self.app
        app.npc_catalog['3-2']=[]
        app.npc_map.set('3-2');app.remember_map_npcs('3-2',['mordon','saimon','lordakia'])
        app.npc_profile_maps['3-2']={};app.profile_table_signature=None;app.refresh_profile_table()
        app.npc_engine=None;self.root.update()

    def test_table_lists_every_observed_type_even_after_npcs_disappear(self):
        app=self.app
        self.assertEqual(set(app.profile_table.get_children()),{'mordon','saimon','lordakia'})
        app.remember_map_npcs('3-2',[])
        self.assertEqual(len(app.profile_table.get_children()),3)

    def test_map_specific_distance_and_ammo_do_not_leak(self):
        app=self.app
        app.npc_profile_maps['3-2']={'mordon':profile(radius=650,ammo='mcb50')}
        app.npc_catalog['4-3']=['mordon'];app.npc_profile_maps['4-3']={'mordon':profile(radius=350,ammo='lcb10')}
        app.npc_map.set('4-3');app.profile_kind.set('mordon');app.load_npc_profile()
        self.assertEqual(app.profile_radius.get(),'350');self.assertEqual(app.profile_ammo.get(),'lcb10')
        app.npc_map.set('3-2');app.profile_kind.set('mordon');app.load_npc_profile()
        self.assertEqual(app.profile_radius.get(),'650');self.assertEqual(app.profile_ammo.get(),'mcb50')

    def test_apply_saves_extras_and_updates_running_configuration(self):
        app=self.app;engine=Mock();engine.profile_map='3-2';app.npc_engine=engine
        app.profile_kind.set('mordon');app.profile_radius.set('675');app.profile_ammo.set('mcb25')
        app.profile_kill.set(True);app.profile_orbit.set(False);app.profile_rocket.set('r310')
        app.profile_portal.set(False);app.profile_pursuit.set(True);app.save_npc_profile()
        p=app.active_npc_profiles()['mordon'];self.assertEqual(p['radius'],675);self.assertTrue(p['pursuit'])
        engine.live_settings.update.assert_called_once()
        self.assertEqual(engine.live_settings.update.call_args.args[0]['mordon']['ammo'],'mcb25')
        self.assertIn('675',app.profile_table.item('mordon','values'))
        app.npc_engine=None

    def test_editing_another_map_does_not_change_the_running_farm(self):
        app=self.app;engine=Mock();engine.profile_map='4-3';app.npc_engine=engine
        app.profile_kind.set('mordon');app.profile_radius.set('500');app.profile_kill.set(True);app.save_npc_profile()
        engine.live_settings.update.assert_not_called();app.npc_engine=None

    def test_catalog_table_has_no_thirty_npc_limit(self):
        app=self.app;kinds=['npc_%d'%i for i in range(65)]
        app.remember_map_npcs('3-2',kinds)
        self.assertTrue(set(kinds).issubset(set(app.profile_table.get_children())))

    def test_invalid_distance_does_not_overwrite_saved_profile(self):
        app=self.app;app.active_npc_profiles()['mordon']=profile(radius=650)
        app.profile_kind.set('mordon');app.profile_radius.set('99');app.profile_kill.set(True)
        app.save_npc_profile();self.assertEqual(app.active_npc_profiles()['mordon']['radius'],650)
        app.profile_radius.set('450')

    def test_distance_can_be_edited_directly_in_the_table(self):
        from types import SimpleNamespace
        app=self.app;root=self.root
        app.open_settings('combat');root.deiconify();root.geometry('960x760');root.update()
        table=app.profile_table;x,y,w,h=table.bbox('mordon','#4')
        app.edit_npc_cell(SimpleNamespace(x=x+w/2,y=y+h/2));root.update()
        editor=app.npc_cell_editor
        self.assertIsNotNone(editor)
        editor.focus_force();editor.delete(0,'end');editor.insert(0,'625');root.update()
        editor.event_generate('<Return>');root.update()
        self.assertEqual(app.active_npc_profiles()['mordon']['radius'],625)
        self.assertIsNone(app.npc_cell_editor)
        root.withdraw()

    def test_mark_all_and_apply_values_only_to_selected_map(self):
        app=self.app
        app.npc_profile_maps['4-3']={'mordon':profile(radius=300)}
        app.mark_all_npcs(True)
        self.assertTrue(all(app.npc_kind_vars[k].get() for k in app.npc_profile_kinds()))
        app.profile_radius.set('700');app.profile_ammo.set('mcb50');app.apply_to_marked_npcs()
        self.assertTrue(all(p['radius']==700 for p in app.active_npc_profiles().values()))
        self.assertEqual(app.npc_profile_maps['4-3']['mordon']['radius'],300)
        app.mark_all_npcs(False)
        self.assertFalse(any(app.npc_kind_vars[k].get() for k in app.npc_profile_kinds()))

    def test_legacy_global_extras_are_visible_in_the_effective_row(self):
        app=self.app;app.npc_portal_fight.set(True);app.pursuit_enabled.set(True)
        app.profile_kind.set('mordon');app.load_npc_profile()
        self.assertTrue(app.profile_portal.get());self.assertTrue(app.profile_pursuit.get())
        app.npc_portal_fight.set(False);app.pursuit_enabled.set(False)
