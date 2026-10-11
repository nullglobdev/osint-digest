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
    def test_additional_scope_migration_roundtrip_and_worker_flags(self):
        from osint_digest.core import scopes
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            (root / 'settings.json').write_text(json.dumps({'schema_version': 6, 'sector_scope': 'education'}))
            value = settings.load_settings(root)
            self.assertEqual(value['sector_scope'], 'education')
            self.assertTrue(all(value[key] == '' for key in scopes.CATALOGS))
            chosen = {key: next(iter(catalog)) for key, catalog in scopes.CATALOGS.items()}
            value.update(chosen, provider='none', developer_mode=True)
            settings.save_settings(root, value)
            self.assertEqual(scopes.selection(settings.load_settings(root)), scopes.selection(value))
            for action in ('new', 'test', 'preview', 'test-preview', 'ai'):
                def main():
                    argv = worker.sys.argv
                    for key, option in scopes.selection(value).items():
                        self.assertEqual(argv[argv.index('--' + key.replace('_', '-')) + 1], option)
                    return 0
                with self.subTest(action=action), patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main):
                    self.assertEqual(worker.run_worker(root, action), 0)
            for key in scopes.CATALOGS:
                with self.assertRaises(ValueError):
                    settings.validate({**value, key: 'unknown'})

    def test_test_timeframe_migration_validation_and_worker_isolation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            (root / 'settings.json').write_text(json.dumps({'schema_version': 5}))
            value = settings.load_settings(root)
            self.assertEqual(value['test_lookback_days'], 2)
            value.update(test_lookback_days=30, developer_mode=True, provider='none')
            settings.save_settings(root, value)
            self.assertEqual(settings.load_settings(root)['test_lookback_days'], 30)
            for invalid in (0, 366, True, '7'):
                with self.assertRaises(ValueError):
                    settings.validate({**value, 'test_lookback_days': invalid})
            for action in ('new', 'test', 'preview', 'test-preview', 'ai'):
                def main():
                    argv = worker.sys.argv
                    self.assertEqual(argv[argv.index('--max-age-hours') + 1], '48' if action == 'new' else '720')
                    return 0
                with self.subTest(action=action), patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main):
                    self.assertEqual(worker.run_worker(root, action), 0)
            value['developer_mode'] = False
            settings.save_settings(root, value)
            with patch.object(worker.bot, 'main') as collect:
                self.assertEqual(worker.run_worker(root, 'test'), 1)
                collect.assert_not_called()

    def test_scope_defaults_migration_validation_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'settings.json').write_text(json.dumps({'schema_version': 4, 'per_source_limit': 8}))
            config = settings.load_settings(root)
            self.assertEqual(config['sector_scope'], '')
            settings.save_settings(root, {**config, 'sector_scope': 'education'})
            saved = settings.load_settings(root)
            self.assertEqual(saved['sector_scope'], 'education')
            self.assertEqual(saved['per_source_limit'], 8)
            with self.assertRaises(ValueError):
                settings.validate({**saved, 'sector_scope': 'unknown'})

    def test_worker_passes_scope_for_all_collection_actions(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            settings.save_settings(root, {**settings.DEFAULTS, 'provider': 'none',
                                         'sector_scope': 'education', 'developer_mode': True})
            def main():
                argv = worker.sys.argv
                self.assertEqual(argv[argv.index('--sector-scope') + 1], 'education')
                self.assertEqual(argv[argv.index('--max-age-hours') + 1], '48')
                return 0
            for action in ('new', 'preview', 'test', 'test-preview', 'ai'):
                with self.subTest(action=action), patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main) as collect:
                    self.assertEqual(worker.run_worker(root, action), 0)
                    collect.assert_called_once()

    def test_limit_migrates_from_old_test_count_and_saves_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'settings.json').write_text(json.dumps({'schema_version': 3, 'batch_size': 10}))
            migrated = settings.load_settings(root)
            self.assertEqual(migrated['per_source_limit'], 10)
            migrated['per_source_limit'] = 100
            settings.save_settings(root, migrated)
            self.assertEqual(settings.load_settings(root)['per_source_limit'], 100)
            self.assertNotIn('batch_size', json.loads((root / 'settings.json').read_text()))
            for value in (0, 101, True, '5'):
                with self.assertRaises(ValueError):
                    settings.validate({**migrated, 'per_source_limit': value})

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

    def test_worker_test_mode_routes_count_and_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            value = {**settings.DEFAULTS, 'webhook': 'https://discord.com/api/webhooks/123/test-secret',
                     'api_key': 'private-gemini-secret', 'per_source_limit': 10, 'developer_mode': True}
            settings.save_settings(root, value)
            def main():
                self.assertEqual(worker.sys.argv, ['bot.py', '--test-mode', '--per-source-limit', '10', '--max-age-hours', '48'])
                self.assertEqual(worker.bot.ROOT, root)
                print(value['webhook'], value['api_key'])
                return 0
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main):
                self.assertEqual(worker.run_worker(root, 'test'), 0)
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

    def test_worker_normal_and_dev_actions_enforce_source_limit_and_age_window(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, MAX_POSTS='1'):
            root = Path(tmp)
            settings.initialize(root)
            settings.save_settings(root, {**settings.DEFAULTS, 'developer_mode': True})
            calls = []
            def main():
                calls.append(worker.sys.argv[:])
                self.assertNotIn('MAX_POSTS', os.environ)
                return 0
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=main):
                for action in ('new', 'preview', 'test-preview'):
                    self.assertEqual(worker.run_worker(root, action), 0)
            self.assertEqual(calls, [['bot.py', '--per-source-limit', '5', '--max-age-hours', '48', '--local'],
                                     ['bot.py', '--dry-run', '--per-source-limit', '5', '--max-age-hours', '48', '--local'],
                                     ['bot.py', '--test-mode', '--dry-run', '--per-source-limit', '5', '--max-age-hours', '48', '--local']])

    def test_worker_rejects_preview_actions_outside_dev_mode(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main') as main:
                for action in ('preview', 'test', 'test-preview', 'ai'):
                    self.assertEqual(worker.run_worker(root, action), 1)
                main.assert_not_called()
            self.assertIn('Dev mode', (root / 'activity.log').read_text())

    def test_worker_with_webhook_keeps_discord_destination(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            settings.save_settings(root, {**settings.DEFAULTS, 'webhook': 'https://discord.com/api/webhooks/123/test'})
            calls = []
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'main', side_effect=lambda: calls.append(worker.sys.argv[:]) or 0):
                self.assertEqual(worker.run_worker(root, 'new'), 0)
            self.assertEqual(calls, [['bot.py', '--per-source-limit', '5', '--max-age-hours', '48']])

    def test_worker_publishes_in_app_without_webhook_and_remembers_delivery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            settings.initialize(root)
            settings.save_settings(root, {**settings.DEFAULTS, 'provider': 'none'})
            source = {'name': 'Test', 'feed': 'https://publisher.example/rss', 'hosts': ['publisher.example']}
            settings.atomic_json(root / 'sources.json', [source])
            raw = f'<rss><channel><item><title>Example</title><link>https://publisher.example/one</link><pubDate>{worker.bot.now()}</pubDate></item></channel></rss>'.encode()
            def report(source, entry):
                return worker.bot.make_report(entry, 'Example article content. ' * 30, 'HTML')
            with patch.object(worker.bot, 'ROOT', root), patch.object(worker.bot, 'fetch', return_value=(200, raw, {}, '')), patch.object(worker.bot, 'article_report', side_effect=report) as process, patch.object(worker.bot, 'send_discord') as send:
                self.assertEqual(worker.run_worker(root, 'new'), 0)
                self.assertEqual(worker.run_worker(root, 'new'), 0)
                process.assert_called_once()
                send.assert_not_called()
            reports = list((root / 'results').glob('*.json'))
            self.assertEqual(len(reports), 1)
            self.assertEqual(json.loads(reports[0].read_text())['title'], 'Example')
            self.assertFalse((root / 'state/state.json').exists())

if __name__ == '__main__':
    unittest.main()
