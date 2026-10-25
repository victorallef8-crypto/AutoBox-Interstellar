import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import user_updater as u

class UserUpdaterTests(unittest.TestCase):
    def package(self,files):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for name,data in files.items(): z.writestr(name,data)
        return out.getvalue()
    def test_only_executable_and_guide_are_accepted(self):
        data=self.package({'AutoBox.exe':b'MZfake','COMO_USAR.txt':b'guide'})
        with patch.object(u,'download',return_value=data):
            stage=u.stage_update({'zip_url':'unused','sha256':hashlib.sha256(data).hexdigest()})
        self.assertEqual({p.name for p in stage.iterdir()},u.FILES)
        import shutil
        shutil.rmtree(stage)
    def test_rejects_source_profile_and_traversal(self):
        for unwanted in ('controller.py','profile/cookies','../AutoBox.exe'):
            data=self.package({'AutoBox.exe':b'MZfake','COMO_USAR.txt':b'guide',unwanted:b'bad'})
            with patch.object(u,'download',return_value=data),self.assertRaises(ValueError):
                u.stage_update({'zip_url':'unused','sha256':hashlib.sha256(data).hexdigest()})
    def test_hash_mismatch_rejected(self):
        with patch.object(u,'download',return_value=b'bad'),self.assertRaises(ValueError):
            u.stage_update({'zip_url':'unused','sha256':'0'*64})
    def test_updates_only_from_user_channel(self):
        u.verified_url(u.MANIFEST_URL)
        u.verified_url(f'https://github.com/{u.REPO}/releases/download/usuario-0.11.0/AutoBox_Usuario.zip')
        for url in ('https://example.com/AutoBox_Usuario.zip',f'https://raw.githubusercontent.com/{u.REPO}/main/AutoBox_Sem_Mouse/AutoBox_Sem_Mouse.zip'):
            with self.assertRaises(ValueError):u.verified_url(url)
