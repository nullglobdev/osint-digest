"""Offline server fan-out, migration, retry, and operator workflow regression tests."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from osint_digest.core import collector as bot
from osint_digest.server import app, settings, setup


SOURCE = {'name': 'Test', 'feed': 'https://publisher.example/rss',
          'hosts': ['publisher.example'], 'enabled': True}
ENTRY = {'source': 'Test', 'url': 'https://publisher.example/article', 'title': 'Article',
         'published': bot.now(), 'discovered': '2026-10-10T00:00:00Z'}
REPORT = {**ENTRY, 'ai_status': 'No AI', 'analysis': None, 'iocs': [], 'cves': [],
          'attack_ids': [], 'publisher_excerpt': 'A publisher excerpt.'}
TARGETS = [{'name': 'Security', 'url': 'https://discord.com/api/webhooks/123/first-secret', 'enabled': True},
           {'name': 'Operations', 'url': 'https://discord.com/api/webhooks/456/second-secret', 'enabled': True}]


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        settings.initialize(self.root)
        self.configure(webhooks=deepcopy(TARGETS), sources=[SOURCE])
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.fetch = self.stack.enter_context(patch.object(bot, 'fetch', return_value=(200, b'feed', {'ETag': 'same'}, '')))
        self.stack.enter_context(patch.object(bot, 'parse_feed', side_effect=lambda *_: [dict(ENTRY)]))
        self.report = self.stack.enter_context(patch.object(bot, 'article_report', return_value=deepcopy(REPORT)))
        self.send = self.stack.enter_context(patch.object(bot, 'send_discord', return_value='message-id'))

    def configure(self, **changes):
        config, revision = settings.load_config(self.root)
        config.update(changes)
        settings.save_config(self.root, config, revision)
        return config

    def state(self):
        return json.loads((self.root / 'state/state.json').read_text())

    def test_all_targets_receive_one_report_and_restart_deduplicates(self):
        self.assertEqual(app.run_action(self.root, 'new'), 0)
        self.assertEqual(self.fetch.call_count, 1)
        self.assertEqual(self.report.call_count, 1)
        self.assertEqual([c.kwargs['webhook'] for c in self.send.call_args_list], [t['url'] for t in TARGETS])
        saved = self.state()
        self.assertEqual(set(saved['deliveries'][ENTRY['url']]), {'123', '456'})
        self.assertFalse(saved['pending'])
        self.assertEqual(saved['seen'][ENTRY['url']]['status'], 'sent')
        for target in TARGETS:
            self.assertNotIn(target['url'].rsplit('/', 1)[-1], json.dumps(saved))
        self.assertEqual(app.run_action(self.root, 'new'), 0)
        self.assertEqual(self.send.call_count, 2)
        self.assertEqual(self.report.call_count, 1)

    def test_failure_is_independent_and_retry_reuses_cached_report(self):
        self.send.side_effect = [TimeoutError(), 'healthy-message']
        self.assertEqual(app.run_action(self.root, 'new'), 1)
        saved = self.state()
        self.assertEqual(saved['deliveries'][ENTRY['url']]['456']['message_id'], 'healthy-message')
        self.assertNotIn(ENTRY['url'], saved['seen'])
        self.assertIn(ENTRY['url'], saved['pending'])
        # No due target: neither another post nor another AI call.
        self.assertEqual(app.run_action(self.root, 'new'), 0)
        self.assertEqual(self.send.call_count, 2)
        retry_at = saved['deliveries'][ENTRY['url']]['123']['retry_after']
        self.send.side_effect = None
        with patch('time.time', return_value=retry_at + 1):
            self.assertEqual(app.run_action(self.root, 'new'), 0)
        self.assertEqual(self.send.call_count, 3)
        self.assertEqual(self.send.call_args.kwargs['webhook'], TARGETS[0]['url'])
        self.assertEqual(self.report.call_count, 1)
        self.assertFalse(self.state()['pending'])

    def test_new_destination_receives_existing_feed_without_repeating_old_destination(self):
        self.configure(webhooks=deepcopy(TARGETS[:1]))
        app.run_action(self.root, 'new')
        self.configure(webhooks=deepcopy(TARGETS))
        self.fetch.reset_mock()
        self.send.reset_mock()
        app.run_action(self.root, 'new')
        self.assertEqual(self.fetch.call_args.args[2], {})  # bypass cached ETag
        self.send.assert_called_once_with(REPORT, webhook=TARGETS[1]['url'])

    def test_new_destination_does_not_wait_for_another_destinations_backoff(self):
        self.configure(webhooks=deepcopy(TARGETS[:1]))
        self.send.side_effect = TimeoutError()
        app.run_action(self.root, 'new')
        self.configure(webhooks=deepcopy(TARGETS))
        self.send.reset_mock(side_effect=True)
        app.run_action(self.root, 'new')
        self.send.assert_called_once_with(REPORT, webhook=TARGETS[1]['url'])
        self.assertEqual(self.report.call_count, 1)

    def test_disable_remove_readd_rename_and_token_rotation_keep_history(self):
        app.run_action(self.root, 'new')
        targets = deepcopy(TARGETS)
        targets[0]['enabled'] = False
        self.configure(webhooks=targets)
        app.run_action(self.root, 'new')
        self.configure(webhooks=targets[1:])
        app.run_action(self.root, 'new')
        targets[0].update(enabled=True, name='Renamed', url='https://discord.com/api/webhooks/123/rotated-token')
        self.configure(webhooks=targets)
        app.run_action(self.root, 'new')
        self.assertEqual(self.send.call_count, 2)

    def test_legacy_receipts_bind_only_to_original_webhook_before_settings_edit(self):
        legacy = {**deepcopy(settings.DEFAULTS), 'schema_version': 1, 'webhook': TARGETS[0]['url'], 'sources': [SOURCE]}
        legacy.pop('webhooks')
        legacy.pop('legacy_webhook_id')
        settings.atomic_json(self.root / 'server.json', legacy)
        bot.save_state(self.root / 'state/state.json', {'feeds': {'Test': {'delivery_only': True, 'etag': 'same'}},
            'pending': {}, 'seen': {ENTRY['url']: {'status': 'sent', 'message_id': 'legacy-message'}}})
        # Operator replaces the first URL before the new collector has run.
        config, revision = settings.load_config(self.root)
        config['webhooks'] = deepcopy(TARGETS[1:])
        settings.save_config(self.root, config, revision)
        app.run_action(self.root, 'new')
        self.send.assert_called_once_with(REPORT, webhook=TARGETS[1]['url'])
        self.assertEqual(self.state()['deliveries'][ENTRY['url']]['123']['message_id'], 'legacy-message')
        self.configure(webhooks=deepcopy(TARGETS))
        app.run_action(self.root, 'new')
        self.assertEqual(self.send.call_count, 1)

    def test_legacy_single_webhook_upgrade_does_not_replay(self):
        self.configure(webhooks=deepcopy(TARGETS[:1]), legacy_webhook_id='123')
        bot.save_state(self.root / 'state/state.json', {'feeds': {}, 'pending': {},
            'seen': {ENTRY['url']: {'status': 'sent', 'message_id': 'legacy'}}})
        app.run_action(self.root, 'new')
        self.send.assert_not_called()

    def test_stop_between_destinations_checkpoints_success_and_resumes(self):
        stop = threading.Event()
        def first(report, *, webhook):
            stop.set()
            return 'first-message'
        self.send.side_effect = first
        self.assertEqual(app.run_action(self.root, 'new', stop=stop), 0)
        self.assertEqual(self.send.call_count, 1)
        self.assertIn(ENTRY['url'], self.state()['pending'])
        self.send.reset_mock(side_effect=True)
        app.run_action(self.root, 'new')
        self.send.assert_called_once_with(REPORT, webhook=TARGETS[1]['url'])
        self.assertEqual(self.report.call_count, 1)

    def test_preview_never_writes_delivery_receipts_or_posts(self):
        self.configure(webhooks=deepcopy(TARGETS[:1]))
        app.run_action(self.root, 'new')
        self.configure(webhooks=deepcopy(TARGETS))
        before = (self.root / 'state/state.json').read_bytes()
        self.send.reset_mock()
        self.assertEqual(app.run_action(self.root, 'preview'), 0)
        self.send.assert_not_called()
        self.assertEqual((self.root / 'state/state.json').read_bytes(), before)
        self.assertEqual(len(list((self.root / 'preview').glob('*.json'))), 1)

    def test_test_mode_repeats_all_targets_and_failures_preserve_receipts(self):
        app.run_action(self.root, 'new')
        before = self.state()
        self.send.side_effect = TimeoutError()
        self.assertEqual(app.run_action(self.root, 'new', count=1, test_mode=True), 1)
        self.assertEqual(self.send.call_count, 4)
        after = self.state()
        self.assertEqual(after['deliveries'], before['deliveries'])
        self.assertEqual(after['pending'], before['pending'])
        self.send.side_effect = None
        app.run_action(self.root, 'new')
        self.assertEqual(self.send.call_count, 4)

    def test_failed_test_keeps_existing_destination_retry_unchanged(self):
        self.send.side_effect = [TimeoutError(), 'success']
        app.run_action(self.root, 'new')
        before = self.state()
        self.send.side_effect = TimeoutError()
        app.run_action(self.root, 'new', count=1, test_mode=True)
        after = self.state()
        self.assertEqual(after['pending'], before['pending'])
        self.assertEqual(after['deliveries'], before['deliveries'])

    def test_invalid_and_duplicate_targets_are_rejected_without_secret_echo(self):
        cases = [None, {}, [None], [{**TARGETS[0], 'enabled': 'yes'}],
                 [{**TARGETS[0], 'name': 'bad\nname'}], [{**TARGETS[0], 'url': 'https://evil.test/secret'}],
                 [{**TARGETS[0], 'url': TARGETS[0]['url'] + '?secret=1'}],
                 [TARGETS[0], {**TARGETS[1], 'name': TARGETS[0]['name']}],
                 [TARGETS[0], {**TARGETS[1], 'url': 'https://discord.com/api/webhooks/123/changed-secret'}]]
        for targets in cases:
            with self.subTest(targets=targets), self.assertRaises(settings.SettingsError) as caught:
                settings.validate_webhooks(targets)
            self.assertNotIn('secret', str(caught.exception))

    def test_all_disabled_blocks_delivery_and_ignores_inherited_webhook(self):
        targets = deepcopy(TARGETS)
        for target in targets:
            target['enabled'] = False
        config = self.configure(webhooks=targets)
        with self.assertRaises(settings.SettingsError):
            app.run_action(self.root, 'new')
        with settings.configured_environment(config):
            import os
            self.assertEqual(os.environ['DISCORD_WEBHOOK_URL'], '')
        self.send.assert_not_called()

    def test_webhook_menu_add_edit_disable_remove_and_secret_redaction(self):
        config, _ = settings.load_config(self.root)
        output = io.StringIO()
        answers = ['a', 'Third', 'e', '3', 'Renamed', 't', '1', 'r', '2', 'y', '0']
        with patch('builtins.input', side_effect=answers), patch('osint_digest.server.setup.getpass.getpass',
                side_effect=['https://discord.com/api/webhooks/789/third-secret', '']), redirect_stdout(output):
            setup.webhooks_menu(config)
        settings.validate(config)
        self.assertEqual([t['name'] for t in config['webhooks']], ['Security', 'Renamed'])
        self.assertFalse(config['webhooks'][0]['enabled'])
        self.assertNotIn('secret', output.getvalue())
        stream = app.RedactedStream(output, config)
        stream.write('first-secret third-secret ' + config['webhooks'][0]['url'])
        self.assertNotIn('secret', output.getvalue())
        self.assertNotIn('discord.com', output.getvalue())

    def test_connection_check_continues_after_failure_and_skips_disabled(self):
        targets = deepcopy(TARGETS) + [{'name': 'Paused', 'url': 'https://discord.com/api/webhooks/789/third-secret', 'enabled': False}]
        self.configure(webhooks=targets)
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('osint_digest.server.app.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = [TimeoutError(), response]
            self.assertEqual(app.run_action(self.root, 'test-discord'), 1)
            self.assertEqual(opener.return_value.open.call_count, 2)
            for call in opener.return_value.open.call_args_list:
                self.assertEqual(call.args[0].get_method(), 'GET')
                self.assertIsNone(call.args[0].data)
        self.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
