from pathlib import Path
import os
import queue
import threading
import struct
import math

GAME_URL = "https://interstellar-verse.com/play/#play"

def find_opera_gx():
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMFILES"),
                 os.environ.get("PROGRAMFILES(X86)")):
        if not base:
            continue
        base = Path(base)
        for folder in (base / "Programs" / "Opera GX", base / "Opera GX"):
            for name in ("opera.exe", "launcher.exe"):
                executable = folder / name
                if executable.is_file():
                    return str(executable)
    return ""

class BrowserSession:
    """Dono unico do navegador. Captura e cliques nao passam pelo mouse do Windows."""
    def __init__(self, folder, viewport, factory=None):
        self.folder = Path(folder)
        self.viewport = dict(viewport)
        self.factory = factory
        self.jobs = queue.Queue()
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.closed.set()
        self.error = None
        self.warning = None
        self.thread = None
        self.capture_geometry = None
        self.capture_page = None
        self.last_click = None

    def start(self, executable):
        if self.thread is not None and self.thread.is_alive():
            return
        self.error = None
        self.warning = None
        self.capture_geometry = None
        self.capture_page = None
        self.last_click = None
        self.ready.clear()
        self.closed.clear()
        self.thread = threading.Thread(target=self._run, args=(executable,), daemon=True)
        self.thread.start()

    def request(self, operation, payload=None, allowed=None, timeout=8):
        if not self.ready.is_set() and operation != "close":
            raise RuntimeError(self.error or "Abra primeiro a sessao dedicada do Opera GX.")
        reply = queue.Queue(maxsize=1)
        cancelled = threading.Event()
        self.jobs.put((operation, payload, allowed, reply, cancelled))
        try:
            ok, result = reply.get(timeout=timeout)
        except queue.Empty:
            cancelled.set()
            raise RuntimeError("A janela do jogo demorou a responder. Coleta interrompida.")
        if not ok:
            raise RuntimeError(result)
        return result

    def close(self):
        if self.thread is None or not self.thread.is_alive():
            return
        try:
            self.request("close", timeout=8)
        finally:
            self.thread.join(timeout=3)

    @staticmethod
    def _game_page(context):
        pages = [page for page in context.pages if not page.is_closed()
                 and page.url.split("#")[0].split("?")[0].rstrip("/") ==
                 GAME_URL.split("#")[0].rstrip("/")]
        if not pages:
            raise RuntimeError("Abra a pagina de jogo do Interstellar na sessao dedicada.")
        return pages[-1]


    @staticmethod
    def _measure(page):
        # Somente medidas do navegador; nao le estado interno do jogo.
        value = page.evaluate("""() => ({
            width: window.innerWidth, height: window.innerHeight,
            dpr: window.devicePixelRatio,
            offset_x: window.visualViewport ? window.visualViewport.offsetLeft : 0,
            offset_y: window.visualViewport ? window.visualViewport.offsetTop : 0,
            scale: window.visualViewport ? window.visualViewport.scale : 1
        })""")
        keys = ("width", "height", "dpr", "offset_x", "offset_y", "scale")
        if not isinstance(value, dict) or any(
            not isinstance(value.get(k), (float, int)) or not math.isfinite(value[k]) for k in keys
        ) or min(value["width"], value["height"], value["dpr"]) <= 0:
            raise ValueError("Medidas da pagina indisponiveis. Coleta interrompida.")
        if abs(value["scale"] - 1) > .001 or abs(value["offset_x"]) > .01 or abs(value["offset_y"]) > .01:
            raise ValueError("Zoom por gesto nao suportado. Use o zoom normal do Opera e calibre novamente.")
        return value

    def _capture(self, page):
        self.capture_geometry = None
        self.capture_page = None
        before = self._measure(page)
        data = page.screenshot(type="png", timeout=5000)
        after = self._measure(page)
        if before != after:
            raise ValueError("Zoom ou tamanho mudou durante a captura. Calibre novamente.")
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
            raise ValueError("Captura PNG invalida.")
        width, height = struct.unpack(">II", data[16:24])
        if width <= 0 or height <= 0:
            raise ValueError("Captura sem tamanho valido.")
        self.capture_geometry = dict(after, image_width=width, image_height=height)
        self.capture_page = page
        return data

    def _click(self, page, point, allowed):
        geometry = self.capture_geometry
        if geometry is None or self.capture_page is not page:
            raise ValueError("Capture a imagem dessa pagina antes de clicar.")
        current = self._measure(page)
        if any(current[k] != geometry[k] for k in current):
            self.capture_geometry = None
            raise ValueError("Zoom ou tamanho mudou apos a captura. Pause e calibre novamente.")
        x, y = point
        if (not math.isfinite(x) or not math.isfinite(y) or
                not (0 <= x < geometry["image_width"] and 0 <= y < geometry["image_height"])):
            raise ValueError("Clique fora da imagem do jogo.")
        # Captura em pixels da imagem; Playwright recebe pixels CSS do viewport.
        # No zoom 33%, uma imagem de 1280 pode representar cerca de 3840 pixels CSS.
        css_x = x * geometry["width"] / geometry["image_width"]
        css_y = y * geometry["height"] / geometry["image_height"]
        if allowed is not None and not allowed():
            return False
        page.mouse.click(css_x, css_y, button="left", delay=40)
        self.last_click = {"image": (x,y), "css": (css_x,css_y),
                           "image_size": (geometry["image_width"],geometry["image_height"]),
                           "css_size": (geometry["width"],geometry["height"])}
        return True

    def _run(self, executable):
        context = None
        try:
            if self.factory is None:
                from playwright.sync_api import sync_playwright
                factory = sync_playwright
            else:
                factory = self.factory
            self.folder.mkdir(parents=True, exist_ok=True)
            with factory() as driver:
                context = driver.chromium.launch_persistent_context(
                    user_data_dir=str(self.folder), executable_path=executable,
                    headless=False, chromium_sandbox=True, viewport=self.viewport, device_scale_factor=1,
                    accept_downloads=False)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    self.warning = "Confira a conexao e abra o jogo na janela dedicada."
                self.ready.set()
                while True:
                    try:
                        operation, payload, allowed, reply, cancelled = self.jobs.get(timeout=.1)
                    except queue.Empty:
                        if not context.pages:
                            break
                        try:
                            context.pages[0].wait_for_timeout(30)
                        except Exception:
                            break
                        continue
                    if cancelled.is_set():
                        reply.put((False, "Comando expirado e cancelado."))
                        continue
                    if operation == "close":
                        context.close()
                        context = None
                        reply.put((True, None))
                        break
                    try:
                        page = self._game_page(context)
                        # Recusa cliques enfileirados se F9/F10 ja interrompeu o bot.
                        if allowed is not None and not allowed():
                            reply.put((True, False))
                            continue
                        if operation == "screenshot":
                            result = self._capture(page)
                        elif operation == "click":
                            result = self._click(page, payload, allowed)
                        else:
                            raise ValueError("Comando de navegador desconhecido.")
                        reply.put((True, result))
                    except Exception as exc:
                        reply.put((False, str(exc)))
        except Exception as exc:
            self.error = "Nao foi possivel abrir o Opera GX dedicado: " + str(exc)
        finally:
            self.ready.clear()
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self.closed.set()
