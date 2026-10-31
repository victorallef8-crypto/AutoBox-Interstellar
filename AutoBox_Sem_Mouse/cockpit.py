"""Compact live cockpit. Rendering uses sanitized game snapshots, never screenshots."""
import math
import os
import tkinter as tk
from tkinter import ttk
from collections import deque


FONT="Segoe UI" if os.name=="nt" else "Helvetica"


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


class MapModel:
    def __init__(self):
        self.context = None
        self.trail = deque(maxlen=80)

    def update(self, snapshot):
        context = (snapshot.get("map"), snapshot.get("respawn_revision"))
        size = snapshot.get("map_size") or ()
        position = snapshot.get("position") or ()
        if (not snapshot.get("fresh") or not isinstance(size,(tuple,list)) or not isinstance(position,(tuple,list))
                or len(size) != 2 or len(position) != 2
                or not all(number(v) for v in (*size, *position)) or min(size) <= 0):
            self.trail.clear()
            return None
        if context != self.context:
            self.trail.clear()
            self.context = context
        if not self.trail or tuple(position) != self.trail[-1]:
            self.trail.append(tuple(position))
        def valid(item):
            return (number(item.get("x")) and number(item.get("y"))
                    and 0 <= item["x"] <= size[0] and 0 <= item["y"] <= size[1])
        return dict(size=size, position=position, trail=list(self.trail),
                    npcs=[n for n in snapshot.get("npc_candidates", []) if valid(n)][:300],
                    allies=[p for p in snapshot.get("allies", []) if valid(p)][:200],
                    boxes=[b for b in snapshot.get("candidates", []) if valid(b)][:500],
                    gates=[g for g in snapshot.get("gates", []) if valid(g)][:50],
                    combat=snapshot.get("combat") or {}, destination=snapshot.get("destination"))


