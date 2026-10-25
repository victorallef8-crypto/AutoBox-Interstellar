"""Atualizador exclusivo do aplicativo compilado; não instala código fonte."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from updater import CURRENT_VERSION, version_tuple

REPO='victorallef8-crypto/AutoBox-Interstellar'
MANIFEST_URL=f'https://raw.githubusercontent.com/{REPO}/main/AutoBox_Usuario/update_manifest.json'
EXE='AutoBox.exe'
FILES={EXE,'COMO_USAR.txt'}

def verified_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.fragment or p.port:
        raise ValueError('Endereço de atualização inválido.')
    if url==MANIFEST_URL: return url
    prefix=f'https://github.com/{REPO}/releases/download/usuario-'
    if not url.startswith(prefix) or p.query or not re.fullmatch(r'[0-9.]+/AutoBox_Usuario.zip',url[len(prefix):]):
        raise ValueError('Pacote fora do canal oficial de usuários.')
    return url

def download(url,limit):
    verified_url(url)
    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            p=urllib.parse.urlsplit(newurl)
            if p.scheme!='https' or p.hostname!='release-assets.githubusercontent.com' or p.username or p.password:
                raise ValueError('Redirecionamento não autorizado.')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    request=urllib.request.Request(url,headers={'User-Agent':'AutoBox-Usuario','Cache-Control':'no-cache'})
    with urllib.request.build_opener(Redirects).open(request,timeout=90) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError('Pacote excedeu o limite permitido.')
    return data

def check_for_update():
    manifest=json.loads(download(MANIFEST_URL,65536).decode('utf-8'))
    if version_tuple(manifest['version'])<=version_tuple(CURRENT_VERSION): return None
    verified_url(manifest['zip_url'])
    if not re.fullmatch('[a-fA-F0-9]{64}',manifest.get('sha256','')): raise ValueError('Hash inválido.')
    return manifest

def stage_update(manifest):
    data=download(manifest['zip_url'],180_000_000)
    if hashlib.sha256(data).hexdigest()!=manifest['sha256'].lower(): raise ValueError('Integridade do pacote inválida.')
    import io
    stage=Path(tempfile.mkdtemp(prefix='autobox_usuario_'))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names=archive.namelist()
            if len(names)!=len(FILES) or set(names)!=FILES or sum(x.file_size for x in archive.infolist())>250_000_000:
                raise ValueError('Conteúdo do pacote inválido.')
            for name in FILES: (stage/name).write_bytes(archive.read(name))
        if not (stage/EXE).read_bytes().startswith(b'MZ'): raise ValueError('Aplicativo Windows inválido.')
        return stage
    except Exception:
        shutil.rmtree(stage)
        raise

def start_update(staged,app_dir):
    # Copia o aplicador antes de fechar para liberar o executável original.
    helper=Path(staged)/'AplicarAtualizacao.exe'
    shutil.copy2(sys.executable,helper)
    target=Path(sys.executable).resolve()
    if target.name!=EXE: raise ValueError('Mantenha o nome AutoBox.exe para atualizar.')
    env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1')
    subprocess.Popen([str(helper),'--apply',str(staged),str(target),str(os.getpid())],env=env,
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

def apply_update(staged,target,pid):
    import ctypes
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle,60000)!=0: raise RuntimeError('Feche o AutoBox para atualizar.')
        finally: kernel.CloseHandle(handle)
    if target.name!=EXE or not (staged/EXE).is_file(): raise ValueError('Destino de atualização inválido.')
    temporary=target.with_suffix('.new')
    backup=target.with_suffix('.bak')
    for attempt in range(40):
        try:
            shutil.copy2(staged/EXE,temporary)
            shutil.copy2(target,backup)
            os.replace(temporary,target)
            break
        except OSError:
            if attempt==39: raise
            time.sleep(.5)
    env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1')
    subprocess.Popen([str(target)],cwd=target.parent,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    # O helper em execução fica apenas na pasta temporária; nenhum perfil é apagado.
