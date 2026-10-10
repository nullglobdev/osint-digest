import argparse
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import bot
import desktop_ai
import server
import server_setup
import server_settings as settings
from ai_endpoints import ollama_base_url

WEBHOOK = 'https://discord.com/api/webhooks/123/test-token'
SOURCE = {'name': 'Test', 'feed': 'https://publisher.example/feed',
          'hosts': ['publisher.example'], 'enabled': True}


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        settings.initialize(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, **changes):
        config, revision = settings.load_config(self.root)
        config.update(changes)
        settings.save_config(self.root, config, revision)
        return config

    def test_fresh_profile_is_paused_and_does_not_inherit_credentials(self):
        with patch.dict(os.environ, DISCORD_WEBHOOK_URL='shell-secret', GEMINI_API_KEY='shell-key'):
            config, _ = settings.load_config(self.root)
            self.assertFalse(config['enabled'])
            self.assertEqual(config['provider'], 'none')
            self.assertEqual(config['webhook'], '')
            self.assertGreater(len(config['sources']), 0)
            with settings.configured_environment(config):
                self.assertEqual(os.environ['DISCORD_WEBHOOK_URL'], '')
                self.assertNotIn('GEMINI_API_KEY', os.environ)
            self.assertEqual(os.environ['GEMINI_API_KEY'], 'shell-key')

    def test_config_rejects_stale_session_and_preserves_valid_file(self):
        original, revision = settings.load_config(self.root)
        self.configure(interval_minutes=360)
        original['max_posts'] = 10
        with self.assertRaises(settings.SettingsError):
            settings.save_config(self.root, original, revision)
        self.assertEqual(settings.load_config(self.root)[0]['interval_minutes'], 360)
        self.assertEqual(settings.load_config(self.root)[0]['max_posts'], 5)

    def test_validation_bounds_and_credential_safe_messages(self):
        config, _ = settings.load_config(self.root)
        for changes in ({'interval_minutes': 361}, {'interval_minutes': 14}, {'max_posts': 0},
                        {'enabled': 'yes'}, {'webhook': 'https://example.test/secret-token'},
                        {'schema_version': 999}, {'ollama_url': 'http://secret-token@host:11434'}):
            with self.subTest(changes=changes), self.assertRaises(settings.SettingsError) as caught:
                settings.validate({**config, **changes})
            self.assertNotIn('secret-token', str(caught.exception))
        for interval in (15, 360):
            settings.validate({**config, 'interval_minutes': interval})

    @unittest.skipUnless(os.name == 'posix', 'POSIX container file permissions')
    def test_config_is_private_before_and_after_save(self):
        path = self.root / 'server.json'
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.configure(max_posts=10)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_provider_keys_are_isolated_and_paid_ai_requires_opt_in(self):
        config = self.configure(provider='openai', webhook=WEBHOOK, profiles={
            'openai': {'api_key': 'openai-key', 'model': 'gpt-test', 'allow_paid': False},
            'gemini': {'api_key': 'gemini-key', 'model': 'gemini-test'}})
        with self.assertRaises(settings.SettingsError):
            settings.require_ready(config)
        config['profiles']['openai']['allow_paid'] = True
        settings.require_ready(config)
        with patch.dict(os.environ, GEMINI_API_KEY='inherited-key'), settings.configured_environment(config):
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'openai-key')
            self.assertEqual(os.environ['AI_MODEL'], 'gpt-test')
            self.assertEqual(os.environ['ALLOW_PAID_AI'], 'true')
            self.assertNotIn('GEMINI_API_KEY', os.environ)

    def test_run_uses_config_snapshot_and_preserves_collector_context(self):
        self.configure(webhook=WEBHOOK, sources=[SOURCE], max_posts=1)
        original_root = bot.ROOT
        with patch.object(bot, 'run', return_value=0) as run, patch.object(bot, 'load_env') as env, redirect_stdout(io.StringIO()):
            self.assertEqual(server.run_action(self.root, 'preview'), 0)
            self.assertEqual(run.call_args.args[0].batch, 1)
            self.assertTrue(run.call_args.args[0].dry_run)
            self.assertEqual(run.call_args.kwargs['sources'], [SOURCE])
            env.assert_not_called()
        self.assertEqual(bot.ROOT, original_root)
        self.assertEqual(json.loads((self.root / 'last-run.json').read_text())['action'], 'preview')

    def test_preview_does_not_send_or_change_history(self):
        self.configure(webhook=WEBHOOK, sources=[SOURCE], max_posts=1)
        state = {'feeds': {}, 'pending': {}, 'seen': {'old': {'status': 'sent'}}}
        bot.save_state(self.root / 'state/state.json', state)
        original = (self.root / 'state/state.json').read_bytes()
        entry = {'source': 'Test', 'title': 'Test article', 'url': 'https://publisher.example/one',
                 'published': '', 'discovered': bot.now()}
        with patch.object(bot, 'fetch', return_value=(200, b'feed', {}, '')), patch.object(bot, 'parse_feed', return_value=[entry]), patch.object(bot, 'article_report', return_value={
            **entry, 'ai_status': 'No AI', 'analysis': None, 'iocs': [], 'cves': [], 'attack_ids': [],
            'publisher_excerpt': 'Text'}), patch.object(bot, 'send_discord') as send, redirect_stdout(io.StringIO()):
            self.assertEqual(server.run_action(self.root, 'preview'), 0)
            send.assert_not_called()
        self.assertEqual((self.root / 'state/state.json').read_bytes(), original)
        self.assertEqual(len(list((self.root / 'preview').glob('*.json'))), 1)

    def test_busy_worker_blocks_second_action_and_backup(self):
        with settings.file_lock(self.root / '.run.lock'):
            with self.assertRaises(settings.BusyError):
                server.run_action(self.root, 'check-feeds')
            with self.assertRaises(settings.BusyError):
                server.backup(self.root)
        with patch.object(bot, 'run', return_value=0), redirect_stdout(io.StringIO()):
            self.assertEqual(server.run_action(self.root, 'check-feeds'), 0)

    def test_service_lock_blocks_duplicate_daemon(self):
        with settings.file_lock(self.root / '.service.lock'), self.assertRaises(settings.BusyError):
            server.serve(self.root, threading.Event())

    def test_paused_service_reloads_configuration_without_restart(self):
        stop = threading.Event()
        calls = []
        def wait(_):
            if not calls:
                self.configure(webhook=WEBHOOK, enabled=True, interval_minutes=360)
        def run(*args, **kwargs):
            calls.append((args, kwargs))
            stop.set()
            return 1  # A failed feed is recorded, not a tight restart loop.
        with patch.object(stop, 'wait', side_effect=wait), patch.object(server, 'run_action', side_effect=run), redirect_stdout(io.StringIO()):
            self.assertEqual(server.serve(self.root, stop), 0)
        self.assertEqual(len(calls), 1)
        state = json.loads((self.root / 'runtime.json').read_text())
        self.assertEqual(state['phase'], 'stopped')
        self.assertEqual(state['last_exit_code'], 1)

    def test_invalid_enabled_configuration_pauses_without_network(self):
        self.configure(enabled=True)
        stop = threading.Event()
        with patch.object(stop, 'wait', side_effect=lambda _: stop.set()), patch.object(server, 'run_action') as run, redirect_stdout(io.StringIO()):
            server.serve(self.root, stop)
            run.assert_not_called()

    def test_health_rejects_missing_stale_and_failed_runtime(self):
        self.assertEqual(server.health(self.root), 1)
        for phase, age, expected in [('paused', 0, 0), ('running', 0, 0), ('idle', 120, 1),
                                     ('stopped', 0, 1), ('configuration-error', 0, 1)]:
            settings.atomic_json(self.root / 'runtime.json', {'phase': phase, 'heartbeat': time.time() - age})
            self.assertEqual(server.health(self.root), expected)

    def test_stop_finishes_current_post_and_retains_remaining_queue(self):
        self.configure(webhook=WEBHOOK, sources=[SOURCE], max_posts=2)
        pending = {f'https://publisher.example/{i}': {'url': f'https://publisher.example/{i}',
            'source': 'Test', 'discovered': str(i), 'title': f'Article {i}', 'published': ''} for i in range(2)}
        bot.save_state(self.root / 'state/state.json', {'feeds': {}, 'pending': pending, 'seen': {}})
        stop = threading.Event()
        def send(report):
            stop.set()
            return 'message-1'
        with patch.object(bot, 'discover', return_value=0), patch.object(bot, 'article_report', return_value={
            'ai_status': 'No AI', 'analysis': None}), patch.object(bot, 'send_discord', side_effect=send) as post, redirect_stdout(io.StringIO()):
            self.assertEqual(server.run_action(self.root, 'new', stop=stop), 0)
            self.assertEqual(post.call_count, 1)
        saved = json.loads((self.root / 'state/state.json').read_text())
        self.assertEqual(saved['seen']['https://publisher.example/0']['message_id'], 'message-1')
        self.assertIn('https://publisher.example/1', saved['pending'])

    def test_secret_values_are_hidden_in_status_and_worker_logs(self):
        config = self.configure(webhook=WEBHOOK, profiles={'gemini': {'api_key': 'secret-key', 'model': ''}})
        output = io.StringIO()
        with redirect_stdout(output):
            server.show_status(self.root)
        stream = server.RedactedStream(output, config)
        stream.write(WEBHOOK + ' secret-key')
        self.assertNotIn(WEBHOOK, output.getvalue())
        self.assertNotIn('secret-key', output.getvalue())
        self.assertIn('[hidden]', output.getvalue())

    def test_webhook_check_uses_get_and_refuses_redirects(self):
        self.configure(webhook=WEBHOOK)
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('server.urllib.request.build_opener') as opener, redirect_stdout(io.StringIO()):
            opener.return_value.open.return_value = response
            self.assertEqual(server.run_action(self.root, 'test-discord'), 0)
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertIsInstance(opener.call_args.args[0], desktop_ai.NoRedirect)

    def test_backup_contains_configuration_and_history_without_recursive_backups(self):
        self.configure(webhook=WEBHOOK)
        bot.save_state(self.root / 'state/state.json', {'seen': {'example': 'sent'}})
        with redirect_stdout(io.StringIO()):
            target = server.backup(self.root)
        with tarfile.open(target) as archive:
            names = archive.getnames()
            self.assertIn('server.json', names)
            self.assertIn('state/state.json', names)
            self.assertFalse(any('backups' in p or '.lock' in p for p in names))

    def test_terminal_wizard_preserves_secrets_and_can_pause(self):
        self.configure(webhook=WEBHOOK, enabled=True)
        # Keep webhook, choose excerpts, 10 articles, 360 minutes, pause, skip sources.
        with patch('server_setup.getpass.getpass', return_value=''), patch('builtins.input', side_effect=['5', '10', '360', 'n', 'n']), redirect_stdout(io.StringIO()):
            server_setup.edit(self.root, 'setup')
        config, _ = settings.load_config(self.root)
        self.assertEqual(config['webhook'], WEBHOOK)
        self.assertEqual((config['max_posts'], config['interval_minutes'], config['enabled']), (10, 360, False))

    def test_sources_menu_adds_reorders_and_disables_custom_feed(self):
        config, _ = settings.load_config(self.root)
        config['sources'] = [SOURCE]
        answers = ['a', 'Custom', 'https://custom.example/rss', 'articles.example',
                   'm', '2', '1', 't', '1', '0']
        with patch('builtins.input', side_effect=answers), redirect_stdout(io.StringIO()):
            server_setup.sources_menu(config)
        settings.validate(config)
        self.assertEqual(config['sources'][0]['name'], 'Custom')
        self.assertFalse(config['sources'][0]['enabled'])
        self.assertIn('articles.example', config['sources'][0]['hosts'])

    def test_model_menu_uses_selected_provider_key_and_endpoint(self):
        config = self.configure(provider='ollama')
        with patch('builtins.input', side_effect=['y', '1']), patch('server_setup.list_models', return_value=['local:8b']) as models, redirect_stdout(io.StringIO()):
            server_setup.choose_model(config)
        self.assertEqual(models.call_args.args, ('ollama', '', config['ollama_url']))
        self.assertEqual(config['profiles']['ollama']['model'], 'local:8b')

    def test_noninteractive_setup_exits_without_reading_or_echoing_password(self):
        result = subprocess.run([sys.executable, str(Path(server.__file__).resolve()), '--data-dir', str(self.root), 'setup'],
                                 input='do-not-echo-this\n', text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('interactive terminal', result.stderr)
        self.assertNotIn('do-not-echo-this', result.stdout + result.stderr)

    def test_ollama_generation_and_discovery_share_custom_endpoint(self):
        config = self.configure(provider='ollama', ollama_url='http://ollama:11434',
            profiles={'ollama': {'model': 'local:8b', 'api_key': ''}})
        article = 'The vendor recommends installing the security update immediately.'
        response = json.dumps({'summary': [{'text': 'Install the update.', 'evidence': article}]})
        with settings.configured_environment(config), patch.object(bot, 'api_json', return_value={'message': {'content': response}}) as api:
            summary, _ = bot.summarize(article)
            self.assertTrue(summary)
            self.assertEqual(api.call_args.args[0], 'http://ollama:11434/api/chat')
        with patch.object(desktop_ai, 'get_json', return_value={'models': []}) as get:
            desktop_ai.list_models('ollama', 'not-sent', config['ollama_url'])
            self.assertEqual(get.call_args.args, ('http://ollama:11434/api/tags', {}))
        for url in ('file:///tmp/model', 'http://name:secret@host', 'http://host/?secret=1', 'http://host:bad'):
            with self.assertRaises(ValueError):
                ollama_base_url(url)


if __name__ == '__main__':
    unittest.main()
