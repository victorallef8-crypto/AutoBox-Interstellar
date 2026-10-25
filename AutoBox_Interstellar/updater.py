"""Atualizador local e verificavel do AutoBox Interstellar.

O aplicativo nunca executa comandos recebidos da rede. Baixa um ZIP do
repositorio publico, confere SHA-256 e substitui somente arquivos conhecidos.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


CURRENT_VERSION = "3.1"
OWNER_REPO = "victorallef8-crypto/AutoBox-Interstellar"
REPO_RAW_PREFIX = (
    "https://raw.githubusercontent.com/"
    "victorallef8-crypto/AutoBox-Interstellar/main/"
)
MANIFEST_URL = REPO_RAW_PREFIX + "update_manifest.json"
PACKAGE_FILES = (
    "AutoBox_Interstellar.py",
    "updater.py",
    "INSTALAR_E_ABRIR.bat",
    "LEIA-ME.txt",
    "requirements.txt",
)
ZIP_PREFIX = "AutoBox_Interstellar/"
MAX_ZIP_BYTES = 10_000_000
MAX_UNCOMPRESSED_BYTES = 30_000_000


def version_tuple(text: str) -> tuple[int, ...]:
    if not isinstance(text, str) or not text or len(text) > 30:
        raise ValueError("Versao invalida")
    parts = text.split(".")
    if not 1 <= len(parts) <= 4 or not all(part.isdigit() for part in parts):
        raise ValueError("Versao invalida")
    return tuple(int(part) for part in parts)


def _verified_repo_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com" or
            parsed.username or parsed.password or parsed.port or
            parsed.query or parsed.fragment or
            url not in (MANIFEST_URL, REPO_RAW_PREFIX + "AutoBox_Interstellar.zip")):
        raise ValueError("Endereco de atualizacao nao autorizado")
    return url


def _read_url(url: str, max_bytes: int) -> bytes:
    class BlockRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("Redirecionamento nao autorizado")

    req = urllib.request.Request(
        _verified_repo_url(url),
        headers={"User-Agent": "AutoBox-Interstellar-Updater/3.1"},
    )
    with urllib.request.build_opener(BlockRedirects).open(req, timeout=15) as response:
        final_url = response.geturl()
        _verified_repo_url(final_url)  # nao segue redirects para outros sites
        output = response.read(max_bytes + 1)
    if len(output) > max_bytes:
        raise ValueError("Arquivo de atualizacao maior que o permitido")
    return output


def check_for_update() -> dict | None:
    content = _read_url(MANIFEST_URL, 65_536)
    manifest = json.loads(content.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Manifesto de atualizacao invalido")
    latest = manifest.get("version")
    if version_tuple(latest) <= version_tuple(CURRENT_VERSION):
        return None
    package_url = _verified_repo_url(manifest.get("zip_url", ""))
    expected_sha = manifest.get("sha256", "")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ValueError("Assinatura SHA-256 ausente")
    int(expected_sha, 16)
    return {"version": latest, "zip_url": package_url,
            "sha256": expected_sha.lower()}


def stage_update(manifest: dict) -> Path:
    package = _read_url(manifest["zip_url"], MAX_ZIP_BYTES)
    digest = hashlib.sha256(package).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("Verificacao de integridade falhou; instalacao cancelada")
    staged = Path(tempfile.mkdtemp(prefix="autobox_update_"))
    try:
        with tempfile.TemporaryFile() as memory_file:
            memory_file.write(package)
            memory_file.seek(0)
            with zipfile.ZipFile(memory_file) as archive:
                names = set(archive.namelist())
                wanted = {ZIP_PREFIX + f for f in PACKAGE_FILES}
                if not wanted.issubset(names):
                    raise ValueError("Pacote incompleto: faltam arquivos do AutoBox")
                if any(name not in wanted for name in names):
                    raise ValueError("Pacote com arquivos inesperados")
                if sum(entry.file_size for entry in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Pacote descompactado muito grande")
                for filename in PACKAGE_FILES:
                    data = archive.read(ZIP_PREFIX + filename)
                    (staged / filename).write_bytes(data)
        return staged
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise


def start_update(staged: Path, app_dir: Path):
    """Lanca aplicador independente; app principal precisa fechar em seguida."""
    if os.name != "nt":
        raise RuntimeError("Instalacao automatica disponivel somente no Windows")
    helper = app_dir / "updater.py"
    subprocess.Popen(
        [sys.executable, str(helper), "--apply", str(staged), str(app_dir),
         str(os.getpid())],
        cwd=str(app_dir),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _wait_for_pid(pid: int):
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel.WaitForSingleObject(handle, 45_000)
            kernel.CloseHandle(handle)
        else:
            time.sleep(1.5)
    else:
        time.sleep(1.5)


def apply_staged_update(staged: Path, app_dir: Path, parent_pid: int):
    _wait_for_pid(parent_pid)
    for filename in PACKAGE_FILES:
        source = staged / filename
        destination = app_dir / filename
        if not source.is_file() or destination.parent != app_dir:
            raise ValueError("Atualizacao com arquivo invalido")
        temporary = app_dir / (filename + ".new")
        for retry in range(12):
            try:
                shutil.copyfile(source, temporary)
                os.replace(temporary, destination)
                break
            except (PermissionError, OSError):
                if retry == 11:
                    raise
                time.sleep(.5)
    shutil.rmtree(staged, ignore_errors=True)
    subprocess.Popen([sys.executable, str(app_dir / "AutoBox_Interstellar.py")],
                     cwd=str(app_dir),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


if __name__ == "__main__" and len(sys.argv) == 5 and sys.argv[1] == "--apply":
    try:
        apply_staged_update(Path(sys.argv[2]).resolve(),
                            Path(sys.argv[3]).resolve(), int(sys.argv[4]))
    except Exception as exc:
        print("Falha na atualizacao do AutoBox:", exc)
        input("Pressione Enter para fechar...")
