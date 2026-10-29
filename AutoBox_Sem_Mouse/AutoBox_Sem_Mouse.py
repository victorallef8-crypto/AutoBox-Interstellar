"""AutoBox Sem Mouse — aplicativo independente, exclusivo de coleta no Interstellar."""
from __future__ import annotations
import ctypes
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from pynput import keyboard
from browser_session import BrowserSession, find_opera_gx
from controller import DataFarmPlanner, DataCollector, SessionEarnings, TravelWorker, NpcTestWorker, NpcFarmWorker, GalaxyWorker, SkylabWorker
import updater
from cockpit import Cockpit
from controller import normalize_npc_profiles

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "AutoBoxSemMouse"
CONFIG_PATH = APP_DIR / "config.json"
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

def read_config():
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class AutoBoxSemMouse:
    def __init__(self, root):
        self.root = root
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = read_config()
        self.viewport = {"width": max(800, min(1280, root.winfo_screenwidth()-60)),
                         "height": max(500, min(720, root.winfo_screenheight()-120))}
        self.cfg["viewport"] = self.viewport
        self.session = BrowserSession(APP_DIR / "opera_session", self.viewport)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.worker = None
        self.skylab_worker=None
        self.skylab_stop=threading.Event();self.skylab_stop.set()
        self.skylab_status=tk.StringVar(value="Parado. Abra o Skylab no jogo antes de iniciar.")
        self.skylab_reserve=tk.StringVar(value=str(self.cfg.get("skylab_reserve",0)))
        self.gg_worker=None
        self.gg_stop=threading.Event();self.gg_stop.set()
        self.gg_enabled=tk.BooleanVar(value=False)
        self.gg_uri=tk.BooleanVar(value=False)
        self.gg_gate=tk.StringVar(value=self.cfg.get("gg_gate","alpha"))
        self.gg_reserve=tk.StringVar(value=str(self.cfg.get("gg_reserve",50000)))
        self.gg_limit=tk.StringVar(value=str(self.cfg.get("gg_limit",1000)))
        self.gg_sizes={n:tk.BooleanVar(value=n in self.cfg.get("gg_sizes",[100,50,10,5,1])) for n in (100,50,10,5,1)}
        self.gg_status=tk.StringVar(value="Parado. Apenas materialização; não entra em portais.")
        self.buy_laser=tk.BooleanVar(value=self.cfg.get("buy_laser",False))
        self.buy_missile=tk.BooleanVar(value=self.cfg.get("buy_missile",False))
        self.buy_fields={key:tk.StringVar(value=str(self.cfg.get("buy_"+key,default))) for key,default in
            (("laser_threshold",1000),("laser_quantity",5000),("missile_threshold",50),("missile_quantity",500),
             ("reserve_uri",50000),("reserve_credits",100000))}
        self.npc_worker = None
        self.npc_engine = None
        self.npc_stop_event = threading.Event()
        self.npc_stop_event.set()
        self.npc_state = "stopped"
        self.npc_generation = 0
        self.npc_summary = tk.StringVar(value="Parado | NPCs derrotados: 0")
        self.opening = False
        self.closing = False
        self.attempts = self.confirmed = self.failed = 0
        self.collect_state="stopped"
        self.collect_summary=tk.StringVar(value="Parado")
        self.vitals_text={k:tk.StringVar(value="—") for k in ("hp","shield")}
        self.map_summary=tk.StringVar(value="Mapa — | Boxes próximas —")
        self.running = False
        self.active_started = 0.
        self.active_elapsed = 0.
        self.counter_vars = {key:tk.StringVar(value="0") for key in ("attempts","confirmed","failed")}
        self.active_time = tk.StringVar(value="Tempo em coleta: 00:00:00")
        self.session_label = tk.StringVar(value="Opera desconectado")
        self.running_label = tk.StringVar(value="Coleta pausada")
        self.status = tk.StringVar(value="Abra o Opera GX dedicado para comecar.")
        self.stats = tk.StringVar(value="Tentativas: 0 | Confirmadas: 0 | Sem progresso: 0")
        self.world_vars = {key:tk.StringVar(value="—") for key in
                           ("status","map","position","hp","counts","nearest","distance","sequence")}
        self.world_vars["status"].set("Abra o Opera dedicado e entre no mapa.")
        self.last_world_refresh = -100.
        self.collect_map=tk.StringVar(value=self.cfg.get("collect_map",""))
        self.npc_map=tk.StringVar(value=self.cfg.get("npc_map",""))
        self.npc_kind=tk.StringVar(value=self.cfg.get("npc_kind","mordon"))
        self.npc_kinds_saved=set(self.cfg.get("npc_kinds") or [self.npc_kind.get()])
        self.cfg["npc_profiles"]=normalize_npc_profiles(self.cfg.get("npc_profiles"))
        self.npc_kind_vars={}
        self.npc_min_hp=tk.StringVar(value=str(self.cfg.get("npc_min_hp",40)))
        self.npc_orbit=tk.BooleanVar(value=self.cfg.get("npc_orbit",True))
        self.npc_ammo=tk.StringVar(value=self.cfg.get("npc_ammo","lcb10"))
        self.npc_rocket=tk.StringVar(value=self.cfg.get("npc_rocket","none"))
        self.npc_radius=tk.StringVar(value=str(self.cfg.get("npc_radius",450)))
        self.npc_repair=tk.BooleanVar(value=self.cfg.get("npc_repair",False))
        self.pursuit_enabled=tk.BooleanVar(value=self.cfg.get("pursuit_enabled",False))
        self.npc_portal_fight=tk.BooleanVar(value=self.cfg.get("npc_portal_fight",False))
        self.last_npc_report=None
        self.combat_status=tk.StringVar(value="Farm contínuo: alvos marcados, munições escolhidas e recuperação por vida.")
        self.combat_report_status=tk.StringVar(value="Registro ainda não iniciado.")
        self.map_boxes=[]
        self.cloak_enabled=tk.BooleanVar(value=self.cfg.get("cloak",False))
        self.cloak_status=tk.StringVar(value="Camuflagem automática desativada." if not self.cloak_enabled.get() else "Camuflagem aguardando início da coleta.")
        self.green = tk.BooleanVar(value=self.cfg.get("green",False))
        self.reconnect = tk.BooleanVar(value=self.cfg.get("reconnect",True))
        self.respawn = tk.StringVar(value=self.cfg.get("respawn","Desativado"))
        self.max_deaths = tk.StringVar(value=str(self.cfg.get("max_deaths",3)))
        self.max_cost = tk.StringVar(value=str(self.cfg.get("max_cost",0)))
        self.death_state = {"ids":set(),"count":0}
        self.death_label = tk.StringVar(value="Mortes nesta sessão: 0")
        self.repair_label = tk.StringVar(value="Custos de renascimento aparecem quando a nave morrer.")
        self.earnings = SessionEarnings()
        self.earnings_elapsed=0.
        self.earnings_last=None
        self.earnings_active=False
        self.account_vars = {key:tk.StringVar(value="—") for key in ("uridium","credits","xp","honor","level","earned","last_hour","hourly","booty_keys")}
        self.data_planner = DataFarmPlanner(arrival_radius=180)
        self.farm_plan = tk.StringVar(value="Aguardando dados para planejar.")
        self.manual_probe_status = tk.StringVar(value="Registre uma coleta manual para validar o comando.")
        root.title("AutoBoxV — " + updater.CURRENT_VERSION)
        root.geometry("940x" + str(min(820, root.winfo_screenheight()-90)))
        root.minsize(760,min(620,root.winfo_screenheight()-80))
        self._draw()
        self._draw_world_page()
        self._draw_combat_page()
        self._draw_services()
        self.cockpit = Cockpit(root, self)
        self.compact = False
        self.full_geometry = "940x"+str(min(820,root.winfo_screenheight()-90))
        self.set_compact(self.cfg.get("compact_view", True))
        self._bind_keys()
        root.after(100, self._drain)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#111827", foreground="#e5e7eb",
                        font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 10), fieldbackground="#1f2937")
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb")
        style.configure("Muted.TLabel", foreground="#94a3b8")
        style.configure("Title.TLabel", font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 18, "bold"), foreground="#f8fafc")
        style.configure("Heading.TLabel", font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 13, "bold"))
        style.configure("Card.TFrame", background="#1e293b")
        style.configure("Card.TLabel", background="#1e293b", foreground="#94a3b8")
        style.configure("Count.TLabel", background="#1e293b", foreground="#67e8f9",
                        font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 20, "bold"))
        style.configure("Balance.TLabel", background="#1e293b", foreground="#f8fafc", font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 23, "bold"))
        style.configure("Income.TLabel", background="#1e293b", foreground="#4ade80", font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 16, "bold"))
        style.configure("HP.Horizontal.TProgressbar",background="#22c55e",troughcolor="#263449")
        style.configure("Shield.Horizontal.TProgressbar",background="#3b82f6",troughcolor="#263449")
        style.configure("Compact.TButton",padding=(8,4))
        style.configure("BalanceName.TLabel", background="#1e293b", foreground="#94a3b8", font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"), 11))
        style.configure("TButton", background="#263449", padding=(12,8))
        style.map("TButton", background=[("active","#334b68"),("disabled","#1e293b")],
                  foreground=[("disabled","#64748b")])
        style.configure("Start.TButton", background="#0e7490", foreground="white")
        style.map("Start.TButton", background=[("active","#0891b2")])
        style.configure("TNotebook", background="#111827", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", padding=(14,10))
        style.map("TNotebook.Tab", background=[("selected","#155e75")],
                  foreground=[("disabled","#64748b"),("selected","#f8fafc")])
        style.configure("TLabelframe", background="#111827", bordercolor="#334155")
        style.configure("TLabelframe.Label", background="#111827", foreground="#67e8f9")
        style.configure("TEntry", fieldbackground="#1e293b", foreground="#f8fafc", insertcolor="white")
        style.configure("TCheckbutton", background="#111827", foreground="#e5e7eb")
        style.map("TCheckbutton", background=[("active","#111827")])
        for name in ("TEntry","TCombobox","TSpinbox"):
            style.configure(name,fieldbackground="#1e293b",background="#334155",foreground="#f8fafc",arrowcolor="#f8fafc",insertcolor="#f8fafc")
            style.map(name,fieldbackground=[("disabled","#263449"),("readonly","#1e293b"),("!disabled","#1e293b")],
                      foreground=[("disabled","#94a3b8"),("!disabled","#f8fafc")],
                      selectbackground=[("!disabled","#155e75")],selectforeground=[("!disabled","#ffffff")])
        style.configure("Treeview",background="#111827",fieldbackground="#111827",foreground="#e5e7eb",rowheight=26)
        style.map("Treeview",background=[("selected","#155e75")],foreground=[("selected","#ffffff")])
        style.configure("Treeview.Heading",background="#263449",foreground="#f8fafc")
        style.map("Treeview.Heading",background=[("active","#334155")],foreground=[("active","#ffffff")])
        style.map("TCheckbutton",foreground=[("disabled","#94a3b8"),("active","#f8fafc")],
                  indicatorbackground=[("selected","#0e7490"),("!selected","#334155")],indicatorforeground=[("selected","#ffffff")])
        for option,value in (("background","#1e293b"),("foreground","#f8fafc"),("selectBackground","#155e75"),("selectForeground","#ffffff")):
            self.root.option_add("*TCombobox*Listbox."+option,value)
        self.root.configure(background="#111827")

    def _scroll_page(self, parent):
        canvas = tk.Canvas(parent, background="#111827", highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas, padding=16)
        item = canvas.create_window((0,0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        return body

    def _draw(self):
        self._theme()
        shell = ttk.Frame(self.root, padding=16)
        self.main_shell = shell
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0,14))
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="AutoBoxV", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Interstellar  •  versão "+updater.CURRENT_VERSION,
                  style="Muted.TLabel").pack(anchor="w")
        connection = ttk.Frame(header); connection.pack(side="right")
        ttk.Label(connection, textvariable=self.session_label, style="Heading.TLabel").pack(anchor="e")
        ttk.Label(connection, textvariable=self.running_label, style="Muted.TLabel").pack(anchor="e")

        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True)
        self.pages = {}
        for key, title in (("dashboard","Painel"),("data","Coleta"),("combat","Kill NPC"),("galaxy","Galaxy Gate"),("skylab","Skylab"),("advanced","Avançado")):
            page=ttk.Frame(self.notebook)
            self.pages[key]=page
            self.notebook.add(page,text=title)
        advanced=ttk.Notebook(self.pages["advanced"])
        advanced.pack(fill="both",expand=True)
        for key,title in (("browser","Navegador"),("diagnostics","Diagnóstico")):
            page=ttk.Frame(advanced)
            self.pages[key]=page
            advanced.add(page,text=title)

        dashboard = self._scroll_page(self.pages["dashboard"])
        dashboard.configure(padding=8)
        toolbar=ttk.Frame(dashboard);toolbar.pack(fill="x",pady=(0,8))
        ttk.Button(toolbar,text="Iniciar jogo",command=self.open_browser,style="Compact.TButton").pack(side="left")
        ttk.Button(toolbar,text="Modo compacto",command=lambda:self.set_compact(True),style="Compact.TButton").pack(side="left",padx=6)
        ttk.Button(toolbar,text="Verificar atualizações",command=self.check_updates,style="Compact.TButton").pack(side="right")
        balances=ttk.Frame(dashboard);balances.pack(fill="x")
        for col,(key,label) in enumerate((("uridium","Uridium total"),("credits","Créditos"))):
            balances.columnconfigure(col,weight=1,uniform="balance")
            card=ttk.Frame(balances,padding=6,style="Card.TFrame");card.grid(row=0,column=col,sticky="ew",padx=(0,6) if col==0 else 0)
            ttk.Label(card,text=label,style="Card.TLabel").pack(anchor="w")
            ttk.Label(card,textvariable=self.account_vars[key],style="Balance.TLabel").pack(anchor="w")
        income=ttk.LabelFrame(dashboard,text="Rendimento do farm",padding=4);income.pack(fill="x",pady=6)
        for col,(key,label) in enumerate((("last_hour","Última hora"),("hourly","Média por hora"))):
            income.columnconfigure(col,weight=1,uniform="income")
            card=ttk.Frame(income,style="Card.TFrame",padding=6);card.grid(row=0,column=col,sticky="ew",padx=2)
            ttk.Label(card,text=label,style="Card.TLabel").pack(anchor="w")
            ttk.Label(card,textvariable=self.account_vars[key],style="Income.TLabel").pack(anchor="w")
        details=ttk.Frame(dashboard);details.pack(fill="x",pady=4)
        for col,(key,label) in enumerate((("xp","XP"),("honor","Honra"),("level","Nível"),("booty_keys","Chaves verdes"))):
            details.columnconfigure(col,weight=1)
            cell=ttk.Frame(details);cell.grid(row=0,column=col,sticky="w")
            ttk.Label(cell,text=label,style="Muted.TLabel").pack(side="left",padx=(0,6))
            ttk.Label(cell,textvariable=self.account_vars[key]).pack(side="left")
        stats=ttk.LabelFrame(dashboard,text="Estatísticas da coleta",padding=6);stats.pack(fill="x",pady=4)
        for col,(key,label) in enumerate((("attempts","Tentativas"),("confirmed","Confirmadas"),("failed","Sem progresso"))):
            stats.columnconfigure(col,weight=1)
            cell=ttk.Frame(stats);cell.grid(row=0,column=col,sticky="w")
            ttk.Label(cell,text=label+": ",style="Muted.TLabel").pack(side="left")
            ttk.Label(cell,textvariable=self.counter_vars[key]).pack(side="left")
        ship=ttk.LabelFrame(dashboard,text="Situação da nave",padding=4);ship.pack(fill="x",pady=4)
        self.vitals_bars={}
        for col,(key,label,style) in enumerate((("hp","HP","HP.Horizontal.TProgressbar"),("shield","Escudo","Shield.Horizontal.TProgressbar"))):
            ship.columnconfigure(col,weight=1,uniform="vitals")
            cell=ttk.Frame(ship);cell.grid(row=0,column=col,sticky="ew",padx=4)
            ttk.Label(cell,text=label).pack(side="left")
            ttk.Label(cell,textvariable=self.vitals_text[key]).pack(side="right")
            bar=ttk.Progressbar(ship,maximum=100,style=style);bar.grid(row=1,column=col,sticky="ew",padx=4,pady=4)
            self.vitals_bars[key]=bar
        ttk.Label(ship,textvariable=self.map_summary,style="Muted.TLabel").grid(row=2,column=0,columnspan=2,sticky="w")
        quick=ttk.Frame(dashboard);quick.pack(fill="x",pady=4)
        self.quick_buttons={}
        for row,(mode,title,state,commands) in enumerate((
            ("collect","Farm de coleta",self.collect_summary,(self.start,self.pause,self.stop)),
            ("npc","NPC Killer",self.npc_summary,(self.start_npc_test,self.pause_npc,self.stop_npc)))):
            group=ttk.LabelFrame(quick,text=title,padding=4);group.pack(fill="x",pady=3)
            ttk.Label(group,textvariable=state,wraplength=370).pack(side="left",fill="x",expand=True)
            for action,command in zip(("Iniciar","Pausar","Parar"),commands):
                button=ttk.Button(group,text=action,command=command,style="Compact.TButton",width=9)
                button.pack(side="left",padx=2);self.quick_buttons[(mode,action)]=button
        ttk.Label(dashboard,textvariable=self.combat_status,wraplength=720,style="Muted.TLabel").pack(anchor="w",pady=3)
        recent=ttk.Frame(dashboard);recent.pack(fill="x")
        ttk.Label(recent,text="Atividades recentes").pack(side="left")
        ttk.Button(recent,text="Parar tudo",command=self.stop_all,style="Compact.TButton").pack(side="right")
        self.log=tk.Text(dashboard,height=3,state="disabled",wrap="word",background="#0b1220",
                         foreground="#cbd5e1",relief="flat",padx=8,pady=4,font=(("Segoe UI" if os.name=="nt" else "DejaVu Sans"),9))
        self.log.pack(fill="x",pady=4)

        browser=self._scroll_page(self.pages["browser"])
        ttk.Label(browser,text="Sessão dedicada do Opera GX",style="Heading.TLabel").pack(anchor="w",pady=(0,12))
        ttk.Button(browser,text="Abrir Opera GX e entrar no jogo",command=self.open_browser).pack(fill="x",pady=4)
        ttk.Button(browser,text="Localizar executável do Opera GX",command=self.choose_opera).pack(fill="x",pady=4)
        ttk.Label(browser,textvariable=self.session_label).pack(anchor="w",pady=12)
        ttk.Label(browser,text="Faça login na janela aberta pelo bot. Mantenha essa janela aberta; o computador pode ser usado para outras tarefas. O uso com a janela minimizada ainda precisa de validação.",
                  wraplength=650,style="Muted.TLabel").pack(anchor="w")

        diagnostics=self._scroll_page(self.pages["diagnostics"])
        self.diagnostics_body=diagnostics
        ttk.Label(diagnostics,text="Diagnóstico da coleta por dados",style="Heading.TLabel").pack(anchor="w")

    def _draw_world_page(self):
        body = self._scroll_page(self.pages["data"])
        self._map_controls(body,self.collect_map,"coleta")
        ttk.Label(body,text="Dados ao vivo do jogo",style="Heading.TLabel").pack(anchor="w")
        ttk.Label(body,text="Coleta por ID e coordenadas. F8 inicia; F9 pausa.",
                  wraplength=650,style="Muted.TLabel").pack(anchor="w",pady=(4,12))
        group=ttk.LabelFrame(body,text="Estado recebido pela janela dedicada",padding=14)
        group.pack(fill="x")
        for row,(key,label) in enumerate((("status","Leitura"),("map","Mapa"),("position","Posição da nave"),
                                          ("hp","Vida"),("counts","Objetos"),("nearest","Box mais próxima"),
                                          ("distance","Distância da mais próxima"),("sequence","Atualização"))):
            ttk.Label(group,text=label).grid(row=row,column=0,sticky="nw",padx=(0,18),pady=5)
            ttk.Label(group,textvariable=self.world_vars[key],wraplength=520).grid(row=row,column=1,sticky="w",pady=5)
        group.columnconfigure(1,weight=1)
        plan=ttk.LabelFrame(body,text="Preferências de coleta",padding=12)
        plan.pack(fill="x",pady=10)
        ttk.Checkbutton(plan,text="Coletar caixas verdes usando minhas chaves (não compra chaves)",
                        variable=self.green,command=self.save).pack(anchor="w",pady=4)
        ttk.Checkbutton(plan,text="Reconectar e retomar após perda de conexão",
                        variable=self.reconnect,command=self.save).pack(anchor="w",pady=4)
        ttk.Label(plan,textvariable=self.farm_plan,wraplength=650).pack(anchor="w")
        recovery=ttk.LabelFrame(body,text="Quando a nave morrer",padding=12)
        recovery.pack(fill="x",pady=6)
        ttk.Label(recovery,text="Renascimento automático").grid(row=0,column=0,sticky="w")
        ttk.Combobox(recovery,textvariable=self.respawn,state="readonly",
                     values=("Desativado","Base","Portal","Local")).grid(row=0,column=1,sticky="ew",pady=4)
        ttk.Label(recovery,text="Parar ao atingir este total de mortes").grid(row=1,column=0,sticky="w")
        ttk.Spinbox(recovery,from_=1,to=100,textvariable=self.max_deaths,width=8).grid(row=1,column=1,sticky="w",pady=4)
        ttk.Label(recovery,text="Custo máximo por renascimento (Uridium)").grid(row=2,column=0,sticky="w")
        ttk.Spinbox(recovery,from_=0,to=100000,textvariable=self.max_cost,width=8).grid(row=2,column=1,sticky="w",pady=4)
        ttk.Label(recovery,textvariable=self.death_label).grid(row=3,column=0,columnspan=2,sticky="w",pady=4)
        ttk.Label(recovery,textvariable=self.repair_label,wraplength=650).grid(row=4,column=0,columnspan=2,sticky="w",pady=4)
        ttk.Label(recovery,text="Local pode renascer com pouca vida; a coleta aguarda recuperação manual.",
                  style="Muted.TLabel",wraplength=650).grid(row=5,column=0,columnspan=2,sticky="w",pady=4)
        ttk.Button(recovery,text="Salvar preferências",command=self.save).grid(row=6,column=0,sticky="w",pady=4)
        plan=self.diagnostics_body


        ttk.Button(plan,text="Registrar uma coleta manual (30 segundos)",
                   command=self.record_manual_collect).pack(fill="x",pady=(10,4))
        ttk.Button(plan,text="Copiar diagnóstico da coleta",
                   command=self.copy_collect_diagnostic).pack(fill="x",pady=4)
        ttk.Button(plan,text="Exportar integração do cliente",
                   command=self.export_client_integration).pack(fill="x",pady=4)
        ttk.Label(plan,textvariable=self.manual_probe_status,wraplength=650,style="Muted.TLabel").pack(anchor="w",pady=4)
        ttk.Label(body,text="Abra o jogo pela aba Navegador e entre no mapa. A leitura é automática. Se pedir um estado completo, recarregue a janela dedicada uma vez com o bot pausado.",
                  wraplength=650,style="Muted.TLabel").pack(anchor="w",pady=12)


    def _map_controls(self, parent, variable, mode):
        frame=ttk.LabelFrame(parent,text="Mapa de "+mode,padding=10)
        frame.pack(fill="x",pady=(0,10))
        ttk.Label(frame,text="Destino (vazio = mapa atual)").grid(row=0,column=0,sticky="w")
        box=ttk.Combobox(frame,textvariable=variable,width=16)
        box.grid(row=0,column=1,sticky="ew",padx=8)
        self.map_boxes.append(box)
        ttk.Button(frame,text="Ir ao mapa",command=lambda:self.start_trip(variable.get())).grid(row=0,column=2)
        ttk.Label(frame,text="Selecione um mapa da lista ou digite, por exemplo 4-3. A viagem usa portais normais.",
                  style="Muted.TLabel",wraplength=650).grid(row=1,column=0,columnspan=3,sticky="w",pady=6)
        ttk.Button(frame,text="Salvar mapa",command=self.save).grid(row=2,column=0,sticky="w")

    def _draw_combat_page(self):
        body=self._scroll_page(self.pages["combat"])
        ttk.Label(body,text="Kill NPC — farm contínuo",style="Heading.TLabel").pack(anchor="w",pady=(0,8))
        ttk.Label(body,textvariable=self.combat_status,wraplength=680).pack(anchor="w",pady=(0,10))
        controls=ttk.Frame(body)
        controls.pack(fill="x",pady=8)
        for text,command in (("Iniciar NPC",self.start_npc_test),("Pausar NPC",self.pause_npc),("Parar NPC",self.stop_npc)):
            ttk.Button(controls,text=text,command=command).pack(side="left",expand=True,fill="x",padx=3)
        ttk.Label(body,textvariable=self.npc_summary).pack(anchor="w",pady=4)
        self._map_controls(body,self.npc_map,"NPC")
        test=ttk.LabelFrame(body,text="Farm de NPCs",padding=10)
        test.pack(fill="x",pady=6)
        ttk.Label(test,text="Tipos de NPC (marque um ou mais)").grid(row=0,column=0,sticky="nw")
        self.npc_choices=ttk.Frame(test)
        self.npc_choices.grid(row=0,column=1,sticky="ew",pady=4)
        self._sync_npc_choices(self.npc_kinds_saved | {"mordon"})
        ttk.Label(test,text="Interromper tiros com vida em (%)").grid(row=1,column=0,sticky="w")
        ttk.Spinbox(test,from_=25,to=75,textvariable=self.npc_min_hp,width=8).grid(row=1,column=1,sticky="w",pady=4)
        ttk.Checkbutton(test,text="Circular ao redor do NPC",variable=self.npc_orbit).grid(row=2,column=0,columnspan=2,sticky="w")
        ttk.Label(test,text="Distância desejada (150 a 800)").grid(row=3,column=0,sticky="w")
        ttk.Spinbox(test,from_=150,to=800,textvariable=self.npc_radius,width=8).grid(row=3,column=1,sticky="w")
        ttk.Checkbutton(test,text="Vida no limite: ir ao portal e ativar reparador",variable=self.npc_repair).grid(row=4,column=0,columnspan=2,sticky="w")
        ttk.Checkbutton(test,text="Levar o NPC ao portal e lutar ao redor (experimental)",variable=self.npc_portal_fight).grid(row=5,column=0,columnspan=2,sticky="w")
        ttk.Label(test,text="Laser").grid(row=6,column=0,sticky="w")
        ttk.Combobox(test,textvariable=self.npc_ammo,state="readonly",values=("lcb10","mcb25","mcb50","ucb100","sab50","rsb75")).grid(row=6,column=1,sticky="w")
        ttk.Label(test,text="Míssil (none = desativado)").grid(row=7,column=0,sticky="w")
        ttk.Combobox(test,textvariable=self.npc_rocket,state="readonly",values=("none","r310","plt2026","plt2021","plt3030")).grid(row=7,column=1,sticky="w")
        ttk.Label(test,text="Com pouca vida ao iniciar, o bot repara no portal antes de lutar. Tenha estoque das munições escolhidas. Laser sem confirmação de seleção encerra o farm; míssil vazio não é comprado. "
            "Os botões Pausar NPC e Parar NPC interrompem o combate. Distância não garante evitar dano. Reparo depende do equipamento e de 15 segundos sem combate; não pula o portal; após recuperar 90% de vida, o farm retoma.",
            wraplength=680,style="Muted.TLabel").grid(row=9,column=0,columnspan=2,sticky="w")
        pursuit=ttk.LabelFrame(body,text="Perseguição para finalização",padding=10)
        pursuit.pack(fill="x",pady=6)
        ttk.Checkbutton(pursuit,text="Perseguir de perto para finalizar",variable=self.pursuit_enabled).pack(anchor="w")
        ttk.Label(pursuit,text="Segue bem perto do NPC em fuga com até 20% de vida, ignorando a distância normal de combate. Mantém as proteções de vida, mapa e falta de progresso. Lutar junto ao portal tem prioridade.",wraplength=650).pack(anchor="w")
        shop=ttk.LabelFrame(body,text="Reposição automática de munições",padding=10)
        shop.pack(fill="x",pady=8)
        ttk.Checkbutton(shop,text="Comprar o laser selecionado acima",variable=self.buy_laser).pack(anchor="w")
        ttk.Checkbutton(shop,text="Comprar o míssil selecionado acima",variable=self.buy_missile).pack(anchor="w")
        for key,label in (("laser_threshold","Comprar laser quando estoque ≤"),("laser_quantity","Quantidade de laser por compra"),
                          ("missile_threshold","Comprar míssil quando estoque ≤"),("missile_quantity","Quantidade de mísseis por compra"),
                          ("reserve_uri","Manter no mínimo este uridium"),("reserve_credits","Manter no mínimo estes créditos")):
            row=ttk.Frame(shop);row.pack(fill="x",pady=2)
            ttk.Label(row,text=label).pack(side="left")
            ttk.Entry(row,textvariable=self.buy_fields[key],width=12).pack(side="right")
        ttk.Label(shop,text="Usa o preço e a moeda da loja. Compra apenas os tipos marcados, enquanto o farm está ativo. Se o cliente não confirmar preço, moeda ou estoque, interrompe e informa o motivo.",wraplength=650).pack(anchor="w")
        ttk.Label(body,text="NPCs presentes no mapa",style="Heading.TLabel").pack(anchor="w",pady=6)
        self.npc_table=ttk.Treeview(body,columns=("kind","hp","distance"),show="headings",height=5)
        for name,title,width in (("kind","Tipo de NPC",230),("hp","Vida",140),("distance","Distância",140)):
            self.npc_table.heading(name,text=title)
            self.npc_table.column(name,width=width,stretch=True)
        self.npc_table.pack(fill="x",pady=6)
        profiles=ttk.LabelFrame(body,text="Perfil por NPC • prioridade menor vem primeiro",padding=10)
        profiles.pack(fill="x",pady=6)
        self.profile_kind=tk.StringVar(value="mordon")
        self.profile_ammo=tk.StringVar(value=self.npc_ammo.get())
        self.profile_priority=tk.StringVar(value="0")
        self.profile_radius=tk.StringVar(value=self.npc_radius.get())
        self.profile_orbit=tk.BooleanVar(value=self.npc_orbit.get())
        self.profile_choices=ttk.Combobox(profiles,textvariable=self.profile_kind,values=sorted(self.npc_kind_vars),width=16,state="readonly")
        self.profile_choices.grid(row=0,column=0,sticky="w",padx=3)
        self.profile_choices.bind("<<ComboboxSelected>>",lambda e:self.load_npc_profile())
        ttk.Label(profiles,text="Laser").grid(row=0,column=1)
        ttk.Combobox(profiles,textvariable=self.profile_ammo,state="readonly",width=10,
                     values=("lcb10","mcb25","mcb50","ucb100","sab50","rsb75")).grid(row=0,column=2,padx=3)
        ttk.Label(profiles,text="Prioridade").grid(row=1,column=0,sticky="w")
        ttk.Spinbox(profiles,textvariable=self.profile_priority,from_=-100,to=100,width=8).grid(row=1,column=1)
        ttk.Label(profiles,text="Distância").grid(row=1,column=2)
        ttk.Spinbox(profiles,textvariable=self.profile_radius,from_=150,to=800,width=8).grid(row=1,column=3)
        ttk.Checkbutton(profiles,text="Circular",variable=self.profile_orbit).grid(row=2,column=0,sticky="w")
        ttk.Button(profiles,text="Salvar perfil",command=self.save_npc_profile).grid(row=2,column=1,pady=5)
        ttk.Button(profiles,text="Usar padrão",command=self.remove_npc_profile).grid(row=2,column=2)
        self.profile_table=ttk.Treeview(profiles,columns=("npc","priority","ammo","radius","orbit"),show="headings",height=4)
        for key,label in (("npc","NPC"),("priority","Prioridade"),("ammo","Laser"),("radius","Distância"),("orbit","Circular")):
            self.profile_table.heading(key,text=label);self.profile_table.column(key,width=100)
        self.profile_table.grid(row=3,column=0,columnspan=4,sticky="ew")
        ttk.Label(profiles,text="Perfis valem no próximo início. NPC sem perfil usa as opções gerais acima.",style="Muted.TLabel").grid(row=4,column=0,columnspan=4,sticky="w",pady=4)
        self.refresh_profile_table()
        performance=ttk.LabelFrame(body,text="Desempenho por NPC nesta sessão",padding=10)
        performance.pack(fill="x",pady=6)
        self.performance_table=ttk.Treeview(performance,columns=("npc","kills","average","last","ammo"),show="headings",height=4)
        for key,label in (("npc","NPC"),("kills","Derrotados"),("average","Média/ciclo"),("last","Último ciclo"),("ammo","Laser")):
            self.performance_table.heading(key,text=label);self.performance_table.column(key,width=100)
        self.performance_table.pack(fill="x")
        ttk.Label(performance,text="Tempo por ciclo inclui aproximação e confirmação. Estatísticas não trocam sua munição automaticamente.",style="Muted.TLabel",wraplength=650).pack(anchor="w",pady=4)
        ttk.Label(body,text="Teste manual (até 90 segundos):\n1. Clique em Registrar luta.\n"
            "2. No jogo, selecione um NPC fraco e ataque com a munição básica.\n"
            "3. Pare o ataque uma vez e depois ataque novamente até derrotá-lo, se for seguro.\n"
            "4. Clique em Encerrar registro e em Copiar diagnóstico da luta.",
            wraplength=680).pack(anchor="w",pady=10)
        ttk.Button(body,text="Registrar luta manual (90 segundos)",command=self.record_combat).pack(fill="x",pady=4)
        ttk.Button(body,text="Encerrar registro",command=self.finish_combat_recording).pack(fill="x",pady=4)
        ttk.Button(body,text="Copiar diagnóstico da luta",command=self.copy_combat_report).pack(fill="x",pady=4)
        ttk.Label(body,textvariable=self.combat_report_status,wraplength=680,style="Muted.TLabel").pack(anchor="w",pady=8)
        ttk.Label(body,text="O registro manual só observa. Iniciar farm de NPCs continua após cada derrota confirmada. Pausar/Parar NPC encerram o combate; F8/F9/F10 controlam a coleta.",
                  wraplength=680,style="Muted.TLabel").pack(anchor="w",pady=8)

    def _draw_services(self):
        body=self._scroll_page(self.pages["galaxy"])
        ttk.Label(body,text="Galaxy Gate — energias",style="Heading.TLabel").pack(anchor="w")
        ttk.Checkbutton(body,text="Habilitar giros automáticos nesta sessão",variable=self.gg_enabled).pack(anchor="w",pady=8)
        ttk.Label(body,text="Gate de destino").pack(anchor="w")
        ttk.Combobox(body,textvariable=self.gg_gate,state="readonly",values=("alpha","beta","gamma","delta","epsilon","zeta","kappa","lambda")).pack(anchor="w")
        row=ttk.Frame(body);row.pack(fill="x",pady=8)
        for n,var in self.gg_sizes.items():ttk.Checkbutton(row,text=str(n)+"x",variable=var).pack(side="left")
        ttk.Label(body,text="Usa o maior lote marcado que caiba no saldo e no limite. Marque 1x para consumir sobras.").pack(anchor="w")
        ttk.Label(body,text="Limite total de energias por execução (extras + pagas)").pack(anchor="w",pady=(10,0))
        ttk.Entry(body,textvariable=self.gg_limit).pack(anchor="w")
        ttk.Checkbutton(body,text="Permitir uridium após consumir as energias extras",variable=self.gg_uri).pack(anchor="w",pady=10)
        ttk.Label(body,text="Parar antes de o uridium ficar abaixo de").pack(anchor="w")
        ttk.Entry(body,textvariable=self.gg_reserve).pack(anchor="w")
        ttk.Button(body,text="Iniciar giros",command=self.start_galaxy).pack(fill="x",pady=8)
        ttk.Button(body,text="Parar giros",command=self.gg_stop.set).pack(fill="x")
        ttk.Label(body,textvariable=self.gg_status,wraplength=650).pack(anchor="w",pady=10)
        body=self._scroll_page(self.pages["skylab"])
        ttk.Label(body,text="Skylab — melhorias até nível 20",style="Heading.TLabel").pack(anchor="w")
        ttk.Label(body,text="Abra o Skylab no jogo e mantenha o painel aberto. Constrói um módulo por vez com créditos e minérios; aguarda a conclusão antes do próximo. Transporte termina no nível 1.",wraplength=650).pack(anchor="w",pady=8)
        ttk.Label(body,text="Reserva mínima de créditos").pack(anchor="w")
        ttk.Entry(body,textvariable=self.skylab_reserve,width=18).pack(anchor="w")
        buttons=ttk.Frame(body);buttons.pack(fill="x",pady=8)
        ttk.Button(buttons,text="Iniciar melhorias",command=self.start_skylab).pack(side="left",padx=(0,6))
        ttk.Button(buttons,text="Parar Skylab",command=self.stop_skylab).pack(side="left")
        ttk.Label(body,textvariable=self.skylab_status,wraplength=650).pack(anchor="w",pady=6)
        self.skylab_table=ttk.Treeview(body,columns=("module","level","status","remaining"),show="headings",height=12)
        for key,title,width in (("module","Módulo",180),("level","Nível",65),("status","Situação",180),("remaining","Tempo restante",120)):
            self.skylab_table.heading(key,text=title);self.skylab_table.column(key,width=width,minwidth=60)
        self.skylab_table.pack(fill="x",pady=8)
        ttk.Label(body,text="Não gasta Uridium, não compra robôs, não transfere recursos e não liga ou desliga módulos. Parar impede novas melhorias; não cancela uma construção já aceita pelo jogo. Não retoma sozinho ao reabrir o bot.",wraplength=650).pack(anchor="w",pady=6)
        ttk.Button(body,text="Exportar integração para diagnóstico",command=self.export_client_integration).pack(fill="x")
        cloak=ttk.LabelFrame(self.pages["data"],text="Camuflagem na coleta",padding=8)
        cloak.pack(fill="x",pady=6)
        ttk.Checkbutton(cloak,text="Manter nave camuflada (usa cargas da CPU equipada)",variable=self.cloak_enabled,command=self.save).pack(anchor="w")
        ttk.Label(cloak,textvariable=self.cloak_status,wraplength=650).pack(anchor="w")
        ttk.Label(cloak,text="Não compra CPUs. Aguarda o fim dos tiros e a recarga. Alterações valem no próximo início da coleta.",wraplength=650).pack(anchor="w")


    def skylab_active(self):
        return self.skylab_worker is not None and self.skylab_worker.is_alive()

    def stop_skylab(self):
        self.skylab_stop.set()
        self.skylab_status.set("Skylab encerrando. Uma construção já enviada pode continuar no jogo.")

    def start_skylab(self):
        if self.closing or self.skylab_active():return
        if self.gg_active():
            self.skylab_status.set("Pare os giros do Galaxy Gate antes de iniciar o Skylab.");return
        if not self.session.ready.is_set():
            self.skylab_status.set("Abra o jogo pelo bot e depois o Skylab no jogo.");return
        try:
            reserve=int(self.skylab_reserve.get())
            if not 0<=reserve<=1000000000:raise ValueError()
        except ValueError:
            self.skylab_status.set("Informe uma reserva de créditos entre 0 e 1.000.000.000.");return
        self.cfg["skylab_reserve"]=reserve
        if not self.save():return
        self.skylab_stop.clear()
        engine=SkylabWorker(self.session,self.skylab_stop,lambda e,d:self.events.put((e,d)),reserve=reserve)
        self.skylab_worker=threading.Thread(target=engine.run,daemon=True)
        self.skylab_worker.start()
        self.skylab_status.set("Skylab iniciado. Lendo módulos e recursos.")

    def update_skylab_rows(self,rows):
        reasons={"concluido":"Concluído","construindo":"Construindo","pronto":"Pronto",
                 "modulo_basico":"Aguarda módulo básico","creditos":"Aguarda créditos",
                 "minerios":"Aguarda minérios","energia":"Aguarda energia"}
        for row in rows:
            seconds=int(row.get("remaining",0))
            remaining=(str(seconds//3600)+"h "+str(seconds%3600//60)+"m "+str(seconds%60)+"s") if row.get("job") else "—"
            values=(row["name"],str(row["level"])+"/"+str(row["max"]),reasons.get(row["reason"],row["reason"]),remaining)
            if self.skylab_table.exists(row["id"]):self.skylab_table.item(row["id"],values=values)
            else:self.skylab_table.insert("","end",iid=row["id"],values=values)

    def gg_active(self):
        return self.gg_worker is not None and self.gg_worker.is_alive()

    def start_galaxy(self):
        if self.closing or self.gg_active(): return
        if self.skylab_active():
            self.gg_status.set("Pare o Skylab antes de girar energias.");return
        if not self.gg_enabled.get():
            self.gg_status.set("Marque Habilitar giros automáticos antes de iniciar.");return
        if self.npc_active() or (self.worker is not None and self.worker.is_alive()):
            self.gg_status.set("Pause coleta, viagem e combate antes de girar energias.");return
        if not self.session.ready.is_set():
            self.gg_status.set("Abra o jogo e aguarde os dados ao vivo.");return
        try:
            limit=int(self.gg_limit.get());reserve=int(self.gg_reserve.get())
            sizes=[n for n,v in self.gg_sizes.items() if v.get()]
            if not 1<=limit<=100000 or not 0<=reserve<=1000000000 or not sizes:raise ValueError()
        except ValueError:
            self.gg_status.set("Informe limite de 1 a 100000, reserva válida e ao menos um lote.");return
        self.cfg.update(gg_gate=self.gg_gate.get(),gg_reserve=reserve,gg_limit=limit,gg_sizes=sizes)
        if not self.save():return
        self.gg_stop.clear()
        engine=GalaxyWorker(self.session,self.gg_stop,lambda e,d:self.events.put(("gg_status",d)),
            dict(gate=self.gg_gate.get(),limit=limit,reserve=reserve,sizes=sizes,allow_uri=self.gg_uri.get()))
        self.gg_worker=threading.Thread(target=engine.run,daemon=True);self.gg_worker.start()
        self.gg_status.set("Giros iniciados. Aguardando confirmação de cada lote.")

    def _sync_npc_choices(self,kinds):
        for kind in sorted(set(kinds)|self.npc_kinds_saved):
            if kind in self.npc_kind_vars: continue
            if not isinstance(kind,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",kind): continue
            var=tk.BooleanVar(value=kind in self.npc_kinds_saved)
            index=len(self.npc_kind_vars)
            self.npc_kind_vars[kind]=var
            ttk.Checkbutton(self.npc_choices,text=kind,variable=var).grid(row=index//3,column=index%3,sticky="w",padx=5,pady=2)
        if hasattr(self,"profile_choices"):
            self.profile_choices.configure(values=sorted(set(self.npc_kind_vars)|set(self.cfg.get("npc_profiles",{}))))

    def refresh_profile_table(self):
        self.profile_table.delete(*self.profile_table.get_children())
        for kind,p in sorted(self.cfg.get("npc_profiles",{}).items()):
            self.profile_table.insert("","end",values=(kind,p["priority"],p["ammo"],p["radius"],"Sim" if p["orbit"] else "Não"))

    def load_npc_profile(self):
        p=self.cfg.get("npc_profiles",{}).get(self.profile_kind.get(),{})
        self.profile_priority.set(str(p.get("priority",0)))
        self.profile_ammo.set(p.get("ammo",self.npc_ammo.get()))
        self.profile_radius.set(str(p.get("radius",self.npc_radius.get())))
        self.profile_orbit.set(p.get("orbit",self.npc_orbit.get()))

    def save_npc_profile(self):
        try:
            kind=self.profile_kind.get();priority=int(self.profile_priority.get());radius=int(self.profile_radius.get())
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",kind) or not -100<=priority<=100 or not 150<=radius<=800:
                raise ValueError("Confira NPC, prioridade (-100 a 100) e distância (150 a 800).")
            if self.profile_ammo.get() not in ("lcb10","mcb25","mcb50","ucb100","sab50","rsb75"):
                raise ValueError("Laser inválido.")
            self.cfg["npc_profiles"][kind]=dict(priority=priority,radius=radius,ammo=self.profile_ammo.get(),orbit=self.profile_orbit.get())
            if self.save():self.refresh_profile_table();self.say("Perfil salvo. Vale no próximo início do farm.")
        except ValueError as exc:self.say(str(exc))

    def remove_npc_profile(self):
        self.cfg["npc_profiles"].pop(self.profile_kind.get(),None)
        if self.save():self.refresh_profile_table();self.load_npc_profile()

    def start_npc_test(self, hybrid=False):
        if self.gg_active():
            self.say("Pare os giros do Galaxy Gate antes de iniciar o farm.");return
        if self.closing: return
        if self.npc_active():
            self.combat_status.set("Farm em execução ou encerrando o ataque. Aguarde antes de iniciar novamente.")
            return
        if not self.save(): return
        if not self.session.ready.is_set():
            self.say("Abra o jogo e entre no mapa antes do farm."); return
        if self.worker is not None and self.worker.is_alive():
            self.say("Pause a coleta ou viagem com F9 antes de iniciar o farm de NPC."); return
        snapshot=self.session.get_world_snapshot()
        if not snapshot.get("fresh") or snapshot.get("dead"):
            self.say("Aguarde dados ao vivo com a nave viva."); return
        if snapshot.get("hp_percent") is None:
            self.say("Aguarde a leitura da vida antes do farm."); return
        self.session.combat_probe.stop("Registro manual encerrado para farm automático.")
        self.last_npc_report=None
        self.earnings.observe(snapshot,False)
        previous_kills=self.npc_engine.kills if self.npc_state=="paused" and self.npc_engine else 0
        self.npc_generation+=1
        generation=self.npc_generation
        self.npc_stop_event=threading.Event()
        engine=NpcFarmWorker(self.session,self.npc_stop_event,lambda event,data:self.events.put(("npc_event",(generation,event,data))),
            kind=self.cfg["npc_kinds"],destination=self.cfg.get("npc_map",""),min_hp=self.cfg["npc_min_hp"],orbit=self.npc_orbit.get(),radius=self.cfg["npc_radius"],repair_portal=self.npc_repair.get(),portal_fight=self.npc_portal_fight.get(),ammo=self.npc_ammo.get(),rocket=self.npc_rocket.get(),restock=dict(laser=self.buy_laser.get(),missile=self.buy_missile.get(),**{k:int(v.get()) for k,v in self.buy_fields.items()}),pursuit_enabled=self.pursuit_enabled.get(),npc_profiles=self.cfg.get("npc_profiles",{}),hybrid=hybrid,collect_settings={"green":self.green.get(),"cloak":self.cloak_enabled.get()})
        engine.kills=previous_kills
        if self.npc_state=="paused" and self.npc_engine and isinstance(getattr(self.npc_engine,"stats",None),dict):
            engine.stats=dict(self.npc_engine.stats)
        self.npc_engine=engine
        self.npc_state="running"
        self.npc_worker=threading.Thread(target=engine.run,daemon=True)
        self.npc_worker.start()
        self.combat_status.set("Farm contínuo iniciado: procura o próximo NPC marcado após cada derrota.")

    def npc_active(self):
        return self.npc_worker is not None and self.npc_worker.is_alive()

    def pause_npc(self):
        self.npc_stop_event.set()
        if self.npc_state!="stopped": self.npc_state="paused"
        self.combat_status.set("NPC pausado. Aguarde encerrar os tiros; Iniciar NPC retoma a busca e mantém o contador.")

    def stop_npc(self):
        self.npc_stop_event.set()
        self.npc_state="stopped"
        self.combat_status.set("NPC parado. Aguarde encerrar os tiros; o próximo início abre uma nova sessão.")

    def pause_all(self):
        self.skylab_stop.set()
        self.gg_stop.set()
        self.pause()
        self.pause_npc()

    def stop_all(self):
        self.skylab_stop.set()
        self.gg_stop.set()
        self.stop()
        self.stop_npc()

    def record_combat(self):
        self.skylab_stop.set()
        self.gg_stop.set()
        if self.gg_active():
            self.root.after(100,self.record_combat)
            return
        self.npc_stop_event.set()
        if self.npc_active():
            self.root.after(100,self.record_combat)
            return
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100,self.record_combat)
            return
        try:
            self.session.combat_probe.arm()
            self.say("Coleta pausada. Registro iniciado: selecione um NPC e faça a luta manual.")
        except ValueError as exc:
            self.say(str(exc))

    def finish_combat_recording(self):
        self.session.combat_probe.stop()
        self.combat_report_status.set(self.session.combat_probe.report()["status"])
        self.say("Registro encerrado. Copie o diagnóstico da luta e cole no chat.")

    def copy_combat_report(self):
        report=self.session.combat_probe.report()
        report["automatic_test"]=self.last_npc_report
        report["automatic_combat_commands_sent"]=None if self.last_npc_report else 0
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(report,ensure_ascii=False,indent=2))
        self.say("Diagnóstico da luta copiado. Cole no chat para validar o combate.")

    def start_trip(self,destination):
        if self.gg_active():
            self.say("Pare os giros do Galaxy Gate antes de viajar.");return
        if self.npc_active():
            self.say("Pause o farm na aba Kill NPC antes de iniciar uma viagem manual.")
            return
        destination=destination.strip()
        if not destination:
            self.say("Informe o mapa de destino para viajar.")
            return
        if not self.save(): return
        if not self.session.ready.is_set():
            self.say("Abra o jogo antes de viajar.")
            return
        if self.worker is not None and self.worker.is_alive():
            self.stop_event.set()
            self.root.after(100,lambda:self.start_trip(destination))
            return
        self.session.combat_probe.stop("Registro encerrado para iniciar viagem.")
        self.stop_event=threading.Event()
        engine=TravelWorker(self.session,self.stop_event,lambda event,data:self.events.put((event,data)),destination)
        self.worker=threading.Thread(target=engine.run,daemon=True)
        self.worker.start()

    def record_manual_collect(self):
        self.gg_stop.set()
        if self.gg_active():
            self.root.after(100,self.record_manual_collect)
            return
        self.npc_stop_event.set()
        if self.npc_active():
            self.root.after(100,self.record_manual_collect)
            return
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100,self.record_manual_collect)
            return
        try:
            self.session.arm_manual_probe()
            self.say("Coleta automática pausada. Clique manualmente em uma box no jogo e espere coletar.")
            self.manual_probe_status.set("Registro por 30 segundos. Depois clique em Copiar diagnóstico.")
        except ValueError as exc:
            self.say(str(exc))

    def export_client_integration(self):
        self.skylab_stop.set()
        self.gg_stop.set()
        if self.gg_active():
            self.root.after(100,self.export_client_integration)
            return
        self.npc_stop_event.set()
        if self.npc_active():
            self.root.after(100,self.export_client_integration)
            return
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100,self.export_client_integration)
            return
        if not self.session.ready.is_set():
            self.say("Abra o jogo na janela dedicada antes de exportar.")
            return
        filename=filedialog.asksaveasfilename(parent=self.root,title="Salvar integração do cliente",
            initialfile="AutoBox_integracao_cliente.json",defaultextension=".json",
            filetypes=[("Integração do cliente","*.json")])
        if not filename: return
        self.say("Lendo arquivos JavaScript do cliente na janela dedicada...")
        def export():
            try:
                data=self.session.request("client_sources",timeout=25)
                Path(filename).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                self.events.put(("status","Integração exportada: "+filename+". Anexe esse arquivo aqui no chat."))
            except Exception as exc:
                self.events.put(("status","Falha ao exportar integração: "+str(exc)))
        threading.Thread(target=export,daemon=True).start()

    def copy_collect_diagnostic(self):
        report=self.session.get_manual_probe_report()
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(report,ensure_ascii=False,indent=2))
        self.say("Diagnóstico copiado. Pode colar aqui no chat para validar a coleta.")

    def _update_world_panel(self):
        now=time.monotonic()
        if now-self.last_world_refresh<.5: return
        self.last_world_refresh=now
        data=self.session.get_world_snapshot() if self.session.ready.is_set() else {
            "fresh":False,"status":"Abra o Opera dedicado e entre no mapa."}
        report=self.session.combat_probe.report()
        checks=report.get("checks",{})
        progress=" | ".join(label+(": sim" if checks.get(key) else ": falta") for key,label in (
            ("npc_selected","NPC"),("attack_started","Ataque"),("attack_stopped","Parada"),("damage_observed","Dano")))
        self.combat_report_status.set(report["status"]+"\n"+progress)
        self.npc_table.delete(*self.npc_table.get_children())
        performance=getattr(self.npc_engine,"stats",{}) if self.npc_engine else {}
        if isinstance(performance,dict):
            self.performance_table.delete(*self.performance_table.get_children())
            for kind,row in sorted(performance.items()):
                self.performance_table.insert("","end",values=(kind,row["kills"],"%.1f s" % (row["seconds"]/max(1,row["kills"])),"%.1f s" % row["last"],row["ammo"]))
        if data.get("fresh"):
            import math
            origin=data["position"]
            npcs=sorted(data.get("npc_candidates",[]),
                        key=lambda n:math.hypot(n["x"]-origin[0],n["y"]-origin[1]))
            kinds=sorted({n.get("kind") or n.get("type") for n in npcs
                          if isinstance(n.get("kind") or n.get("type"),str)})
            self._sync_npc_choices(kinds or ("mordon",))
            for npc in npcs[:30]:
                self.npc_table.insert("","end",values=(npc.get("kind") or npc.get("type") or "NPC",
                    str(npc.get("hp","—"))+" / "+str(npc.get("maxHp","—")),
                    "%.0f" % math.hypot(npc["x"]-origin[0],npc["y"]-origin[1])))
            choices=sorted({data["map"],self.collect_map.get(),self.npc_map.get()} |
                           {g["to"] for g in data.get("gates",[]) if isinstance(g.get("to"),str)})
            choices=[v for v in choices if re.fullmatch(r"[0-9]{1,2}-[0-9]{1,2}",v)]
            for box in self.map_boxes: box.configure(values=choices)
        for key,var in self.world_vars.items():
            var.set(data.get("status","Aguardando dados.") if key=="status" else "—")
        self.death_label.set("Mortes nesta sessão: "+str(self.death_state["count"]))
        repair=data.get("repair") or {}
        names={"base":"Base","portal":"Portal","spot":"Local"}
        options=repair.get("options",[])
        self.repair_label.set("  |  ".join(names.get(o.get("id"),"?")+": "+str(o.get("cost","—"))+" U"+
            ("" if o.get("available") and o.get("affordable") else " (indisponível)") for o in options)
            if options else "Custos de renascimento aparecem quando a nave morrer.")
        earning_active=bool(data.get("fresh") and not data.get("dead") and
            ((self.running and not self.stop_event.is_set()) or
             (self.npc_active() and self.npc_state=="running" and not self.npc_stop_event.is_set())))
        if self.earnings_last is not None and self.earnings_active and earning_active:
            self.earnings_elapsed+=max(0,now-self.earnings_last)
        self.earnings_last=now
        self.earnings_active=earning_active
        self.earnings.observe(data,earning_active)
        account=data.get("account",{}) if data.get("fresh") else {}
        for key in ("uridium","credits","xp","honor","level","booty_keys"):
            value=data.get(key) if key=="booty_keys" and data.get("fresh") else account.get(key)
            self.account_vars[key].set(format(value,",.0f").replace(",",".") if type(value) in (int,float) else "—")
        self.data_planner.include_green=self.green.get()
        decision=self.data_planner.step(data,now)
        labels={"paused":"Aguardando", "recover":"Recuperação necessária", "search":"Procurar boxes",
                "approach":"Aproximar", "collect":"Verificar coleta", "confirmed":"Coleta observada",
                "unconfirmed":"Sem confirmação", "stalled":"Sem aproximação"}
        text=labels[decision["phase"]]+": "+decision.get("reason","")
        if decision.get("target_id"):
            text+="\nAlvo: "+decision["target_id"]
        if decision.get("distance") is not None:
            text+="  |  Distância do alvo: %.1f" % decision["distance"]
        if decision.get("eta") is not None:
            text+="  |  Tempo estimado: %.1f s" % decision["eta"]
        self.farm_plan.set(text)
        self.manual_probe_status.set(self.session.get_manual_probe_report()["status"])
        self._update_vitals(data)
        if hasattr(self,"cockpit"):
            self.cockpit.update(data)
        if not data.get("fresh"): return
        self.world_vars["map"].set(data["map"])
        self.world_vars["position"].set("X %.1f  /  Y %.1f" % data["position"])
        self.world_vars["hp"].set("%.1f%%" % data["hp_percent"] if data["hp_percent"] is not None else "Indisponível")
        self.world_vars["counts"].set("%s boxes  /  %s portais  /  %s NPCs" %
                                     (data["boxes"],data["portals"],data["npcs"]))
        nearest=data.get("nearest")
        self.world_vars["nearest"].set(nearest["id"] if nearest else "Nenhuma box disponível")
        self.world_vars["distance"].set("%.1f unidades do mapa" % nearest["distance"] if nearest else "—")
        self.world_vars["sequence"].set("%s  /  recebida há %.1f s" % (data["sequence"],data["age"]))

    def _update_vitals(self,data):
        import math
        for key in ("hp","shield"):
            value=data.get(key+"_percent") if data.get("fresh") else None
            known=type(value) in (int,float) and math.isfinite(value) and 0<=value<=100
            self.vitals_text[key].set(("%.1f%%" % value) if known else "Indisponível")
            self.vitals_bars[key]["value"]=value if known else 0
        if data.get("fresh"):
            position=data.get("position")
            suffix=(" | X %.0f · Y %.0f" % tuple(position)) if isinstance(position,(list,tuple)) and len(position)==2 else ""
            self.map_summary.set("Mapa "+str(data.get("map","—"))+" | Boxes próximas: "+str(data.get("boxes","—"))+suffix)
        else:
            self.map_summary.set("Mapa — | Boxes próximas —")

    def _set_running(self, value):
        now = time.monotonic()
        if value and not self.running:
            self.active_started = now
        elif not value and self.running:
            self.active_elapsed += max(0, now-self.active_started)
        self.running = bool(value)

    def set_compact(self, compact):
        compact=bool(compact)
        if compact:
            if not self.compact and self.root.winfo_width()>1:self.full_geometry=self.root.geometry()
            self.main_shell.pack_forget()
            self.cockpit.pack(fill="both",expand=True)
            self.root.minsize(650,560)
            self.root.geometry("760x560")
        else:
            self.cockpit.pack_forget()
            self.main_shell.pack(fill="both",expand=True)
            self.root.minsize(760,min(620,self.root.winfo_screenheight()-80))
            self.root.geometry(self.full_geometry)
        self.compact=compact
        self.cfg["compact_view"]=compact
        try:self._write_config()
        except OSError as exc:self.say("Não foi possível salvar o modo de janela: "+str(exc))

    def game_window(self, state):
        if not self.session.ready.is_set():
            self.say("Abra o jogo pela sessão dedicada antes de alterar a janela.");return
        def change():
            try:
                self.session.request("window_state",{"state":state},allowed=lambda:not self.closing)
                self.events.put(("status","Jogo minimizado. Uso em segundo plano experimental; acompanhe a leitura ao vivo." if state=="minimized" else "Janela do jogo restaurada."))
            except Exception as exc:
                self.events.put(("status","Não foi possível alterar a janela: "+str(exc)))
        threading.Thread(target=change,daemon=True).start()

    def _update_panel(self):
        self._update_world_panel()
        for key,value in (("attempts",self.attempts),("confirmed",self.confirmed),("failed",self.failed)):
            self.counter_vars[key].set(str(value))
        elapsed = self.active_elapsed
        if self.running:
            elapsed += max(0,time.monotonic()-self.active_started)
        self.account_vars["earned"].set(format(self.earnings.total,",.0f").replace(",","."))
        self.account_vars["last_hour"].set(format(self.earnings.last_hour(),",.0f").replace(",",".")+" U")
        rate=self.earnings.hourly(self.earnings_elapsed)
        self.account_vars["hourly"].set("Calculando (30 s de farm)…" if rate is None else format(rate,",.0f").replace(",",".") + " U/h")
        seconds = int(elapsed)
        self.active_time.set("Tempo em coleta: %02d:%02d:%02d" % (seconds//3600,seconds//60%60,seconds%60))
        self.session_label.set("Opera conectado" if self.session.ready.is_set() else "Opera desconectado")
        alive=self.worker is not None and self.worker.is_alive()
        if not alive and self.stop_event.is_set() and self.collect_state=="running": self.collect_state="stopped"
        collect_label={"running":"Executando","paused":"Pausado","stopped":"Parado"}[self.collect_state]
        if alive and self.stop_event.is_set(): collect_label="Encerrando"
        self.collect_summary.set(collect_label)
        self.running_label.set("Coleta — "+collect_label)
        active=self.npc_active()
        label={"running":"Farmando", "paused":"Pausado", "stopped":"Parado"}[self.npc_state]
        if active and self.npc_stop_event.is_set(): label="Encerrando ataque"
        kills=self.npc_engine.kills if self.npc_engine else 0
        self.npc_summary.set(label+" | NPCs derrotados: "+str(kills))
        if active: self.running_label.set("Kill NPC — "+label)


    def _bind_keys(self):
        def pressed(key):
            action = {keyboard.Key.f8:"start", keyboard.Key.f9:"pause", keyboard.Key.f10:"stop"}.get(key)
            if action:
                self.events.put(("command", action))
        self.listener = keyboard.Listener(on_press=pressed)
        self.listener.daemon = True
        self.listener.start()

    def say(self, text):
        self.status.set(text)
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S") + " — " + text + "\n")
        lines=int(self.log.index("end-1c").split(".")[0])
        if lines>21: self.log.delete("1.0",str(lines-20)+".0")
        self.log.see("end")
        self.log.configure(state="disabled")


    def save(self):
        try:
            for key in ("hp","radius","max_distance","seconds"):
                self.cfg.pop("pursuit_"+key,None)
            self.cfg["pursuit_enabled"]=self.pursuit_enabled.get()
            for key,var in self.buy_fields.items():
                value=int(var.get())
                if value<0 or value>1000000000 or ("quantity" in key and not 1<=value<=100000):
                    raise ValueError("Confira os limites de reposição de munições.")
                self.cfg["buy_"+key]=value
            self.cfg.update(buy_laser=self.buy_laser.get(),buy_missile=self.buy_missile.get())
            for key,var in (("collect_map",self.collect_map),("npc_map",self.npc_map)):
                value=var.get().strip()
                if value and not re.fullmatch(r"[0-9]{1,2}-[0-9]{1,2}",value):
                    raise ValueError("Mapa inválido. Use um código como 4-3 ou deixe vazio.")
                self.cfg[key]=value
            min_hp=int(self.npc_min_hp.get())
            if not 25<=min_hp<=75: raise ValueError("Limite de vida do teste: 25 a 75%.")
            selected_kinds=sorted(kind for kind,var in self.npc_kind_vars.items() if var.get())
            if not selected_kinds: raise ValueError("Marque pelo menos um tipo de NPC.")
            self.cfg["npc_kinds"]=selected_kinds
            if self.npc_ammo.get() not in ("lcb10","mcb25","mcb50","ucb100","sab50","rsb75") or self.npc_rocket.get() not in ("none","r310","plt2026","plt2021","plt3030"):
                raise ValueError("Selecione laser e míssil válidos.")
            self.cfg.update(npc_ammo=self.npc_ammo.get(),npc_rocket=self.npc_rocket.get())
            radius=int(self.npc_radius.get())
            if not 150<=radius<=800: raise ValueError("Distância do NPC: 150 a 800 unidades.")
            self.cfg.update(npc_kind=self.npc_kind.get(),npc_min_hp=min_hp,npc_radius=radius,npc_orbit=self.npc_orbit.get(),npc_repair=self.npc_repair.get(),npc_portal_fight=self.npc_portal_fight.get())
            deaths=int(self.max_deaths.get()); cost=int(self.max_cost.get())
            if not 1<=deaths<=100 or not 0<=cost<=100000:
                raise ValueError("Mortes: 1 a 100; custo: 0 a 100000.")
            self.cfg.update(respawn=self.respawn.get(),max_deaths=deaths,max_cost=cost)
            self.cfg["cloak"] = self.cloak_enabled.get()
            self.cfg["green"] = self.green.get()
            self.cfg["reconnect"] = self.reconnect.get()
            for key in ("collection_mode","threshold","full_map","map","ship","notice","minimap"):
                self.cfg.pop(key,None)
            self._write_config()
            return True
        except (ValueError, OSError) as exc:
            self.say("Nao foi possivel salvar: " + str(exc))
            return False

    def _write_config(self):
        temporary=CONFIG_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.cfg,indent=2),encoding="utf-8")
        os.replace(temporary,CONFIG_PATH)

    def choose_opera(self):
        if self.session.ready.is_set():
            self.say("Feche e reabra o aplicativo para trocar o executavel.")
            return
        selected = filedialog.askopenfilename(title="Selecione opera.exe ou launcher.exe do Opera GX",
                                              filetypes=[("Executavel", "*.exe")])
        if selected:
            self.cfg["opera_executable"] = selected
            self.save()
            self.say("Opera GX selecionado.")

    def open_browser(self):
        if self.opening or self.closing or self.session.ready.is_set():
            return
        executable = self.cfg.get("opera_executable") or find_opera_gx()
        if not executable or not Path(executable).is_file():
            self.say("Use Localizar executavel para selecionar seu Opera GX.")
            return
        self.opening = True
        self.say("Abrindo a sessao separada do Opera GX...")
        def open_session():
            try:
                self.session.start(executable)
                if not self.session.ready.wait(65):
                    raise RuntimeError(self.session.error or "Opera GX nao respondeu.")
                self.events.put(("status", self.session.warning or
                    "Sessao aberta. Entre no mapa e aguarde a leitura na aba Dados."))
            except Exception as exc:
                self.events.put(("status", str(exc)))
            finally:
                self.opening = False
        threading.Thread(target=open_session, daemon=True).start()


    def start(self):
        if self.gg_active():
            self.say("Pare os giros do Galaxy Gate antes de iniciar a coleta.");return
        if self.npc_active():
            self.say("Pause ou pare o farm na aba Kill NPC antes de iniciar a coleta.")
            return
        if self.closing:
            return
        if self.worker is not None and self.worker.is_alive():
            if self.stop_event.is_set():
                self.say("Coleta encerrando. Aguarde antes de iniciar novamente.")
            return
        if not self.session.ready.is_set():
            self.say("Abra a sessao dedicada primeiro.")
            return
        if not self.save():
            return
        snapshot=self.session.get_world_snapshot()
        if not snapshot.get("fresh"):
            self.say("Aguarde a leitura ao vivo na aba Dados antes de iniciar.")
            return
        if snapshot.get("hp_percent") is None or snapshot["hp_percent"]<=25 or snapshot.get("dead"):
            self.say("Recupere a nave antes de iniciar a coleta por dados.")
            return
        self.session.combat_probe.stop("Registro encerrado para iniciar coleta.")
        self.stop_event=threading.Event()
        self.earnings.observe(snapshot,False)
        engine=DataCollector(self.session,self.stop_event,lambda event,data:self.events.put((event,data)),
                             settings={"green":self.green.get(),"cloak":self.cloak_enabled.get(),"reconnect":self.reconnect.get(),"farm_map":self.cfg.get("collect_map",""),
                                 "respawn":{"Base":"base","Portal":"portal","Local":"spot"}.get(self.respawn.get()),
                                 "max_deaths":self.cfg["max_deaths"],"max_cost":self.cfg["max_cost"],
                                 "death_state":self.death_state})
        self.worker=threading.Thread(target=engine.run,daemon=True)
        self.worker.start()
        self.collect_state="running"
        self.cloak_status.set("Verificando camuflagem durante a coleta." if self.cloak_enabled.get() else "Camuflagem automática desativada.")
        self.say("Coleta por dados iniciada. Mantém o alvo até a coleta; F9 pausa.")
        return

    def pause(self):
        self.cloak_status.set("Camuflagem automática parada junto com a coleta.")
        self.collect_state="paused"
        self.stop_event.set()
        self.say("Pausado. F8 inicia uma nova busca.")

    def stop(self):
        self.cloak_status.set("Camuflagem automática parada junto com a coleta.")
        self.collect_state="stopped"
        self.stop_event.set()
        self.say("Parado.")







    def check_updates(self):
        self.say("Verificando atualizacoes deste bot...")
        def check():
            try:
                manifest=updater.check_for_update()
                if manifest:
                    self.events.put(("update",manifest))
                else:
                    self.events.put(("status","Este bot ja esta atualizado."))
            except Exception as exc:
                self.events.put(("status","Falha ao verificar atualizacao: "+str(exc)))
        threading.Thread(target=check,daemon=True).start()

    def _download(self, manifest):
        self.skylab_stop.set()
        self.gg_stop.set()
        self.stop_event.set()
        self.npc_stop_event.set()
        self.say("Baixando e verificando a atualizacao...")
        def download():
            try:
                self.events.put(("update_ready",updater.stage_update(manifest)))
            except Exception as exc:
                self.events.put(("status","Atualizacao cancelada: "+str(exc)))
        threading.Thread(target=download,daemon=True).start()

    def _drain(self):
        if self.closing:
            return
        while True:
            try:
                event,data=self.events.get_nowait()
            except queue.Empty:
                break
            if event=="command":
                {"start":self.start,"pause":self.pause,"stop":self.stop}[data]()
            elif event=="cloak_status":
                self.cloak_status.set(data)
                self.say(data)
            elif event=="skylab_status":
                self.skylab_status.set(data)
                self.say(data)
            elif event=="skylab_rows":
                self.update_skylab_rows(data)
            elif event=="gg_status":
                self.gg_status.set(data)
                self.say(data)
            elif event=="npc_event":
                generation,kind,value=data
                if generation!=self.npc_generation: continue
                if kind=="confirmed":self.confirmed+=1
                elif kind=="failed":self.failed+=1
                elif kind=="attempt":self.attempts+=1
                elif kind=="cloak_status":self.cloak_status.set(value)
                elif kind=="npc_report":
                    self.last_npc_report=value
                    if self.npc_state=="running": self.combat_status.set(value["status"])
                elif kind=="status":
                    if self.npc_state=="running": self.combat_status.set(value)
                    self.say(value)
                elif kind=="running" and not value and self.npc_state=="running":
                    self.npc_state="stopped"
            elif event=="npc_report":
                self.last_npc_report=data
                self.combat_status.set(data["status"])
            elif event=="running":
                self._set_running(data)
            elif event=="status":
                self.say(data)
            elif event=="attempt":
                self.attempts+=1
            elif event=="confirmed":
                self.confirmed+=1
                self.say("Box coletada e confirmada.")
            elif event=="failed":
                self.failed+=1
            elif event=="update":
                if messagebox.askyesno("Atualizacao", "Instalar a versao "+data["version"]+" deste bot?"):
                    self._download(data)
            elif event=="update_ready":
                self.close(lambda: updater.start_update(data,Path(__file__).resolve().parent))
                return
        self.stats.set("Tentativas: %s | Confirmadas: %s | Sem progresso: %s" %
                       (self.attempts,self.confirmed,self.failed))
        self._update_panel()
        self.root.after(100,self._drain)

    def close(self, after=None):
        self.skylab_stop.set()
        if self.closing:
            return
        self.closing=True
        self.gg_stop.set()
        self.stop_event.set()
        self.npc_stop_event.set()
        self.listener.stop()
        self.say("Encerrando a sessao dedicada...")
        done=threading.Event()
        def shutdown():
            try:
                if self.npc_worker is not None:
                    self.npc_worker.join(timeout=5)
                self.session.close()
            finally:
                done.set()
        threading.Thread(target=shutdown,daemon=True).start()
        def finish():
            if not done.is_set():
                self.root.after(100,finish)
                return
            try:
                if after:
                    after()
            finally:
                self.root.destroy()
        finish()

if __name__=="__main__":
    root=tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    AutoBoxSemMouse(root)
    root.mainloop()
