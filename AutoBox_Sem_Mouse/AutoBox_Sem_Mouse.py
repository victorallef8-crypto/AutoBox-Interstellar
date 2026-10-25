"""AutoBox Sem Mouse — aplicativo independente, exclusivo de coleta no Interstellar."""
from __future__ import annotations
import ctypes
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from pynput import keyboard
from browser_session import BrowserSession, find_opera_gx
from controller import DataFarmPlanner, DataCollector, SessionEarnings
import updater

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
        self.opening = False
        self.closing = False
        self.attempts = self.confirmed = self.failed = 0
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
        self.green = tk.BooleanVar(value=self.cfg.get("green",False))
        self.reconnect = tk.BooleanVar(value=self.cfg.get("reconnect",True))
        self.respawn = tk.StringVar(value=self.cfg.get("respawn","Desativado"))
        self.max_deaths = tk.StringVar(value=str(self.cfg.get("max_deaths",3)))
        self.max_cost = tk.StringVar(value=str(self.cfg.get("max_cost",0)))
        self.death_state = {"ids":set(),"count":0}
        self.death_label = tk.StringVar(value="Mortes nesta sessão: 0")
        self.repair_label = tk.StringVar(value="Custos de renascimento aparecem quando a nave morrer.")
        self.earnings = SessionEarnings()
        self.account_vars = {key:tk.StringVar(value="—") for key in ("uridium","credits","xp","honor","level","earned","hourly","booty_keys")}
        self.data_planner = DataFarmPlanner(arrival_radius=180)
        self.farm_plan = tk.StringVar(value="Aguardando dados para planejar.")
        self.manual_probe_status = tk.StringVar(value="Registre uma coleta manual para validar o comando.")
        root.title("AutoBox Sem Mouse — beta " + updater.CURRENT_VERSION)
        root.geometry("940x" + str(min(820, root.winfo_screenheight()-90)))
        root.minsize(760,min(620,root.winfo_screenheight()-80))
        self._draw()
        self._draw_world_page()
        self._bind_keys()
        root.after(100, self._drain)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _theme(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#111827", foreground="#e5e7eb",
                        font=("Segoe UI", 10), fieldbackground="#1f2937")
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb")
        style.configure("Muted.TLabel", foreground="#94a3b8")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#f8fafc")
        style.configure("Heading.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Card.TFrame", background="#1e293b")
        style.configure("Card.TLabel", background="#1e293b", foreground="#94a3b8")
        style.configure("Count.TLabel", background="#1e293b", foreground="#67e8f9",
                        font=("Segoe UI", 20, "bold"))
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
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0,14))
        title = ttk.Frame(header); title.pack(side="left")
        ttk.Label(title, text="AutoBox Interstellar", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="Sem mouse  /  beta "+updater.CURRENT_VERSION,
                  style="Muted.TLabel").pack(anchor="w")
        connection = ttk.Frame(header); connection.pack(side="right")
        ttk.Label(connection, textvariable=self.session_label, style="Heading.TLabel").pack(anchor="e")
        ttk.Label(connection, textvariable=self.running_label, style="Muted.TLabel").pack(anchor="e")

        # Controles sempre visiveis, inclusive ao consultar outra aba.
        controls = ttk.LabelFrame(shell, text="Coleta de boxes", padding=10)
        controls.pack(side="bottom", fill="x", pady=(12,0))
        buttons = ttk.Frame(controls); buttons.pack(fill="x")
        for label, command, style in (("Iniciar coleta (F8)",self.start,"Start.TButton"),
                                       ("Pausar (F9)",self.pause,"TButton"),
                                       ("Parar (F10)",self.stop,"TButton")):
            ttk.Button(buttons,text=label,command=command,style=style).pack(
                side="left",fill="x",expand=True,padx=3)
        status_message=ttk.Label(controls,textvariable=self.status,wraplength=900)
        status_message.pack(anchor="w",pady=(8,3))
        controls.bind("<Configure>",lambda event:status_message.configure(wraplength=max(100,event.width-24)))
        ttk.Label(controls,textvariable=self.stats,style="Muted.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(shell)
        self.notebook.pack(fill="both", expand=True)
        self.pages = {}
        for key, title in (("dashboard","Painel"),("data","Dados e coleta"),("advanced","Avançado")):
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
        ttk.Button(dashboard,text="Iniciar jogo",command=self.open_browser,style="Start.TButton").pack(anchor="w",pady=(0,10))
        ttk.Label(dashboard,text="Modo disponível: coleta de boxes  •  alvo mais próximo primeiro",
                  style="Muted.TLabel").pack(anchor="w",pady=(3,12))
        cards = ttk.Frame(dashboard); cards.pack(fill="x")
        for column, (key,label) in enumerate((("attempts","Tentativas"),("confirmed","Confirmadas"),
                                             ("failed","Sem progresso"))):
            cards.columnconfigure(column,weight=1)
            card=ttk.Frame(cards,padding=14,style="Card.TFrame")
            card.grid(row=0,column=column,sticky="ew",padx=(0,8) if column<2 else 0)
            ttk.Label(card,text=label,style="Card.TLabel").pack(anchor="w")
            ttk.Label(card,textvariable=self.counter_vars[key],style="Count.TLabel").pack(anchor="w")
        balances=ttk.LabelFrame(dashboard,text="Conta e rendimento",padding=10)
        balances.pack(fill="x",pady=(10,0))
        for index,(key,label) in enumerate((("uridium","Uridium"),("credits","Créditos"),("xp","XP"),
                ("honor","Honra"),("level","Nível"),("booty_keys","Chaves verdes"),
                ("earned","Uridium das boxes nesta sessão"),("hourly","Uridium por hora"))):
            row,col=divmod(index,2)
            ttk.Label(balances,text=label,style="Muted.TLabel").grid(row=row,column=col*2,sticky="w",padx=6,pady=4)
            ttk.Label(balances,textvariable=self.account_vars[key]).grid(row=row,column=col*2+1,sticky="e",padx=10)
        balances.columnconfigure(1,weight=1)
        balances.columnconfigure(3,weight=1)
        ttk.Label(dashboard,textvariable=self.active_time,style="Muted.TLabel").pack(anchor="w",pady=12)
        shortcuts=ttk.Frame(dashboard); shortcuts.pack(fill="x",pady=(0,12))
        ttk.Button(shortcuts,text="Configurar coleta",command=lambda:self.notebook.select(self.pages["data"])).pack(side="left",padx=(0,8))
        ttk.Button(shortcuts,text="Verificar atualizações deste bot",command=self.check_updates).pack(side="left")
        ttk.Label(dashboard,text="Histórico da sessão",style="Heading.TLabel").pack(anchor="w",pady=(4,8))
        self.log=tk.Text(dashboard,height=4,state="disabled",wrap="word",background="#0b1220",
                         foreground="#cbd5e1",insertbackground="white",relief="flat",padx=10,pady=10,
                         font=("Consolas",10))
        log_scroll=ttk.Scrollbar(dashboard,orient="vertical",command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right",fill="y")
        self.log.pack(fill="both",expand=True)

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


    def record_manual_collect(self):
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
        for key,var in self.world_vars.items():
            var.set(data.get("status","Aguardando dados.") if key=="status" else "—")
        self.death_label.set("Mortes nesta sessão: "+str(self.death_state["count"]))
        repair=data.get("repair") or {}
        names={"base":"Base","portal":"Portal","spot":"Local"}
        options=repair.get("options",[])
        self.repair_label.set("  |  ".join(names.get(o.get("id"),"?")+": "+str(o.get("cost","—"))+" U"+
            ("" if o.get("available") and o.get("affordable") else " (indisponível)") for o in options)
            if options else "Custos de renascimento aparecem quando a nave morrer.")
        self.earnings.observe(data, self.running and not self.stop_event.is_set())
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

    def _set_running(self, value):
        now = time.monotonic()
        if value and not self.running:
            self.active_started = now
        elif not value and self.running:
            self.active_elapsed += max(0, now-self.active_started)
        self.running = bool(value)

    def _update_panel(self):
        self._update_world_panel()
        for key,value in (("attempts",self.attempts),("confirmed",self.confirmed),("failed",self.failed)):
            self.counter_vars[key].set(str(value))
        elapsed = self.active_elapsed
        if self.running:
            elapsed += max(0,time.monotonic()-self.active_started)
        self.account_vars["earned"].set(format(self.earnings.total,",.0f").replace(",","."))
        rate=self.earnings.hourly(elapsed)
        self.account_vars["hourly"].set("Calculando…" if rate is None else format(rate,",.0f").replace(",",".") + " U/h")
        seconds = int(elapsed)
        self.active_time.set("Tempo em coleta: %02d:%02d:%02d" % (seconds//3600,seconds//60%60,seconds%60))
        self.session_label.set("Opera conectado" if self.session.ready.is_set() else "Opera desconectado")
        self.running_label.set("Coletando boxes" if self.running and not self.stop_event.is_set() else "Coleta pausada")

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
        if int(self.log.index("end-1c").split(".")[0]) > 70:
            self.log.delete("1.0", "20.0")
        self.log.see("end")
        self.log.configure(state="disabled")


    def save(self):
        try:
            deaths=int(self.max_deaths.get()); cost=int(self.max_cost.get())
            if not 1<=deaths<=100 or not 0<=cost<=100000:
                raise ValueError("Mortes: 1 a 100; custo: 0 a 100000.")
            self.cfg.update(respawn=self.respawn.get(),max_deaths=deaths,max_cost=cost)
            self.cfg["green"] = self.green.get()
            self.cfg["reconnect"] = self.reconnect.get()
            for key in ("collection_mode","threshold","full_map","map","ship","notice","minimap"):
                self.cfg.pop(key,None)
            temporary = CONFIG_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
            os.replace(temporary, CONFIG_PATH)
            return True
        except (ValueError, OSError) as exc:
            self.say("Nao foi possivel salvar: " + str(exc))
            return False

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
        if self.closing:
            return
        if self.worker is not None and self.worker.is_alive():
            if self.stop_event.is_set():
                self.root.after(100, self.start)
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
        self.stop_event=threading.Event()
        self.earnings.observe(snapshot,False)
        engine=DataCollector(self.session,self.stop_event,lambda event,data:self.events.put((event,data)),
                             settings={"green":self.green.get(),"reconnect":self.reconnect.get(),
                                 "respawn":{"Base":"base","Portal":"portal","Local":"spot"}.get(self.respawn.get()),
                                 "max_deaths":self.cfg["max_deaths"],"max_cost":self.cfg["max_cost"],
                                 "death_state":self.death_state})
        self.worker=threading.Thread(target=engine.run,daemon=True)
        self.worker.start()
        self.say("Coleta por dados iniciada. Mantém o alvo até a coleta; F9 pausa.")
        return

    def pause(self):
        self.stop_event.set()
        self.say("Pausado. F8 inicia uma nova busca.")

    def stop(self):
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
        self.stop_event.set()
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
            elif event=="running":
                self._set_running(data)
            elif event=="status":
                self.say(data)
            elif event=="attempt":
                self.attempts+=1
            elif event=="confirmed":
                self.confirmed+=1
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
        if self.closing:
            return
        self.closing=True
        self.stop_event.set()
        self.listener.stop()
        self.say("Encerrando a sessao dedicada...")
        done=threading.Event()
        def shutdown():
            try:
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
