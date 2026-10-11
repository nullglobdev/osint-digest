"""Sector keyword matching and filtering before AI, output, and article limits."""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from osint_digest.core import collector as bot, sectors
from osint_digest.server import app as server, settings as server_settings, setup


class SectorKeywordTests(unittest.TestCase):
    def test_catalog_covers_all_sectors_and_education_groups(self):
        self.assertEqual(len(sectors.SECTORS), 23)
        self.assertEqual(len(sectors.SCOPES), 25)
        for scope, terms in sectors.KEYWORDS.items():
            for term in terms:
                with self.subTest(scope=scope, term=term):
                    self.assertIn(scope, sectors.classify(term))

    def test_education_accepts_any_provided_keyword_without_extra_context(self):
        for text in ('Cloud incident', 'New research', 'An IP address', 'China', 'SSO outage', 'universities affected', 'K12 schools'):
            with self.subTest(text=text):
                self.assertIn('education', sectors.classify(text))

    def test_boundaries_acronyms_phrases_and_plurals(self):
        for text in ('report damage label', 'it failed to respond', 'An exhibit at a large expo'):
            matches = sectors.classify(text)
            for scope in ('it', 'dams', 'transportation', 'education_research'):
                self.assertNotIn(scope, matches)
        self.assertIn('it', sectors.classify('The IT team found a ZERO–DAY.'))
        self.assertIn('financial', sectors.classify('Banks and credit unions were affected.'))
        self.assertIn('education', sectors.classify('Universities and campuses published advisories.'))

    def test_parenthetical_qualifier_requires_base_and_context(self):
        self.assertTrue(sectors.keyword_matches('ransomware (education)', 'Education suffered ransomware.'))
        self.assertFalse(sectors.keyword_matches('ransomware (education)', 'A ransomware campaign.'))
        self.assertFalse(sectors.keyword_matches('ransomware (education)', 'An education announcement.'))

    def test_reports_use_full_text_classification_and_legacy_available_text(self):
        report = {'title': 'Incident', 'sector_catalog': sectors.CATALOG_VERSION,
                  'sector_matches': {'education': ['university']}}
        self.assertTrue(sectors.report_matches(report, 'education'))
        self.assertFalse(sectors.report_matches(report, 'financial'))
        self.assertTrue(sectors.report_matches({'title': 'A university incident'}, 'education'))
        self.assertTrue(sectors.report_matches({'title': 'Anything'}, ''))
        self.assertFalse(sectors.report_matches({'title': 'Malformed', 'analysis': ['bad']}, 'education'))


class SectorCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = [{'name': name, 'feed': f'https://publisher.example/{name}/rss',
                         'hosts': ['publisher.example']} for name in ('A', 'B')]
        self.current = datetime.now(timezone.utc).timestamp()
        self.articles = {'A': [('retail', 'A retail incident.'), ('health', 'A hospital incident.'),
                              ('campus', 'A university incident.'), ('cloud', 'A cloud incident.'),
                              ('bank', 'A bank incident.')],
                         'B': [('college', 'A college incident.'), ('lms', 'An LMS incident.')]}
        self.args = SimpleNamespace(check_feeds=False, dry_run=False, per_source_limit=1,
                                    max_age_hours=48, sector_scope='education')
        stack = self.enterContext(ExitStack())
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(bot, 'ROOT', self.root))
        stack.enter_context(patch.dict(bot.os.environ, DISCORD_WEBHOOK_URL='fake', AI_PROVIDER='none'))
        stack.enter_context(patch.object(bot, 'robots_allowed', return_value=True))
        self.fetch = stack.enter_context(patch.object(bot, 'fetch', side_effect=self.get))
        self.ai = stack.enter_context(patch.object(bot, 'summarize', return_value=(None, 'No AI')))
        self.send = stack.enter_context(patch.object(bot, 'send_discord', return_value='message'))

    def get(self, url, *_):
        if url.endswith('/rss'):
            name = url.split('/')[-2]
            xml = '<rss><channel>'
            for index, (slug, _) in enumerate(self.articles[name]):
                stamp = datetime.fromtimestamp(self.current - 3600 * (index + 1), timezone.utc).isoformat()
                xml += f'<item><title>Incident {slug}</title><link>https://publisher.example/{slug}</link><pubDate>{stamp}</pubDate></item>'
            return 200, (xml + '</channel></rss>').encode(), {'ETag': name}, url
        slug = url.rsplit('/', 1)[-1]
        text = next(text for rows in self.articles.values() for name, text in rows if name == slug)
        body = '<article>' + ('No further details were provided about this incident. ' * 8) + text + '</article>'
        return 200, body.encode(), {'Content-Type': 'text/html'}, url

    def run_check(self):
        return bot.run(self.args, sources=self.sources)

    def titles(self):
        return [call.args[0]['title'] for call in self.send.call_args_list]

    def test_nonmatches_are_never_analyzed_or_sent_and_do_not_consume_limits(self):
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(set(self.titles()), {'Incident college', 'Incident campus'})
        self.assertEqual(self.ai.call_count, 2)
        # The campus keyword occurs after the excerpt, so full text must be used.
        campus = next(c.args[0] for c in self.send.call_args_list if c.args[0]['title'] == 'Incident campus')
        self.assertNotIn('university', campus['publisher_excerpt'])
        self.assertIn('university', campus['sector_matches']['education'])
        saved = json.loads((self.root / 'state/state.json').read_text())
        self.assertNotIn('https://publisher.example/retail', saved['seen'])
        self.assertIn('scope_excluded', saved['pending']['https://publisher.example/retail'])

    def test_same_scope_remembers_nonmatches_and_none_reconsiders_without_resending_successes(self):
        self.run_check()
        self.fetch.reset_mock()
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(set(self.titles()), {'Incident cloud', 'Incident lms'})
        fetched = [call.args[0] for call in self.fetch.call_args_list]
        self.assertNotIn('https://publisher.example/retail', fetched)
        self.args.sector_scope = ''
        self.send.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.titles(), ['Incident retail'])

    def test_selecting_another_scope_reconsiders_previously_excluded_articles(self):
        self.run_check()
        self.args.sector_scope = 'financial'
        self.send.reset_mock()
        self.ai.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.titles(), ['Incident bank'])
        self.ai.assert_called_once()

    def test_none_keeps_default_collection_without_filtering(self):
        self.args.sector_scope = ''
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(set(self.titles()), {'Incident retail', 'Incident college'})
        self.assertEqual(self.ai.call_count, 2)

    def test_dev_mode_repeats_only_matches_and_keeps_limit_and_window(self):
        self.run_check()
        self.args.test_mode = True
        self.send.reset_mock()
        self.ai.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(set(self.titles()), {'Incident college', 'Incident campus'})
        self.assertEqual(self.ai.call_count, 2)
        self.current -= 49 * 3600
        self.send.reset_mock()
        self.ai.reset_mock()
        self.assertEqual(self.run_check(), 0)
        self.send.assert_not_called()
        self.ai.assert_not_called()

    def test_preview_filters_without_posting_or_mutating_history(self):
        self.run_check()
        before = (self.root / 'state/state.json').read_bytes()
        self.args.dry_run = True
        self.args.test_mode = True
        self.send.reset_mock()
        self.run_check()
        self.assertEqual(len(list((self.root / 'preview').glob('*.json'))), 2)
        self.send.assert_not_called()
        self.assertEqual((self.root / 'state/state.json').read_bytes(), before)

    def test_cached_report_does_not_bypass_new_scope_or_repeat_ai(self):
        cached = {'title': 'University', 'sector_catalog': sectors.CATALOG_VERSION,
                  'sector_matches': {'education': ['university']}, 'ai_status': 'Cached', 'analysis': None}
        self.assertIsNone(bot.scoped_report(self.sources[0], {}, 'financial', cached))
        self.assertEqual(bot.scoped_report(self.sources[0], {}, 'education', cached)['ai_status'], 'Cached')
        self.fetch.assert_not_called()
        self.ai.assert_not_called()

    def test_ai_test_skips_nonmatches_before_generating(self):
        with patch.dict(bot.os.environ, AI_PROVIDER='gemini'):
            # Mock AI returns an excerpt, so generation test reports failure after
            # choosing the first matching article; unrelated pages never use AI.
            self.assertEqual(bot.test_ai(self.sources, 'A', 48, 'education'), 1)
        self.ai.assert_called_once()
        report = json.loads((self.root / 'preview/ai-test.json').read_text())
        self.assertEqual(report['title'], 'Incident campus')
        self.send.assert_not_called()

    def test_legacy_cached_report_is_rechecked_against_article_body_without_repeat_ai(self):
        cached = {'title': 'Old report title with university', 'analysis': None, 'ai_status': 'Cached'}
        entry = {'title': 'Retail incident', 'url': 'https://publisher.example/retail'}
        self.assertIsNone(bot.scoped_report(self.sources[0], entry, 'education', cached))
        entry.update(title='Campus incident', url='https://publisher.example/campus')
        report = bot.scoped_report(self.sources[0], entry, 'education', cached)
        self.assertEqual(report['ai_status'], 'Cached')
        self.assertIn('university', report['sector_matches']['education'])
        self.ai.assert_not_called()

    def test_cli_global_test_limit_counts_matches_instead_of_skipped_candidates(self):
        self.args.test_mode = True
        self.args.max_posts = 2
        self.args.per_source_limit = None
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(set(self.titles()), {'Incident college', 'Incident lms'})
        self.assertEqual(self.ai.call_count, 2)

    def test_server_scope_menu_and_multi_webhook_delivery_use_same_filter(self):
        server_settings.initialize(self.root)
        config, revision = server_settings.load_config(self.root)
        with patch('builtins.input', side_effect=['1', '1', '0']):
            setup.scope_menu(config)
        self.assertEqual(config['sector_scope'], 'education')
        config.update(sources=self.sources, per_source_limit=1, webhooks=[
            {'name': str(i), 'url': f'https://discord.com/api/webhooks/{i}/offline-test', 'enabled': True}
            for i in (123, 456)])
        server_settings.save_config(self.root, config, revision)
        self.assertEqual(server.run_action(self.root, 'new'), 0)
        self.assertEqual(len(self.titles()), 4)
        self.assertEqual(set(self.titles()), {'Incident campus', 'Incident college'})
        self.assertEqual(self.ai.call_count, 2)


if __name__ == '__main__':
    unittest.main()
