"""Render the actual Tk app with explicit simulated data. Requires a running display."""
import math
from pathlib import Path
from PIL import ImageGrab
from test_app import AppTests


def capture():
    AppTests.setUpClass()
    app,root=AppTests.app,AppTests.root
    output=Path(__file__).resolve().parents[2]/'docs'
    try:
        for timer in root.tk.call('after','info'):root.after_cancel(timer)
        root.geometry('840x560+20+20');root.deiconify();app.set_compact(True)
        for key,value in dict(uridium='128.450',credits='14.820.600',earned='8.240 U',last_hour='6.180 U',hourly='6.420 U/h').items():app.account_vars[key].set(value)
        app.npc_summary.set('Farmando · NPCs: 24')
        app.status.set('PRÉVIA VISUAL · Dados simulados · Sem conexão com o jogo')
        s=dict(fresh=True,map='3-2',respawn_revision=1,map_size=(20000,12000),position=(8500,6700),
               hp_percent=82,shield_percent=64,combat=dict(target_id='npc1',attacking=True,selectedAmmo='lcb10',selected_stock=28450),
               npc_candidates=[dict(id='npc1',kind='Mordon',x=10200,y=6100,hp=1800,maxHp=6000),
                               dict(id='npc2',kind='Saimon',x=4000,y=3000),dict(id='npc3',kind='Lordakia',x=15000,y=9000),
                               dict(id='npc4',kind='Mordon',x=5700,y=8500),dict(id='npc5',kind='Saimon',x=14000,y=3500)],
               candidates=[dict(id=str(i),x=1300+(i*2137)%16000,y=1200+(i*1879)%9500) for i in range(24)],
               gates=[dict(x=1400,y=1400),dict(x=18500,y=10600),dict(x=1400,y=10600)],destination=dict(x=9500,y=5900))
        app.vitals_text['hp'].set('82,0%');app.vitals_text['shield'].set('64,0%')
        for i in range(25):
            app.cockpit.model.update(dict(s,position=(6500+i*80,6700+math.sin(i/5)*550)))
        s.update(allies_available=True,allies=[dict(id='ally1',nickname='Aliado 01',x=9000,y=3600),dict(id='ally2',nickname='Aliado 02',x=3800,y=7200)])
        app.cockpit.layers['npc_names'].set(True);app.cockpit.layers['ally_names'].set(True)
        app.cockpit.update(s);root.update();root.update_idletasks()
        def snap(window,name):
            window.update();x=window.winfo_rootx();y=window.winfo_rooty()
            ImageGrab.grab(xdisplay=root.winfo_screen()).crop((x,y,x+window.winfo_width(),y+window.winfo_height())).save(output/name)
        snap(root,'autobox-interface-preview.png')
        app.open_settings('combat');app.settings_window.geometry('960x760+20+20');root.update()
        snap(app.settings_window,'autobox-settings-preview.png')
        print('Rendered actual app:',output)
    finally:AppTests.tearDownClass()

if __name__=='__main__':capture()
