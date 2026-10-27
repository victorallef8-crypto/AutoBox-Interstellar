"""Compact live cockpit. Rendering uses sanitized game snapshots, never screenshots."""
import math
import tkinter as tk
from tkinter import ttk
from collections import deque


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
                    boxes=[b for b in snapshot.get("candidates", []) if valid(b)][:500],
                    gates=[g for g in snapshot.get("gates", []) if valid(g)][:50],
                    combat=snapshot.get("combat") or {}, destination=snapshot.get("destination"))


class Cockpit(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self.model = MapModel()
        self.snapshot = {"fresh": False}
        self.mode = tk.StringVar(value="NPC Killer")
        self.pinned = tk.BooleanVar(value=False)
        self.map_text = tk.StringVar(value="Aguardando mapa")
        self.detail = tk.StringVar(value="Sem leitura ao vivo")
        self.health = tk.StringVar(value="HP —   |   Escudo —")
        self.ammo = tk.StringVar(value="Laser —")
        top = ttk.Frame(self); top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="AutoBoxV", style="Heading.TLabel").pack(side="left", padx=(0, 10))
        ttk.Combobox(top, textvariable=self.mode, values=("Coleta", "NPC Killer", "Matar + coletar"),
                     state="readonly", width=16).pack(side="left")
        self.buttons = {}
        for label, command in (("Iniciar", self.start), ("Pausar", app.pause_all), ("Parar", app.stop_all)):
            button = ttk.Button(top, text=label, command=command, style="Compact.TButton", width=7)
            button.pack(side="left", padx=2); self.buttons[label] = button
        ttk.Button(top, text="Configurações", command=lambda: app.set_compact(False),
                   style="Compact.TButton").pack(side="right")
        body = ttk.Frame(self); body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#080e16", highlightthickness=1,
                                highlightbackground="#354558", width=440, height=300)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.render())
        side = ttk.Frame(body, padding=(10, 4)); side.pack(side="right", fill="y")
        ttk.Label(side, textvariable=self.map_text, style="Heading.TLabel").pack(anchor="w", pady=(0, 8))
        for title, variable in (("Uridium", app.account_vars["uridium"]),
                                ("Ganhos na sessão", app.account_vars["earned"]),
                                ("Média / hora", app.account_vars["hourly"]),
                                ("NPC Killer", app.npc_summary), ("Coleta", app.collect_summary)):
            row=ttk.Frame(side);row.pack(fill="x",pady=3)
            ttk.Label(row, text=title, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(row, textvariable=variable, wraplength=190).pack(anchor="w")
        ttk.Label(side, textvariable=self.ammo, wraplength=190).pack(anchor="w", pady=8)
        ttk.Checkbutton(side, text="Sempre visível", variable=self.pinned,
                        command=lambda: app.root.attributes("-topmost", self.pinned.get())).pack(anchor="w")
        ttk.Button(side, text="Abrir jogo", command=app.open_browser,
                   style="Compact.TButton").pack(fill="x",pady=(6,0))
        ttk.Button(side, text="Mostrar jogo", command=lambda: app.game_window("normal"),
                   style="Compact.TButton").pack(fill="x", pady=(8, 3))
        ttk.Button(side, text="Minimizar jogo (teste)", command=lambda: app.game_window("minimized"),
                   style="Compact.TButton").pack(fill="x")
        ttk.Label(self, text="Nave: ciano   |   NPC: vermelho   |   Recurso: amarelo   |   Portal: lilás", style="Muted.TLabel").pack(anchor="w", pady=4)
        ttk.Label(self, textvariable=self.health).pack(anchor="w")
        ttk.Label(self, textvariable=self.detail, wraplength=650, style="Muted.TLabel").pack(anchor="w", pady=3)
        ttk.Label(self, textvariable=app.status, wraplength=650).pack(anchor="w")

    def start(self):
        if self.mode.get() == "Coleta":
            self.app.start()
        else:
            self.app.start_npc_test(hybrid=self.mode.get() == "Matar + coletar")

    def update(self, snapshot):
        self.snapshot = snapshot
        self.render()
        fresh = snapshot.get("fresh")
        self.map_text.set("Mapa " + str(snapshot.get("map", "—")) if fresh else "Sem conexão")
        self.health.set("HP " + self.app.vitals_text["hp"].get() + "   |   Escudo " + self.app.vitals_text["shield"].get())
        combat = (snapshot.get("combat") or {}) if fresh else {}
        stock = combat.get("selected_stock")
        self.ammo.set("Laser " + str(combat.get("selectedAmmo") or "—") + "\nEstoque: " + str(stock if stock is not None else "—"))
        self.detail.set(("Leitura ao vivo | atualização " + str(snapshot.get("sequence", "—"))
                         + " | " + str(self.app.combat_status.get() if self.app.npc_active() else self.app.collect_summary.get()))
                        if fresh else "Leitura indisponível. O minimapa aguarda novos dados do jogo.")

    def render(self):
        c = self.canvas; c.delete("all")
        data = self.model.update(self.snapshot)
        width, height = max(1, c.winfo_width()), max(1, c.winfo_height())
        if data is None:
            c.create_text(width/2, height/2, text="AGUARDANDO DADOS DO JOGO", fill="#8293a8", font=("Segoe UI", 10))
            return
        scale = min(max(1, width-24)/data["size"][0], max(1, height-24)/data["size"][1])
        mx, my = (width-data["size"][0]*scale)/2, (height-data["size"][1]*scale)/2
        def point(x, y): return mx+x*scale, my+y*scale
        right, bottom = point(*data["size"])
        c.create_rectangle(mx, my, right, bottom, outline="#546579")
        for i in range(1, 5):
            x = mx+(right-mx)*i/5; y = my+(bottom-my)*i/5
            c.create_line(x, my, x, bottom, fill="#172333")
            c.create_line(mx, y, right, y, fill="#172333")
        trail = [v for p in data["trail"] for v in point(*p)]
        if len(trail) >= 4: c.create_line(*trail, fill="#246b70", width=1)
        for box in data["boxes"]:
            x,y=point(box["x"],box["y"])
            c.create_rectangle(x-2,y-2,x+2,y+2,outline="#62d7a0" if box.get("kind")=="booty" else "#e5d17c")
        for gate in data["gates"]:
            x,y=point(gate["x"],gate["y"])
            c.create_polygon(x,y-5,x+5,y,x,y+5,x-5,y,outline="#b59cff",fill="")
        selected = data["combat"].get("target_id")
        ship = point(*data["position"])
        for npc in data["npcs"]:
            x,y=point(npc["x"],npc["y"])
            target = selected is not None and str(npc.get("id"))==str(selected)
            c.create_oval(x-3,y-3,x+3,y+3,fill="#ff6b70",outline="")
            if target:
                c.create_oval(x-7,y-7,x+7,y+7,outline="#ffbd69")
                c.create_text(x+9,y-9,text=npc.get("kind") or npc.get("type") or "NPC",fill="#ffbd69",anchor="w")
                if data["combat"].get("attacking"): c.create_line(*ship,x,y,fill="#f9b36c",dash=(3,3))
        dest = data.get("destination")
        if isinstance(dest,dict) and all(number(dest.get(k)) for k in ("x","y")):
            x,y=point(dest["x"],dest["y"]);c.create_line(*ship,x,y,fill="#67e8f9",dash=(2,4))
        x,y=ship
        c.create_polygon(x,y-7,x+5,y+5,x,y+2,x-5,y+5,fill="#65e5e0",outline="#b2ffff")