class Cockpit(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=0)
        self.app = app
        self.model = MapModel()
        self.snapshot = {"fresh": False}
        self.mode = tk.StringVar(value=app.cfg.get("cockpit_mode","NPC Killer"))
        if self.mode.get() not in ("Coleta","NPC Killer","Matar + coletar"):self.mode.set("NPC Killer")
        self.pinned = tk.BooleanVar(value=app.cfg.get("always_on_top",False))
        self.map_text = tk.StringVar(value="SEM CONEXÃO")
        self.detail = tk.StringVar(value="Sem leitura ao vivo")
        self.health = tk.StringVar(value="HP —   |   Escudo —")
        self.ammo = tk.StringVar(value="Laser —")
        self.target_text = tk.StringVar(value="Nenhum NPC selecionado")
        self.coordinates = tk.StringVar(value="— / —")
        self.stats_visible=tk.BooleanVar(value=app.cfg.get("map_stats",True))
        prefs=app.cfg.get("map_layers",{})
        if not isinstance(prefs,dict):prefs={}
        self.layers={key:tk.BooleanVar(value=prefs.get(key,key not in ("npc_names","ally_names")))
                     for key in ("npcs","boxes","gates","trail","allies","npc_names","ally_names")}
        self.buttons={}
        toolbar=ttk.Frame(self,style="Toolbar.TFrame",padding=(6,5));toolbar.pack(fill="x")
        for label,command in (("Config.",lambda:app.open_settings()),
                              ("Estatísticas",lambda:app.open_settings("dashboard")),
                              ("Iniciar",self.start),("Pausar",app.pause_all),("Parar",app.stop_all)):
            button=ttk.Button(toolbar,text=label,command=command,style="Toolbar.TButton",width=12 if label=="Estatísticas" else 7)
            button.pack(side="left",padx=(0,3));self.buttons[label]=button
        ttk.Label(toolbar,text="AutoBoxV",style="Toolbar.TLabel",font=(FONT,11,"bold")).pack(side="left",expand=True,padx=6)
        ttk.Button(toolbar,text="Abrir jogo",command=app.open_browser,style="Toolbar.TButton").pack(side="left",padx=2)
        ttk.Button(toolbar,text="Ocultar",command=lambda:app.game_window("minimized"),style="Toolbar.TButton",width=7).pack(side="left",padx=2)
        ttk.Button(toolbar,text="Mostrar",command=lambda:app.game_window("normal"),style="Toolbar.TButton",width=7).pack(side="left",padx=2)
        controls=ttk.Frame(self,style="Toolbar.TFrame",padding=(8,3));controls.pack(fill="x")
        ttk.Label(controls,text="Módulo",style="Toolbar.TLabel").pack(side="left",padx=(0,6))
        choice=ttk.Combobox(controls,textvariable=self.mode,values=("Coleta","NPC Killer","Matar + coletar"),state="readonly",width=17)
        choice.pack(side="left");choice.bind("<<ComboboxSelected>>",lambda e:self.save_view())
        for key,label in (("npcs","NPCs"),("boxes","Boxes"),("gates","Portais"),("trail","Rastro"),("allies","Aliados")):
            ttk.Checkbutton(controls,text=label,variable=self.layers[key],command=self.save_view,style="Map.TCheckbutton").pack(side="left",padx=(8,0))
        ttk.Checkbutton(controls,text="Dados",variable=self.stats_visible,command=self.save_view,style="Map.TCheckbutton").pack(side="left",padx=(8,0))
        ttk.Checkbutton(controls,text="Fixar",variable=self.pinned,command=self.pin,style="Map.TCheckbutton").pack(side="right")
        names=ttk.Frame(self,style="Toolbar.TFrame",padding=(8,2));names.pack(fill="x")
        ttk.Label(names,text="Mostrar nomes:",style="Toolbar.TLabel").pack(side="left",padx=(0,8))
        for key,label in (("npc_names","NPCs"),("ally_names","Aliados")):
            ttk.Checkbutton(names,text=label,variable=self.layers[key],command=self.save_view,style="Map.TCheckbutton").pack(side="left",padx=(0,12))
        self.ally_status=tk.StringVar(value="Aliados: aguardando dados do jogo")
        ttk.Label(names,textvariable=self.ally_status,style="Toolbar.TLabel").pack(side="right")
        self.canvas=tk.Canvas(self,background="#121719",highlightthickness=0,width=760,height=360)
        self.canvas.pack(fill="both",expand=True)
        self.canvas.bind("<Configure>",lambda e:self.render())
        self.overlay=tk.Frame(self.canvas,bg="#20262a",padx=12,pady=10,highlightthickness=1,highlightbackground="#3b464b")
        tk.Label(self.overlay,text="ESTATÍSTICAS",bg="#20262a",fg="#96a7af",font=(FONT,8,"bold")).pack(anchor="w",pady=(0,6))
        for label,key in (("Uridium","uridium"),("Créditos","credits"),("Sessão","earned"),("Última hora","last_hour"),("Média / hora","hourly")):
            row=tk.Frame(self.overlay,bg="#20262a");row.pack(fill="x",pady=2)
            tk.Label(row,text=label,bg="#20262a",fg="#a6b1b7",font=(FONT,9)).pack(anchor="w")
            tk.Label(row,textvariable=app.account_vars[key],bg="#20262a",fg="#e2eee7",font=(FONT,12 if key=="uridium" else 10,"bold")).pack(anchor="w")
        tk.Label(self.overlay,textvariable=app.npc_summary,bg="#20262a",fg="#a6b1b7",wraplength=170,font=(FONT,9)).pack(anchor="w",pady=(8,0))
        info=ttk.Frame(self,style="Toolbar.TFrame",padding=(8,4));info.pack(fill="x")
        ttk.Label(info,textvariable=self.map_text,style="Toolbar.TLabel",font=(FONT,10,"bold")).pack(side="left")
        ttk.Label(info,textvariable=self.coordinates,style="Toolbar.TLabel").pack(side="right")
        ttk.Label(info,textvariable=self.target_text,style="Toolbar.TLabel").pack(side="left",padx=18)
        vitals=ttk.Frame(self,padding=(8,4));vitals.pack(fill="x")
        self.bars={}
        for key,title,style in (("hp","HP","HP.Horizontal.TProgressbar"),("shield","Escudo","Shield.Horizontal.TProgressbar")):
            ttk.Label(vitals,text=title).pack(side="left",padx=(0,4))
            bar=ttk.Progressbar(vitals,maximum=100,style=style,length=110);bar.pack(side="left",fill="x",expand=True,padx=(0,4));self.bars[key]=bar
            ttk.Label(vitals,textvariable=app.vitals_text[key],width=13).pack(side="left",padx=(0,10))
        ttk.Label(vitals,textvariable=self.ammo,style="Muted.TLabel").pack(side="right")
        footer=ttk.Frame(self,padding=(8,3));footer.pack(fill="x")
        ttk.Label(footer,textvariable=app.status,wraplength=650,style="Muted.TLabel").pack(anchor="w")
        # Reserve the status and ship information before allocating the resizable map.
        for row in (footer,vitals,info):
            row.pack_forget()
            row.pack(side="bottom",fill="x",before=self.canvas)
        self.pin(save=False)

    def pin(self, save=True):
        self.app.root.attributes("-topmost",self.pinned.get())
        if save:self.save_view()

    def save_view(self):
        self.app.cfg.update(cockpit_mode=self.mode.get(),always_on_top=self.pinned.get(),
                            map_stats=self.stats_visible.get(),map_layers={k:v.get() for k,v in self.layers.items()})
        try:self.app._write_config()
        except OSError as exc:self.app.say("Não foi possível salvar o visual: "+str(exc))
        self.render()

    def start(self):
        if self.mode.get() == "Coleta":
            self.app.start()
        else:
            self.app.start_npc_test(hybrid=self.mode.get() == "Matar + coletar")

    def update(self, snapshot):
        self.snapshot = snapshot
        fresh=snapshot.get("fresh")
        self.map_text.set("MAPA " + str(snapshot.get("map", "—")) if fresh else "SEM CONEXÃO")
        self.health.set("HP " + self.app.vitals_text["hp"].get() + "   |   Escudo " + self.app.vitals_text["shield"].get())
        combat=(snapshot.get("combat") or {}) if fresh else {}
        self.ally_status.set(("Aliados: "+str(len(snapshot.get("allies",[])))) if fresh and snapshot.get("allies_available") else "Aliados: identificação indisponível")
        stock=combat.get("selected_stock")
        self.ammo.set(str(combat.get("selectedAmmo") or "Laser —").upper()+" · "+str(stock if stock is not None else "—"))
        for key in self.bars:
            value=snapshot.get("hp_percent" if key=="hp" else "shield_percent") if fresh else None
            self.bars[key]["value"]=max(0,min(100,value)) if number(value) else 0
        position=snapshot.get("position") if fresh else None
        self.coordinates.set("X: %.0f   Y: %.0f" % tuple(position) if isinstance(position,(tuple,list)) and len(position)==2 and all(number(v) for v in position) else "X: —   Y: —")
        target=next((n for n in snapshot.get("npc_candidates",[]) if fresh and combat.get("target_id") is not None and str(n.get("id"))==str(combat["target_id"])),None)
        if target:
            hp=target.get("hp");maximum=target.get("maxHp")
            health=("%.0f%%" % (100*hp/maximum)) if number(hp) and number(maximum) and maximum>0 else (str(hp) if number(hp) else "—")
            self.target_text.set(str(target.get("kind") or target.get("type") or "NPC")+" · HP "+health)
        else:self.target_text.set("Nenhum NPC selecionado")
        self.render()

    def render(self):
        c = self.canvas; c.delete("all")
        data = self.model.update(self.snapshot)
        width, height = max(1, c.winfo_width()), max(1, c.winfo_height())
        if self.stats_visible.get() and width>=620 and data is not None:
            self.overlay.place(relx=1,x=-14,y=16,anchor="ne")
        else:self.overlay.place_forget()
        if data is None:
            c.create_text(width/2, height/2, text="AGUARDANDO DADOS DO JOGO", fill="#8293a8", font=(FONT, 10))
            return
        # Deterministic canvas stars: decoration only, never game entities.
        for i in range(85):
            x=(i*193+37)%max(1,int(width));y=(i*127+19)%max(1,int(height))
            c.create_oval(x,y,x+1,y+1,fill="#354145",outline="")
        scale = min(max(1, width-24)/data["size"][0], max(1, height-24)/data["size"][1])
        mx, my = (width-data["size"][0]*scale)/2, (height-data["size"][1]*scale)/2
        def point(x, y): return mx+x*scale, my+y*scale
        right, bottom = point(*data["size"])
        c.create_rectangle(mx, my, right, bottom, outline="#4d6767")
        for i in range(1, 5):
            x = mx+(right-mx)*i/5; y = my+(bottom-my)*i/5
            c.create_line(x, my, x, bottom, fill="#202b2d")
            c.create_line(mx, y, right, y, fill="#202b2d")
        trail = [v for p in data["trail"] for v in point(*p)]
        if self.layers["trail"].get() and len(trail) >= 4: c.create_line(*trail, fill="#246b70", width=1)
        for box in data["boxes"] if self.layers["boxes"].get() else []:
            x,y=point(box["x"],box["y"])
            c.create_rectangle(x-2,y-2,x+2,y+2,outline="#62d7a0" if box.get("kind")=="booty" else "#e5d17c")
        for gate in data["gates"] if self.layers["gates"].get() else []:
            x,y=point(gate["x"],gate["y"])
            c.create_polygon(x,y-5,x+5,y,x,y+5,x-5,y,outline="#b59cff",fill="")
        selected = data["combat"].get("target_id")
        ship = point(*data["position"])
        def label(x,y,text,color,tag):
            # Bound single-line labels and keep them inside the map viewport.
            text=" ".join(str(text).split())[:36]
            anchor="e" if x>right-130 else "w"
            c.create_text(max(mx+6,min(right-6,x-8 if anchor=="e" else x+8)),
                          max(my+10,min(bottom-10,y-10)),text=text,fill=color,
                          anchor=anchor,font=(FONT,9),tags=(tag,))
        for npc in data["npcs"] if self.layers["npcs"].get() else []:
            x,y=point(npc["x"],npc["y"])
            target = selected is not None and str(npc.get("id"))==str(selected)
            c.create_oval(x-3,y-3,x+3,y+3,fill="#ff6b70",outline="")
            if target:
                c.create_oval(x-7,y-7,x+7,y+7,outline="#ffbd69")
                if data["combat"].get("attacking"): c.create_line(*ship,x,y,fill="#f9b36c",dash=(3,3))
            if target or self.layers["npc_names"].get():
                label(x,y,npc.get("name") or npc.get("kind") or npc.get("type") or "NPC",
                      "#ffbd69" if target else "#ee969a","npc-name")
        for ally in data["allies"] if self.layers["allies"].get() else []:
            x,y=point(ally["x"],ally["y"])
            c.create_polygon(x,y-4,x+4,y,x,y+4,x-4,y,fill="#6edda5",outline="#a7edc7",tags=("ally-marker",))
            if self.layers["ally_names"].get():
                label(x,y,ally.get("nickname") or ally.get("name") or "Aliado","#91e2b5","ally-name")
        dest = data.get("destination")
        if isinstance(dest,dict) and all(number(dest.get(k)) for k in ("x","y")):
            x,y=point(dest["x"],dest["y"]);c.create_line(*ship,x,y,fill="#67e8f9",dash=(2,4))
        x,y=ship
        c.create_polygon(x,y-7,x+5,y+5,x,y+2,x-5,y+5,fill="#65e5e0",outline="#b2ffff")
