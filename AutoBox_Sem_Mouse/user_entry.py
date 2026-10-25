import os
import sys
from pathlib import Path
import user_updater

if __name__=='__main__':
    if len(sys.argv)==5 and sys.argv[1]=='--apply':
        try:
            user_updater.apply_update(Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve(),int(sys.argv[4]))
        except Exception as exc:
            import tkinter.messagebox
            tkinter.messagebox.showerror('Atualização não concluída',str(exc))
        raise SystemExit
    sys.modules['updater']=user_updater
    import AutoBox_Sem_Mouse as app
    app.APP_DIR=Path(os.environ.get('APPDATA',str(Path.home())))/'AutoBoxUsuario'
    app.CONFIG_PATH=app.APP_DIR/'config.json'
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        import json
        import ssl
        context=user_updater.tls_context()
        assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        assert context.cert_store_stats()['x509_ca']>0
        # Exercita o mesmo HTTPS do atualizador e o redirecionamento dos releases.
        manifest=json.loads(user_updater.download(user_updater.MANIFEST_URL,65536))
        stage=user_updater.stage_update(manifest)
        import shutil
        shutil.rmtree(stage)
        from playwright.sync_api import sync_playwright
        root=app.tk.Tk();root.withdraw()
        app.AutoBoxSemMouse._theme(type('ThemeTest',(),{'root':root})())
        with sync_playwright() as pw:
            assert pw.chromium.executable_path
        root.destroy()
        Path(sys.argv[2]).write_text(json.dumps({'ok':True,'version':user_updater.CURRENT_VERSION,'frozen':bool(getattr(sys,'frozen',False))}),encoding='utf-8')
        raise SystemExit
    root=app.tk.Tk()
    app.AutoBoxSemMouse(root)
    root.title('AutoBox Interstellar — Usuário '+user_updater.CURRENT_VERSION)
    root.mainloop()
