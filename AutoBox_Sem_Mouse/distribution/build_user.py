"""Gera pacote de usuário sem perfis, credenciais ou arquivos-fonte soltos."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
APP=ROOT.parent
sys.path.insert(0,str(APP))
import updater
OUT=Path(os.environ.get('AUTOBOX_DIST',str(APP/'dist_user'))).resolve()
OUT.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
    '--name','AutoBox','--distpath',str(OUT),'--workpath',str(OUT/'build'),
    '--specpath',str(OUT/'build'),'--paths',str(APP),
    '--collect-data','certifi','--collect-all','playwright','--hidden-import','pynput.keyboard._win32',
    '--hidden-import','pynput.mouse._win32',str(APP/'user_entry.py')],check=True)
exe=OUT/'AutoBox.exe'
probe=OUT/'self-test.json'
process=subprocess.Popen([str(exe),'--self-test',str(probe)],env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1'))
if process.wait(timeout=120)!=0 or not probe.is_file() or not json.loads(probe.read_text())['ok']:
    raise RuntimeError('Executável não passou no teste de inicialização.')
with zipfile.ZipFile(OUT/'AutoBox_Usuario.zip','w',zipfile.ZIP_DEFLATED) as z:
    z.write(exe,'AutoBox.exe')
    z.write(ROOT/'COMO_USAR.txt','COMO_USAR.txt')
manifest={'version':updater.CURRENT_VERSION,
          'zip_url':f'https://github.com/{updater.OWNER_REPO}/releases/download/usuario-{updater.CURRENT_VERSION}/AutoBox_Usuario.zip',
          'sha256':hashlib.sha256((OUT/'AutoBox_Usuario.zip').read_bytes()).hexdigest()}
(OUT/'update_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Distribuição de usuário verificada:',manifest['version'])
