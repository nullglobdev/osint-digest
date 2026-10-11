"""Filter catalog, AND/OR semantics, persistence and real collection paths."""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from osint_digest.core import collector as bot, scopes, sectors
from osint_digest.server import app as server, settings, setup


class ScopeCatalogTests(unittest.TestCase):
    def test_all_is_default_for_seven_independent_scopes_and_every_alias_matches(self):
        self.assertEqual(len(scopes.CHOICES), 7)
        self.assertEqual(scopes.selection({}), scopes.DEFAULTS)
        for key, choices in scopes.CHOICES.items():
            self.assertEqual(choices[''], 'All')
        for key, catalog in scopes.CATALOGS.items():
            for option, (_, alternatives) in catalog.items():
                for rule in alternatives:
                    with self.subTest(key=key, option=option, rule=rule):
                        self.assertIn(option, scopes.classify(' ; '.join(rule))[key])

    def test_options_are_alternatives_but_scopes_are_intersections(self):
        selected = scopes.selection({'actor_scope': 'ransomware', 'social_scope': 'smishing'})
        for alias in ('ransomware gang', 'RaaS', 'ransomware-as-a-service'):
            self.assertTrue(scopes.matches(scopes.classify(alias + ' uses SMS phishing.'), selected))
        for text in ('A ransomware group incident.', 'SMS phishing hit users.'):
            self.assertFalse(scopes.matches(scopes.classify(text), selected))
        self.assertTrue(scopes.matches(scopes.classify('Unrelated text.'), scopes.DEFAULTS))

    def test_all_seven_filters_can_be_combined(self):
        selected = scopes.selection({'sector_scope': 'education', 'actor_scope': 'nation_state',
                                     'social_scope': 'phishing', 'access_scope': 'zero_day',
                                     'malware_scope': 'data_breach', 'other_scope': 'lateral_movement',
                                     'education_scope': 'university_phishing'})
        text = 'An APT used phishing and a 0-day at a university, followed by lateral movement and a data breach.'
        self.assertTrue(scopes.matches(scopes.classify(text), selected))
        self.assertFalse(scopes.matches(scopes.classify(text.replace('lateral movement', 'unknown activity')), selected))

    def test_education_combinations_require_both_concepts_in_any_order(self):
        selected = scopes.selection({'education_scope': 'university_phishing'})
        self.assertTrue(scopes.matches(scopes.classify('Phishing was reported after universities investigated an incident.'), selected))
        for text in ('A university incident.', 'A phishing incident at a bank.'):
            self.assertFalse(scopes.matches(scopes.classify(text), selected))
        selected['education_scope'] = 'lms_phishing'
        self.assertTrue(scopes.matches(scopes.classify('Phishing targeted Canvas users.'), selected))

    def test_boundaries_case_hyphens_and_explicit_context(self):
        matches = scopes.classify('An apt description of a rat. Relationship with a webmaster.')
        self.assertNotIn('nation_state', matches['actor_scope'])
        self.assertNotIn('rat', matches['malware_scope'])
        self.assertNotIn('web_shell', matches['access_scope'])
        self.assertIn('spear_phishing', scopes.classify('SPEAR-PHISHING targeted staff.')['social_scope'])
        self.assertIn('ai_phishing', scopes.classify('A deepfake video impersonated an executive.')['social_scope'])
        self.assertNotIn('ai_phishing', scopes.classify('An unrelated deepfake.')['social_scope'])
        self.assertIn('affiliate', scopes.classify('An affiliate distributed ransomware.')['actor_scope'])

    def test_signature_changes_with_any_selection_and_invalid_choices_are_rejected(self):
        self.assertEqual(scopes.signature(scopes.DEFAULTS), '')
        base = scopes.selection({'sector_scope': 'education'})
        for key in scopes.CATALOGS:
            changed = {**base, key: next(iter(scopes.CATALOGS[key]))}
            self.assertNotEqual(scopes.signature(base), scopes.signature(changed))
            for value in ('unknown', None, [], True):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    scopes.selection({key: value})

    def test_metadata_and_legacy_reader_fallback(self):
        selected = scopes.selection({'social_scope': 'phishing'})
        report = {'title': 'Unrelated title', 'filter_catalog': scopes.CATALOG_VERSION,
                  'filter_matches': scopes.classify('Phishing found deep in the body.')}
        self.assertTrue(scopes.report_matches(report, selected))
        self.assertFalse(scopes.report_matches(report, {'social_scope': 'vishing'}))
        self.assertTrue(scopes.report_matches({'title': 'Campus phishing'}, selected))
        self.assertFalse(scopes.report_matches({'title': 'Incident', 'analysis': 'bad'}, selected))
        legacy = {**report, 'filter_matches': None, 'sector_catalog': sectors.CATALOG_VERSION,
                  'sector_matches': {'education': ['university']}}
        self.assertTrue(scopes.report_matches(legacy, {'sector_scope': 'education'}))


class ScopeCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = {'name': 'Publisher', 'feed': 'https://publisher.example/rss', 'hosts': ['publisher.example']}
        self.published = datetime.now(timezone.utc).isoformat()
        self.bodies = [('actor-only', 'An APT campaign.'), ('social-only', 'A university phishing incident.'),
                       ('match', 'An APT used phishing at a university.'), ('second', 'A university reported APT phishing.')]
        self.args = SimpleNamespace(check_feeds=False, dry_run=False, max_age_hours=48, per_source_limit=1,
                                    sector_scope='education', actor_scope='nation_state', social_scope='phishing')
        stack = self.enterContext(ExitStack())
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(patch.object(bot, 'ROOT', self.root))
        stack.enter_context(patch.dict(bot.os.environ, AI_PROVIDER='none', DISCORD_WEBHOOK_URL='offline'))
        stack.enter_context(patch.object(bot, 'robots_allowed', return_value=True))
        self.fetch = stack.enter_context(patch.object(bot, 'fetch', side_effect=self.get))
        self.ai = stack.enter_context(patch.object(bot, 'summarize', return_value=(None, 'No AI')))
        self.send = stack.enter_context(patch.object(bot, 'send_discord', return_value='receipt'))

    def get(self, url, *_):
        if url.endswith('/rss'):
            raw = '<rss><channel>' + ''.join(f'<item><title>{name}</title><link>https://publisher.example/{index}</link><pubDate>{self.published}</pubDate></item>'
                                              for index, (name, _) in enumerate(self.bodies)) + '</channel></rss>'
            return 200, raw.encode(), {}, url
        text = self.bodies[int(url.rsplit('/', 1)[-1])][1]
        return 200, ('<article>' + 'No further details were available. ' * 12 + text + '</article>').encode(), {'Content-Type': 'text/html'}, url

    def run_check(self):
        return bot.run(self.args, sources=[self.source])

    def test_all_filters_before_ai_and_nonmatches_do_not_consume_source_limit(self):
        self.assertEqual(self.run_check(), 0)
        report = self.send.call_args.args[0]
        self.assertEqual(report['title'], 'match')
        self.assertEqual(report['filters']['actor_scope'], 'nation_state')
        self.assertNotIn('APT', report['publisher_excerpt'])
        self.assertIn('APT', report['filter_matches']['actor_scope']['nation_state'])
        self.ai.assert_called_once()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.send.call_args.args[0]['title'], 'second')
        self.assertEqual(self.send.call_count, 2)

    def test_change_one_scope_reconsiders_exclusions_without_repeating_deliveries(self):
        self.run_check()
        self.fetch.reset_mock()
        self.args.actor_scope = ''
        self.run_check()
        self.assertEqual(self.send.call_args.args[0]['title'], 'social-only')
        self.assertIn('https://publisher.example/1', [call.args[0] for call in self.fetch.call_args_list])
        for key in scopes.LABELS:
            setattr(self.args, key, '')
        self.run_check()
        self.assertEqual(self.send.call_args.args[0]['title'], 'actor-only')
        titles = [call.args[0]['title'] for call in self.send.call_args_list]
        self.assertEqual(titles.count('match'), 1)

    def test_new_filters_work_without_a_sector(self):
        self.args.sector_scope = ''
        self.args.social_scope = ''
        self.run_check()
        self.assertEqual(self.send.call_args.args[0]['title'], 'actor-only')

    def test_dev_preview_and_ai_test_keep_all_filters_and_history(self):
        self.run_check()
        before = (self.root / 'state/state.json').read_bytes()
        self.args.test_mode = True
        self.args.dry_run = True
        self.assertEqual(self.run_check(), 0)
        reports = list((self.root / 'preview').glob('*.json'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(json.loads(reports[0].read_text())['title'], 'match')
        self.assertEqual((self.root / 'state/state.json').read_bytes(), before)
        with patch.dict(bot.os.environ, AI_PROVIDER='gemini'):
            self.assertEqual(bot.test_ai([self.source], '*', 48, 'education', scopes.selection(self.args)), 1)
        self.assertEqual(json.loads((self.root / 'preview/ai-test.json').read_text())['title'], 'match')
        self.assertEqual(self.send.call_count, 1)

    def test_cached_report_rechecks_new_dimensions_without_regenerating_ai(self):
        entry = {'title': 'match', 'url': 'https://publisher.example/2', 'source': 'Publisher'}
        cached = {'title': 'Cached university', 'analysis': None, 'ai_status': 'Cached',
                  'sector_catalog': sectors.CATALOG_VERSION, 'sector_matches': {'education': ['university']}}
        selected = scopes.selection(self.args)
        report = bot.scoped_report(self.source, entry, 'education', cached, selected)
        self.assertEqual(report['ai_status'], 'Cached')
        self.ai.assert_not_called()
        self.fetch.reset_mock()
        self.assertIsNone(bot.scoped_report(self.source, entry, 'education', report, {**selected, 'social_scope': 'vishing'}))
        self.fetch.assert_not_called()
        self.ai.assert_not_called()

    def test_local_results_only_publish_matching_articles(self):
        self.args.local = True
        self.run_check()
        records = list((self.root / 'results').glob('*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())['title'], 'match')
        self.send.assert_not_called()

    def test_server_migration_menus_persistence_and_two_webhooks(self):
        settings.initialize(self.root)
        config, revision = settings.load_config(self.root)
        old = {key: value for key, value in config.items() if key not in scopes.CATALOGS}
        old.update(schema_version=4, sector_scope='education')
        settings.atomic_json(self.root / 'server.json', old)
        before = (self.root / 'server.json').read_bytes()
        config, revision = settings.load_config(self.root)
        self.assertEqual(config['sector_scope'], 'education')
        self.assertTrue(all(config[key] == '' for key in scopes.CATALOGS))
        self.assertEqual((self.root / 'server.json').read_bytes(), before)
        with patch('builtins.input', side_effect=['2', '3', '3', '1', '0']):
            setup.scope_menu(config)  # Actor: nation-state; Social: phishing.
        self.assertEqual(config['actor_scope'], 'nation_state')
        self.assertEqual(config['social_scope'], 'phishing')
        config.update(per_source_limit=1, sources=[self.source], webhooks=[
            {'name': str(i), 'url': f'https://discord.com/api/webhooks/{i}/offline', 'enabled': True} for i in (123, 456)])
        settings.save_config(self.root, config, revision)
        self.assertEqual(server.run_action(self.root, 'new'), 0)
        self.assertEqual([call.args[0]['title'] for call in self.send.call_args_list], ['match', 'match'])
        self.ai.assert_called_once()

    def test_cli_routes_independent_scopes_and_rejects_unknown_options(self):
        with patch.object(bot, 'load_env'), patch.object(bot, 'run', return_value=0) as run:
            with patch.object(bot.sys, 'argv', ['bot.py', '--actor-scope', 'nation_state', '--social-scope', 'phishing']):
                self.assertEqual(bot.main(), 0)
                self.assertEqual(run.call_args.args[0].actor_scope, 'nation_state')
                self.assertEqual(run.call_args.args[0].social_scope, 'phishing')
            run.reset_mock()
            with patch.object(bot.sys, 'argv', ['bot.py', '--actor-scope', 'unknown']), patch.object(bot.sys, 'stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    bot.main()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
