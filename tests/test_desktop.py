import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from osint_digest.desktop import settings as settings
from osint_digest.desktop import worker as worker
@unittest.skipUnless(os.name == 'nt', 'Desktop app targets Windows')
class DesktopTests(unittest.TestCase):
    def test_settings_encrypt_secrets_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = {**settings.DEFAULTS, 'webhook': 'https://discord.com/api/webhooks/123/private-webhook-token',
                     'api_key': 'private-test-api-key'}
            settings.save_settings(root, value)
            stored = (root / 'settings.json').read_text()
            self.assertNotIn('private-webhook-token', stored)
            self.assertNotIn('private-test-api-key', stored)
            loaded = settings.load_settings(root)
            self.assertEqual(loaded['api_key'], value['api_key'])
            self.assertEqual(loaded['webhook'], value['webhook'])
            self.assertEqual(loaded['profiles']['gemini']['api_key'], value['api_key'])

    def test_fresh_profile_has_sources_but_no_developer_credentials_or_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings.initialize(root)
            self.assertFalse((root / '.env').exists())
            self.assertFalse((root / 'state/state.json').exists())
            self.assertEqual(settings.load_settings(root), settings.DEFAULTS)
            sources = json.loads((root / 'sources.json').read_text())
            self.assertGreaterEqual(len(sources), 10)
            sources[0]['enabled'] = False
            settings.atomic_json(root / 'sources.json', sources)
            settings.initialize(root)
            self.assertFalse(json.loads((root / 'sources.json').read_text())[0]['enabled'])

    def test_inherited_shell_credentials_are_not_used(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'shell-secret', 'OPENAI_API_KEY': 'other-secret',
                                     'DISCORD_WEBHOOK_URL': 'shell-webhook'}):
            settings.apply_environment(settings.DEFAULTS)
            self.assertEqual(os.environ['GEMINI_API_KEY'], '')
            self.assertEqual(os.environ['DISCORD_WEBHOOK_URL'], '')
            self.assertNotIn('OPENAI_API_KEY', os.environ)

    def test_invalid_webhook_is_rejected_without_secret_in_error(self):
        for url in ('http://discord.com/api/webhooks/123/secret', 'https://evil.test/api/webhooks/123/secret',
                    'https://discord.com:444/api/webhooks/123/secret', 'https://name:pass@discord.com/api/webhooks/123/secret'):
            with self.subTest(url=url), self.assertRaises(ValueError) as error:
                settings.validate({**settings.DEFAULTS, 'webhook': url})
            self.assertNotIn('secret', str(error.exception))

    def test_worker_batch_routes_count_and_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            value = {**settings.DEFAULTS, 'webhook': 'https://discord.com/api/webhooks/123/test-secret',
                     'api_key': 'private-gemini-secret', 'batch_size': 10}
            settings.save_settings(root, value)
            def main():
                self.assertEqual(worker.sys.argv, ['bot.py', '--batch', '10'])
                self.assertEqual(worker.bot.ROOT, root)
                print(value['webhook'], value['api_key'])
                return 0
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main):
                self.assertEqual(worker.run_worker(root, 'batch'), 0)
            log = (root / 'activity.log').read_text()
            self.assertIn('[hidden]', log)
            self.assertNotIn('test-secret', log)
            self.assertNotIn('private-gemini-secret', log)

    def test_webhook_check_does_not_send_a_message(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            settings.save_settings(root, {**settings.DEFAULTS, 'webhook': 'https://discord.com/api/webhooks/123/test'})
            response = io.BytesIO(b'{}')
            response.status = 200
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.urllib.request, 'urlopen', return_value=response) as request, patch.object(worker.bot, 'send_discord') as send:
                self.assertEqual(worker.run_worker(root, 'webhook'), 0)
                self.assertIsNone(request.call_args.args[0].data)
                send.assert_not_called()

if __name__ == '__main__':
    unittest.main()
