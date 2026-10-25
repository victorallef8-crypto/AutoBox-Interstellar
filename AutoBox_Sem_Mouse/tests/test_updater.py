import unittest
from unittest.mock import patch, MagicMock
import updater

class UpdateTransportTests(unittest.TestCase):
    def test_internal_cache_nonce_and_headers_keep_exact_response_url(self):
        response=MagicMock()
        response.__enter__.return_value=response
        response.geturl.return_value=updater.MANIFEST_URL+"?autobox_check=123"
        response.read.return_value=b"{}"
        opener=MagicMock(); opener.open.return_value=response
        with patch.object(updater.time,"time_ns",return_value=123), patch.object(updater.urllib.request,"build_opener",return_value=opener):
            self.assertEqual(updater._read_url(updater.MANIFEST_URL,100),b"{}")
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,response.geturl.return_value)
        self.assertEqual(request.get_header("Cache-control"),"no-cache")
        with self.assertRaises(ValueError):
            updater._verified_repo_url(response.geturl.return_value)

    def test_changed_response_url_remains_rejected(self):
        response=MagicMock(); response.__enter__.return_value=response
        response.geturl.return_value="https://example.org/file"
        opener=MagicMock(); opener.open.return_value=response
        with patch.object(updater.urllib.request,"build_opener",return_value=opener):
            with self.assertRaises(ValueError):
                updater._read_url(updater.MANIFEST_URL,100)
