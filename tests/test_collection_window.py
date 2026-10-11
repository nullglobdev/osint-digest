"""Recent-article limits shared by desktop and server; transports stay offline."""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from osint_digest.core import collector as bot
from osint_digest.server import app as server, settings as server_settings

CLOCK = datetime(2026, 10, 10, 16, tzinfo=timezone.utc).timestamp()
SOURCES = [{'name': name, 'feed': f'https://publisher.example/{name}/rss',
            'hosts': ['publisher.example']} for name in ('A', 'B')]


def date(hours):
    return datetime.fromtimestamp(CLOCK - hours * 3600, timezone.utc).isoformat()


def entry(name, hours, source='A'):
    return {'source': source, 'url': f'https://publisher.example/{name}', 'title': name,
            'published': date(hours), 'discovered': date(0)}


def feed(entries):
    return ('<rss><channel>' + ''.join(f"<item><title>{e['title']}</title><link>{e['url']}</link>"
            f"<pubDate>{e['published']}</pubDate></item>" for e in entries) + '</channel></rss>').encode()


class CollectionWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = SimpleNamespace(check_feeds=False, dry_run=False, per_source_limit=2, max_age_hours=48)
        self.entries = {'A': [entry('a-old', 60), entry('a-3', 3), entry('a-2', 2), entry('a-1', 1)],
                        'B': [entry('b-3', 3, 'B'), entry('b-1', 1, 'B'), entry('b-2', 2, 'B')]}
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(bot, 'ROOT', self.root))
        stack.enter_context(patch.dict(bot.os.environ, DISCORD_WEBHOOK_URL='fake', AI_PROVIDER='none'))
        self.clock = stack.enter_context(patch('time.time', return_value=CLOCK))
        stack.enter_context(redirect_stdout(io.StringIO()))
        self.fetch = stack.enter_context(patch.object(bot, 'fetch', side_effect=lambda url, *_:
            (200, feed(self.entries['B' if '/B/' in url else 'A']), {'ETag': 'cache'}, url)))
        self.report = stack.enter_context(patch.object(bot, 'article_report', side_effect=lambda source, item:
            {**item, 'analysis': None, 'ai_status': 'No AI', 'iocs': [], 'cves': [], 'attack_ids': [], 'publisher_excerpt': 'Excerpt'}))
        self.send = stack.enter_context(patch.object(bot, 'send_discord', return_value='receipt'))

    def run_check(self):
        return bot.run(self.args, sources=SOURCES)

    def test_normal_checks_limit_each_source_newest_first_and_skip_delivered_after_restart(self):
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list], ['a-1', 'b-1', 'a-2', 'b-2'])
        saved = json.loads((self.root / 'state/state.json').read_text())
        self.assertEqual({e['title'] for e in saved['pending'].values()}, {'a-3', 'b-3'})
        self.assertEqual(self.run_check(), 0)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list[4:]], ['a-3', 'b-3'])
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.send.call_count, 6)
        self.assertEqual(self.fetch.call_count, 6)

    def test_dev_resends_stay_inside_window_and_use_per_source_limit(self):
        self.run_check()
        self.send.reset_mock()
        self.args.test_mode = True
        self.assertEqual(self.run_check(), 0)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list], ['a-1', 'b-1', 'a-2', 'b-2'])
        self.assertNotIn('a-old', [c.args[0]['title'] for c in self.send.call_args_list])

    def test_extended_test_window_collects_older_articles_and_normal_returns_to_48_hours(self):
        self.entries = {'A': [entry('week-old', 6 * 24), entry('too-old', 8 * 24)], 'B': [entry('ancient', 366 * 24, 'B')]}
        self.args.test_mode = True
        self.args.max_age_hours = 7 * 24
        self.assertEqual(self.run_check(), 0)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list], ['week-old'])
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.send.call_count, 1)  # Explicit tests can repeat it.
        self.entries['A'].append(entry('other-old-unsent', 72))
        self.args.test_mode = False
        self.args.max_age_hours = 48
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.send.assert_not_called()

    def test_extended_preview_preserves_history_and_rejects_unknown_or_future_dates(self):
        self.run_check()
        self.run_check()
        before = (self.root / 'state/state.json').read_bytes()
        self.entries = {'A': [entry('week-old', 6 * 24), entry('future', -2),
                              {**entry('undated', 1), 'published': ''}], 'B': [entry('ancient', 366 * 24, 'B')]}
        self.args.dry_run = True
        self.args.max_age_hours = 7 * 24
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        reports = list((self.root / 'preview').glob('*.json'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text())['title'], 'week-old')
        self.assertEqual((self.root / 'state/state.json').read_bytes(), before)
        self.send.assert_not_called()

    def test_extended_window_requires_testing_and_enforces_bounds_before_fetch(self):
        for hours in (0, True, '168', 8761, 168):
            self.args.max_age_hours = hours
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                self.run_check()
        self.fetch.assert_not_called()
        self.args.test_mode = True
        self.args.max_age_hours = 8760
        self.assertEqual(self.run_check(), 0)

    def test_extended_window_rechecked_after_ai_and_before_each_webhook(self):
        self.entries = {'A': [entry('edge', 7 * 24 - 1 / 3600)], 'B': [entry('ancient', 366 * 24, 'B')]}
        self.args.test_mode = True
        self.args.max_age_hours = 7 * 24
        original = self.report.side_effect
        def slow_report(source, item):
            self.clock.return_value = CLOCK + 2
            return original(source, item)
        self.report.side_effect = slow_report
        self.assertEqual(self.run_check(), 0)
        self.send.assert_not_called()
        self.clock.return_value = CLOCK
        self.report.side_effect = original
        server_settings.initialize(self.root)
        config, revision = server_settings.load_config(self.root)
        config.update(sources=SOURCES, webhooks=[
            {'name': str(i), 'url': f'https://discord.com/api/webhooks/{i}/offline-test', 'enabled': True}
            for i in (123, 456)])
        server_settings.save_config(self.root, config, revision)
        def slow_send(*args, **kwargs):
            self.clock.return_value = CLOCK + 2
            return 'receipt'
        self.send.side_effect = slow_send
        server.run_action(self.root, 'new', test_mode=True, test_days=7)
        self.send.assert_called_once()  # The second destination sees an expired article.

    def test_extended_ai_test_uses_selected_days_without_posting(self):
        self.entries = {'A': [entry('week-old', 6 * 24)], 'B': []}
        self.args.test_ai = 'A'
        self.args.max_age_hours = 7 * 24
        with patch.dict(bot.os.environ, AI_PROVIDER='gemini'):
            self.assertEqual(self.run_check(), 1)  # Mock report is an excerpt, not AI.
        self.report.assert_called_once()
        self.assertEqual(json.loads((self.root / 'preview/ai-test.json').read_text())['title'], 'week-old')
        self.send.assert_not_called()

    def test_local_results_have_same_limit_and_deduplication(self):
        self.args.local = True
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(len(list((self.root / 'results').glob('*.json'))), 4)
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(len(list((self.root / 'results').glob('*.json'))), 6)
        self.send.assert_not_called()
        self.assertFalse((self.root / 'state/state.json').exists())

    def test_preview_respects_limits_and_window_without_changing_history(self):
        self.run_check()
        before = (self.root / 'state/state.json').read_bytes()
        self.args.dry_run = True
        self.args.test_mode = True
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(len(list((self.root / 'preview').glob('*.json'))), 4)
        self.assertEqual((self.root / 'state/state.json').read_bytes(), before)
        self.send.assert_not_called()

    def test_missing_invalid_future_and_naive_dates_are_excluded(self):
        self.entries['A'] = [{**entry(str(index), 1), 'published': value}
                             for index, value in enumerate(('', 'Not provided', 'bad', date(-1), '2026-10-10T15:00:00'))]
        self.entries['B'] = [entry('old', 49, 'B')]
        self.assertEqual(self.run_check(), 0)
        self.report.assert_not_called()
        self.send.assert_not_called()

    def test_age_boundary_and_timezone_offsets(self):
        self.assertTrue(bot.within_window(entry('edge', 48), 48, CLOCK))
        self.assertFalse(bot.within_window(entry('outside', 48 + 1 / 3600), 48, CLOCK))
        self.assertFalse(bot.within_window(entry('future', -1 / 3600), 48, CLOCK))
        for published in ('2026-10-10T08:00:00-04:00', '2026-10-10T14:00:00+02:00',
                          'Sat, 10 Oct 2026 08:00:00 -0400', '2026-10-10T12:00:00Z'):
            self.assertEqual(bot.publication_timestamp({'published': published}), CLOCK - 4 * 3600)

    def test_expired_retries_removed_even_if_feed_fails_and_new_source_still_runs(self):
        old = entry('expired-retry', 49)
        bot.save_state(self.root / 'state/state.json', {'feeds': {}, 'seen': {}, 'pending': {old['url']: old}})
        self.fetch.side_effect = [TimeoutError(), (200, feed(self.entries['B']), {}, '')]
        self.assertEqual(self.run_check(), 1)
        saved = json.loads((self.root / 'state/state.json').read_text())
        self.assertNotIn(old['url'], saved['pending'])
        self.assertEqual({c.args[0]['source'] for c in self.send.call_args_list}, {'B'})

    def test_article_expiring_during_ai_call_is_not_published(self):
        self.entries = {'A': [entry('almost-expired', 48 - 1 / 3600)], 'B': [entry('old', 49, 'B')]}
        def slow_report(source, item):
            self.clock.return_value = CLOCK + 2
            return {**item, 'analysis': None, 'ai_status': 'No AI'}
        self.report.side_effect = slow_report
        self.assertEqual(self.run_check(), 0)
        self.report.assert_called_once()
        self.send.assert_not_called()
        self.assertFalse(json.loads((self.root / 'state/state.json').read_text())['pending'])

    def test_old_updated_atom_entry_does_not_become_recent(self):
        raw = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Edited</title><link href="https://publisher.example/edited"/><published>{date(96)}</published><updated>{date(1)}</updated></entry></feed>'.encode()
        item = bot.parse_feed(raw, SOURCES[0])[0]
        self.assertFalse(bot.within_window(item, 48, CLOCK))
        raw = raw.replace(f'<published>{date(96)}</published>'.encode(), b'')
        self.assertFalse(bot.within_window(bot.parse_feed(raw, SOURCES[0])[0], 48, CLOCK))

    def test_rss_and_atom_publication_formats_are_supported(self):
        for raw in (
            f'<rss><channel><item><link>https://publisher.example/rss</link><pubDate>{format_datetime(datetime.fromtimestamp(CLOCK - 3600, timezone.utc))}</pubDate></item></channel></rss>',
            f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://publisher.example/atom"/><published>{date(2)}</published></entry></feed>',
            f'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><link>https://publisher.example/dc</link><dc:date>{date(3)}</dc:date></item></channel></rss>'):
            self.assertTrue(bot.within_window(bot.parse_feed(raw.encode(), SOURCES[0])[0], 48, CLOCK))

    def test_ai_test_does_not_generate_for_an_old_article(self):
        self.entries['A'] = [entry('old', 49)]
        with patch.dict(bot.os.environ, AI_PROVIDER='gemini'):
            self.assertEqual(bot.test_ai(SOURCES, 'A', max_age_hours=48), 1)
        self.report.assert_not_called()
        self.send.assert_not_called()

    def test_server_applies_same_window_and_per_source_limit_to_every_webhook(self):
        server_settings.initialize(self.root)
        config, revision = server_settings.load_config(self.root)
        config.update(sources=SOURCES, per_source_limit=1, webhooks=[
            {'name': str(i), 'url': f'https://discord.com/api/webhooks/{i}/offline-test', 'enabled': True}
            for i in (123, 456)])
        server_settings.save_config(self.root, config, revision)
        self.assertEqual(server.run_action(self.root, 'new'), 0)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list], ['a-1', 'a-1', 'b-1', 'b-1'])
        self.send.reset_mock()
        self.assertEqual(server.run_action(self.root, 'new', test_mode=True), 0)
        self.assertEqual([c.args[0]['title'] for c in self.send.call_args_list], ['a-1', 'a-1', 'b-1', 'b-1'])


if __name__ == '__main__':
    unittest.main()
