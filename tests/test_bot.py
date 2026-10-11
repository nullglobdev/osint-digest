import json
import io
import contextlib
import csv
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from osint_digest.core import collector as bot
SOURCE = {'name': 'Test', 'hosts': ['publisher.example'], 'feed': 'https://publisher.example/feed'}


def feed(*names):
    items = ''.join(f'<item><title>{n}</title><link>https://publisher.example/{n}</link></item>' for n in names)
    return f'<rss><channel>{items}</channel></rss>'.encode()


class Tests(unittest.TestCase):
    def test_local_publishing_is_durable_deduplicated_and_separate_from_discord(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(check_feeds=False, dry_run=False, local=True)
            def report(source, entry):
                return bot.make_report(entry, 'Article text. ' * 30, 'HTML')
            with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL='', AI_PROVIDER='none'), patch.object(bot, 'fetch', return_value=(200, feed('one', 'two'), {}, '')), patch.object(bot, 'article_report', side_effect=report) as process, patch.object(bot, 'send_discord', return_value='discord-id') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args, sources=[SOURCE]), 0)
                self.assertEqual(len(list((root / 'results').glob('*.json'))), 2)
                self.assertFalse((root / 'state/state.json').exists())
                self.assertEqual(bot.run(args, sources=[SOURCE]), 0)
                self.assertEqual(process.call_count, 2)
                send.assert_not_called()
                local_history = (root / 'state/local-state.json').read_bytes()
                # Adding Discord later must not lose articles that were only saved locally.
                args.local = False
                with patch.dict(os.environ, DISCORD_WEBHOOK_URL='fake'):
                    self.assertEqual(bot.run(args, sources=[SOURCE]), 0)
                    self.assertEqual(send.call_count, 2)
                self.assertEqual((root / 'state/local-state.json').read_bytes(), local_history)
            for path in (root / 'results').glob('*.json'):
                saved = json.loads(path.read_text())
                self.assertEqual(saved['delivery'], 'local')
                self.assertIn('saved_at', saved)
            self.assertFalse(list((root / 'results').glob('*.tmp')))

    def test_failed_local_write_is_retried_without_recording_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(check_feeds=False, dry_run=False, local=True)
            with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL=''), patch.object(bot, 'fetch', return_value=(200, feed('one'), {}, '')), patch.object(bot, 'article_report', return_value={'ai_status': '', 'analysis': None}), patch.object(bot, 'publish_local', side_effect=OSError), patch.object(bot, 'send_discord') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args, sources=[SOURCE]), 1)
                send.assert_not_called()
            state = json.loads((root / 'state/local-state.json').read_text())
            self.assertEqual(state['seen'], {})
            self.assertEqual(len(state['pending']), 1)
            self.assertIn('retry_after', next(iter(state['pending'].values())))

    def test_local_preview_does_not_publish_or_mark_articles_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(check_feeds=False, dry_run=True, local=True)
            with patch.object(bot, 'ROOT', root), patch.dict(os.environ, AI_PROVIDER='none'), patch.object(bot, 'fetch', return_value=(200, feed('one'), {}, '')), patch.object(bot, 'article_report', side_effect=lambda source, entry: bot.make_report(entry, 'Article text. ' * 30, 'HTML')), patch.object(bot, 'send_discord') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args, sources=[SOURCE]), 0)
                send.assert_not_called()
            self.assertFalse((root / 'results').exists())
            self.assertFalse((root / 'state/local-state.json').exists())
            self.assertEqual(len(list((root / 'preview').glob('*.json'))), 1)

    def test_normal_run_checks_every_source_sends_all_unsent_and_remembers_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [SOURCE, {**SOURCE, 'name': 'Other', 'feed': SOURCE['feed'] + '2'},
                       {**SOURCE, 'name': 'Disabled', 'enabled': False}]
            args = SimpleNamespace(check_feeds=False, dry_run=False)
            raw = [feed(*(f'a{i}' for i in range(8))), feed('a0', *(f'b{i}' for i in range(8)))]
            def get(url, hosts, headers):
                return 200, raw[0 if url == SOURCE['feed'] else 1], {'ETag': 'cached'}, url
            with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL='fake', MAX_POSTS='1'), patch.object(bot, 'fetch', side_effect=get) as fetch, patch.object(bot, 'article_report', return_value={'ai_status': 'No AI', 'analysis': None}), patch.object(bot, 'send_discord', return_value='message') as send, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args, sources=sources), 0)
                self.assertEqual(fetch.call_count, 2)
                self.assertEqual(send.call_count, 16)  # No five-post cap; shared URL sent once.
                self.assertEqual(bot.run(args, sources=sources), 0)  # Reload history from disk.
                self.assertEqual(fetch.call_count, 4)
                self.assertEqual(send.call_count, 16)
                raw[1] = feed('new', 'a0')
                self.assertEqual(bot.run(args, sources=sources), 0)
                self.assertEqual(fetch.call_count, 6)
                self.assertEqual(send.call_count, 17)
            saved = json.loads((root / 'state/state.json').read_text())
            self.assertEqual(len(saved['seen']), 17)
            self.assertFalse(saved['pending'])

    def test_legacy_baseline_is_rechecked_but_confirmed_sent_articles_are_skipped(self):
        state = {'feeds': {'Test': {'initialized': True, 'etag': 'old', 'modified': 'old'}},
                 'seen': {'https://publisher.example/baseline': {'status': 'baseline'},
                          'https://publisher.example/sent': {'status': 'sent'}}, 'pending': {}}
        with patch.object(bot, 'fetch', return_value=(200, feed('baseline', 'sent'), {'ETag': 'new'}, '')) as fetch:
            self.assertEqual(bot.discover(SOURCE, state), 1)
            self.assertEqual(fetch.call_args.args[2], {})
        self.assertEqual(list(state['pending']), ['https://publisher.example/baseline'])
        with patch.object(bot, 'fetch', return_value=(304, b'', {}, '')) as fetch:
            self.assertEqual(bot.discover(SOURCE, state), 0)
            self.assertEqual(fetch.call_args.args[2], {'If-None-Match': 'new'})

    def test_failed_source_does_not_prevent_later_sources_or_due_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = lambda name: {'url': 'https://publisher.example/' + name, 'source': 'Test',
                                 'title': name, 'published': '', 'discovered': name}
            entries = [item('sent'), item('retry'), {**item('later'), 'retry_after': 99999999999}]
            bot.save_state(root / 'state/state.json', {'feeds': {},
                'seen': {entries[0]['url']: {'status': 'sent'}}, 'pending': {x['url']: x for x in entries}})
            args = SimpleNamespace(check_feeds=False, dry_run=False)
            sources = [SOURCE, {**SOURCE, 'name': 'Other', 'feed': SOURCE['feed'] + '2'}]
            with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL='fake'), patch.object(bot, 'fetch', side_effect=[TimeoutError, (200, feed('fresh'), {}, '')]) as fetch, patch.object(bot, 'article_report', return_value={'ai_status': 'No AI', 'analysis': None}) as report, patch.object(bot, 'send_discord', return_value='message'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args, sources=sources), 1)
                self.assertEqual(fetch.call_count, 2)
                self.assertEqual({call.args[1]['title'] for call in report.call_args_list}, {'retry', 'fresh'})
            saved = json.loads((root / 'state/state.json').read_text())
            self.assertEqual(list(saved['pending']), ['https://publisher.example/later'])

    def test_limited_test_with_one_source_records_success_without_queuing_failures(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = {'feeds': {}, 'seen': {}, 'pending': {}}
                bot.save_state(root / 'state/state.json', state)
                before = (root / 'state/state.json').read_bytes()
                args = SimpleNamespace(check_feeds=False, dry_run=dry_run, test_mode=True, max_posts=3)
                def report(source, entry):
                    return bot.make_report(entry, 'Article text. ' * 30, 'HTML')
                with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL='fake', AI_PROVIDER='none'), patch.object(bot, 'fetch', return_value=(200, feed('one', 'two', 'three', 'four'), {}, '')), patch.object(bot, 'article_report', side_effect=report) as process, patch.object(bot, 'send_discord', side_effect=[TimeoutError, 'two', 'three']) as send, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(bot.run(args, sources=[SOURCE]), 0 if dry_run else 1)
                    self.assertEqual(process.call_count, 3)
                    self.assertEqual(send.call_count, 0 if dry_run else 3)
                after = json.loads((root / 'state/state.json').read_text())
                self.assertFalse(after['pending'])
                self.assertFalse(after['feeds'])
                if dry_run:
                    self.assertEqual((root / 'state/state.json').read_bytes(), before)
                else:
                    self.assertEqual(set(after['seen']), {'https://publisher.example/two', 'https://publisher.example/three'})
                    # The next normal run sends only the two remaining unsent articles.
                    with patch.object(bot, 'ROOT', root), patch.dict(os.environ, DISCORD_WEBHOOK_URL='fake', AI_PROVIDER='none'), patch.object(bot, 'fetch', return_value=(200, feed('one', 'two', 'three', 'four'), {}, '')), patch.object(bot, 'article_report', side_effect=report), patch.object(bot, 'send_discord', return_value='normal') as send, contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(bot.run(SimpleNamespace(check_feeds=False, dry_run=False), sources=[SOURCE]), 0)
                        self.assertEqual({call.args[0]['title'] for call in send.call_args_list}, {'one', 'four'})

    def test_cli_requires_explicit_mode_for_limits_and_ignores_legacy_env_cap(self):
        for flags in (['--batch', '5'], ['--max-posts', '5'], ['--test-mode', '--max-posts', '0'],
                      ['--test-mode', '--check-feeds'], ['--test-mode', '--batch', '2', '--max-posts', '3']):
            with self.subTest(flags=flags), patch.object(bot, 'load_env'), patch.object(bot.sys, 'argv', ['bot.py', *flags]), patch.object(bot, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    bot.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, 'ROOT', Path(tmp)), patch.object(bot, 'load_env'), patch.dict(os.environ, MAX_POSTS='1'), patch.object(bot, 'run', return_value=0) as run:
            with patch.object(bot.sys, 'argv', ['bot.py']):
                self.assertEqual(bot.main(), 0)
                self.assertIsNone(run.call_args.args[0].max_posts)
                self.assertFalse(run.call_args.args[0].test_mode)
            with patch.object(bot.sys, 'argv', ['bot.py', '--test-mode', '--max-posts', '10']):
                self.assertEqual(bot.main(), 0)
                self.assertEqual(run.call_args.args[0].max_posts, 10)
                self.assertTrue(run.call_args.args[0].test_mode)

    def test_repository_sources_are_loaded_from_config_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'config').mkdir()
            (root / 'config/sources.json').write_text(json.dumps([SOURCE]))
            args = type('Args', (), {'test_ai': None, 'check_feeds': True})()
            with patch.object(bot, 'ROOT', root), patch.object(bot, 'fetch', return_value=(200, feed('one'), {}, '')) as fetch, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args), 0)
                self.assertEqual(fetch.call_args.args, (SOURCE['feed'], SOURCE['hosts']))

    def test_discovery_queues_all_unsent_and_keeps_backlog(self):
        state = {'feeds': {}, 'seen': {}, 'pending': {}}
        def get(raw):
            return lambda *a: (200, raw, {'ETag': 'test'}, '')
        self.assertEqual(bot.discover(SOURCE, state, get(feed('old'))), 1)
        state['seen']['https://publisher.example/old'] = {'status': 'sent'}
        state['pending'].clear()
        self.assertEqual(bot.discover(SOURCE, state, get(feed('new', 'old'))), 1)
        self.assertEqual(bot.discover(SOURCE, state, get(feed('new', 'old'))), 0)
        bot.discover(SOURCE, state, get(feed('newer')))
        self.assertIn('https://publisher.example/new', state['pending'])
        bot.discover(SOURCE, state, lambda *a: (304, b'', {}, ''))
        self.assertEqual(len(state['pending']), 2)

    def test_failed_feed_does_not_seed_or_cache(self):
        state = {'feeds': {}, 'seen': {}, 'pending': {}}
        with self.assertRaises(ValueError):
            bot.discover(SOURCE, state, lambda *a: (200, b'<html/>', {'ETag': 'bad'}, ''))
        self.assertFalse(state['feeds']['Test'].get('initialized'))
        self.assertFalse(state['seen'])

    def test_iocs_defanging_and_invalid_ip(self):
        text = 'C2 hxxps://evil[.]example/path and 203[.]0[.]113[.]8; bad 999.2.3.4; IPv6 2001:db8::1 SHA256 ' + 'a'*64
        iocs, capped = bot.extract_iocs(text)
        values = {x['value'] for x in iocs}
        self.assertIn('https://evil.example/path', values)
        self.assertIn('203.0.113.8', values)
        self.assertIn('2001:db8::1', values)
        self.assertNotIn('999.2.3.4', values)
        self.assertIn('a'*64, values)
        self.assertFalse(capped)

    def test_html_table_and_script(self):
        html = '<nav>junk.example</nav><article><p>' + 'Article content. '*25 + '</p><table><tr><td>8.8.8.8</td><td>test</td></tr></table><script>secret.example</script></article>'
        text, scope = bot.text_from_html(html)
        self.assertEqual(scope, 'article')
        self.assertIn('8.8.8.8', text)
        self.assertNotIn('secret.example', text)
        self.assertNotIn('junk.example', text)

    def test_ai_evidence_missing_is_rejected(self):
        with self.assertRaises(ValueError):
            bot.grounded_output(json.dumps({'summary':[{'text':'Invented', 'evidence':'not present anywhere'}]}), 'actual article')
        result = bot.grounded_output(json.dumps({'summary':[{'text':'Summary', 'evidence':'actual article'}], 'actors':[{'text':'Made up','evidence':'unsupported text'}]}), 'actual article')
        self.assertEqual(result['actors'], [])

    def test_recommendation_cards_are_not_article_body(self):
        html = '<main><div class="entry-content"><p>' + 'Real research and findings. '*30 + '</p></div><article>' + 'Unrelated product news. '*30 + '</article></main>'
        text, scope = bot.text_from_html(html)
        self.assertEqual(scope, 'content container')
        self.assertIn('Real research', text)
        self.assertNotIn('Unrelated', text)

    def test_ai_failure_falls_back(self):
        with patch.dict(os.environ, {'AI_PROVIDER':'gemini', 'GEMINI_API_KEY':'fake'}), patch('osint_digest.core.collector.api_json', side_effect=TimeoutError):
            result, status = bot.summarize('article')
        self.assertIsNone(result)
        self.assertIn('TimeoutError', status)

    def test_ai_test_ignores_history_without_sending_or_modifying_state(self):
        article = 'Researchers observed phishing targeting corporate email accounts. ' * 12
        ai_response = json.dumps({'summary': [{'text': 'A phishing campaign targets email accounts.',
                                              'evidence': 'phishing targeting corporate email accounts'}]})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sources.json').write_text(json.dumps([SOURCE]))
            bot.save_state(root / 'state/state.json', {'feeds': {'Test': {'initialized': True}},
                           'seen': {'https://publisher.example/old': {'status': 'sent'}}, 'pending': {}})
            original = (root / 'state/state.json').read_bytes()
            args = type('Args', (), {'test_ai': 'Test'})()
            with patch('osint_digest.core.collector.ROOT', root), patch.dict(os.environ, {'AI_PROVIDER': 'gemini', 'AI_MODEL': '', 'GEMINI_API_KEY': 'fake'}), patch('osint_digest.core.collector.fetch', side_effect=[
                (200, feed('old'), {}, ''),
                (200, ('<article>' + article + '</article>').encode(), {'Content-Type': 'text/html'}, '')
            ]), patch('osint_digest.core.collector.robots_allowed', return_value=True), patch('osint_digest.core.collector.api_json', return_value={
                'candidates': [{'content': {'parts': [{'text': ai_response}]}}]
            }) as api, patch('osint_digest.core.collector.send_discord') as send, patch('osint_digest.core.collector.discover') as discover, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bot.run(args), 0)
                api.assert_called_once()
                self.assertIn('gemini-3.1-flash-lite', api.call_args.args[0])
                send.assert_not_called()
                discover.assert_not_called()
            self.assertEqual((root / 'state/state.json').read_bytes(), original)
            report = json.loads((root / 'preview/ai-test.json').read_text())
            self.assertEqual(report['analysis']['summary'][0]['text'], 'A phishing campaign targets email accounts.')
            self.assertIn('Evidence:', (root / 'preview/ai-test.txt').read_text())

    def test_ai_test_reports_fallback_as_failure_and_redacts_errors(self):
        error = bot.urllib.error.HTTPError('https://example.test/secret', 429, 'private API key', {}, None)
        with patch.dict(os.environ, {'AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'fake'}), patch('osint_digest.core.collector.api_json', side_effect=error):
            summary, status = bot.summarize('article')
        self.assertIsNone(summary)
        self.assertIn('HTTP 429', status)
        self.assertNotIn('secret', status)
        self.assertNotIn('private', status)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('osint_digest.core.collector.ROOT', Path(tmp)), patch.dict(os.environ, {'AI_PROVIDER': 'gemini'}), patch('osint_digest.core.collector.fetch', return_value=(200, feed('old'), {}, '')), patch('osint_digest.core.collector.article_report', return_value={
                'title': 'Test', 'url': 'https://publisher.example/old', 'analysis': None, 'ai_status': status
            }), patch('osint_digest.core.collector.send_discord') as send, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(bot.test_ai([SOURCE], 'Test'), 1)
                self.assertIn('AI TEST FAILED', output.getvalue())
                send.assert_not_called()

    def test_ai_test_rejects_missing_provider_or_unknown_source_before_network(self):
        with patch.dict(os.environ, {'AI_PROVIDER': ''}), patch('osint_digest.core.collector.fetch') as fetch, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bot.test_ai([SOURCE], '*'), 1)
            fetch.assert_not_called()
        with patch.dict(os.environ, {'AI_PROVIDER': 'gemini'}), patch('osint_digest.core.collector.fetch') as fetch, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(bot.test_ai([SOURCE], 'Unknown'), 1)
            fetch.assert_not_called()

    def test_paid_ai_is_opt_in(self):
        with patch.dict(os.environ, {'AI_PROVIDER':'openai', 'ALLOW_PAID_AI':'false'}), patch('osint_digest.core.collector.api_json') as api:
            result, _ = bot.summarize('article')
        self.assertIsNone(result)
        api.assert_not_called()

    def test_batch_limits_resends_and_preserves_unrelated_queue(self):
        for count, dry_run, fail_first in [(5, False, False), (10, False, False),
                                           (5, True, False), (5, False, True)]:
            with self.subTest(count=count, dry_run=dry_run, fail_first=fail_first), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sources = [{**SOURCE, 'name': f'Source{i}', 'feed': f'https://publisher.example/feed{i}'} for i in range(10)]
                (root / 'sources.json').write_text(json.dumps([{**SOURCE, 'enabled': False}] + sources))
                unrelated = {'url': 'https://publisher.example/unrelated', 'source': 'Source0',
                             'title': 'Unrelated', 'published': 'now', 'discovered': 'old', 'retry_after': 99999999999}
                state = {'feeds': {'Source0': {'initialized': True, 'etag': 'keep'}},
                         'seen': {f'https://publisher.example/item{i}': {'status': 'sent', 'message_id': 'old'} for i in range(10)},
                         'pending': {unrelated['url']: unrelated}}
                bot.save_state(root / 'state/state.json', state)
                before = (root / 'state/state.json').read_bytes()
                args = type('Args', (), dict(test_ai=None, check_feeds=False, dry_run=dry_run,
                                             test_mode=True, max_posts=count))()
                def get_feed(url, hosts):
                    return 200, feed('item' + url.rsplit('feed', 1)[1]), {}, url
                def report(source, entry):
                    return bot.make_report(entry, 'Article text. '*30, 'HTML')
                calls = 0
                def send_report(report):
                    nonlocal calls
                    calls += 1
                    if fail_first and calls == 1:
                        raise TimeoutError
                    return str(calls)
                with patch('osint_digest.core.collector.ROOT', root), patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'fake', 'AI_PROVIDER': 'none'}), patch('osint_digest.core.collector.fetch', side_effect=get_feed) as fetch, patch('osint_digest.core.collector.article_report', side_effect=report) as process, patch('osint_digest.core.collector.send_discord', side_effect=send_report) as send, patch('osint_digest.core.collector.discover') as discover, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(bot.run(args), int(fail_first))
                    self.assertEqual(fetch.call_count, 10)
                    self.assertEqual(process.call_count, count)
                    self.assertEqual(send.call_count, 0 if dry_run else count)
                    discover.assert_not_called()
                after = json.loads((root / 'state/state.json').read_text())
                self.assertEqual(after['feeds'], state['feeds'])
                self.assertEqual(after['pending'][unrelated['url']], unrelated)
                if dry_run:
                    self.assertEqual((root / 'state/state.json').read_bytes(), before)
                    self.assertEqual(len(list((root / 'preview').glob('*.json'))), count)
                else:
                    self.assertEqual(len(after['pending']), 1)
                    for i in range(count):
                        sent = after['seen'][f'https://publisher.example/item{i}']
                        self.assertEqual(sent['message_id'], 'old' if fail_first and i == 0 else str(i + 1))

    def test_repeat_batch_requires_explicit_test_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'sources.json').write_text(json.dumps([SOURCE]))
            args = type('Args', (), dict(test_ai=None, check_feeds=False, dry_run=True, batch=5))()
            with patch('osint_digest.core.collector.ROOT', root), patch('osint_digest.core.collector.fetch') as fetch, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, '--test-mode'):
                    bot.run(args)
                fetch.assert_not_called()
            self.assertFalse((root / 'state/state.json').exists())

    def test_windows_console_does_not_fail_on_publisher_unicode(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_bytes = io.BytesIO()
            output = io.TextIOWrapper(output_bytes, encoding='ascii', errors='strict')
            def run(args):
                print('POSTED: \u2192 \U0001f512')
                return 0
            with patch('osint_digest.core.collector.ROOT', Path(tmp)), patch('osint_digest.core.collector.load_env'), patch('osint_digest.core.collector.sys.argv', ['bot.py']), patch('osint_digest.core.collector.sys.stdout', output), patch('osint_digest.core.collector.run', side_effect=run):
                self.assertEqual(bot.main(), 0)
                output.flush()
                self.assertIn(b'POSTED:', output_bytes.getvalue())

    def test_url_allowlist_and_xml_entities(self):
        self.assertFalse(bot.allowed('https://publisher.example.evil.com/a', SOURCE['hosts']))
        self.assertFalse(bot.allowed('http://publisher.example/a', SOURCE['hosts']))
        with self.assertRaises(ValueError):
            bot.parse_feed(b'<!DOCTYPE rss [<!ENTITY x "hi">]><rss/>', SOURCE)
        self.assertEqual(bot.canonical('https://publisher.example/a?utm_source=x&id=1#top'), 'https://publisher.example/a?id=1')

    def test_discord_limits_and_mentions(self):
        r = {'title':'test','url':'https://publisher.example/a','source':'Test','published':'now',
             'analysis':{k:[{'text':'x'*350}]*4 for k in bot.SECTIONS}, 'publisher_excerpt':'',
             'iocs':[], 'ioc_limit_reached':False, 'cves':[], 'attack_ids':[], 'coverage':'HTML', 'ai_status':'test'}
        p = bot.message_payload(r)
        fields = p['embeds'][0]['fields']
        self.assertTrue(all(len(f['value']) <= 1024 for f in fields))
        self.assertLess(sum(len(f['value']) + len(f['name']) for f in fields)+300, 6000)
        self.assertEqual(p['allowed_mentions'], {'parse':[]})

    def test_defanging_is_limited_to_indicator_values(self):
        prose = 'Upgrade to version 10.1.20. Review T1059.001 and run setup.exe.'
        indicators = [('domain', 'evil[.]example'), ('ipv4', '203.0.113.8'),
                      ('url', 'https://evil.example/payload.exe'), ('email', 'user@evil.example'),
                      ('sha256', 'a' * 64)]
        report = {'title': prose, 'url': 'https://publisher.example/article', 'source': 'Test',
                  'published': '2026-10-07T22:00:16Z', 'publisher_excerpt': prose,
                  'analysis': {k: [{'text': prose}] for k in bot.SECTIONS},
                  'cves': [], 'attack_ids': ['T1059.001'], 'ioc_limit_reached': False,
                  'iocs': [{'type': kind, 'value': value, 'evidence': prose, 'assessment': 'candidate'}
                           for kind, value in indicators]}
        payload = bot.message_payload(report)
        fields = {f['name']: f['value'] for f in payload['embeds'][0]['fields']}
        self.assertEqual(fields['Summary'], '\u2022 ' + prose)
        self.assertEqual(payload['embeds'][0]['url'], report['url'])
        preview = fields['IOC candidates (5)']
        for value in ('evil[.]example', '203[.]0[.]113[.]8', 'hxxps://evil[.]example/payload[.]exe', 'a' * 64):
            self.assertIn(value, preview)
        self.assertIn('user[@]evil[.]example', preview.replace('\u200b', ''))
        self.assertNotIn('[[.]]', preview)
        report['analysis'] = None
        excerpt = bot.message_payload(report)['embeds'][0]['fields'][0]['value']
        self.assertEqual(excerpt, prose)
        rows = list(csv.DictReader(io.StringIO(bot.csv_bytes(report).decode('utf-8-sig'))))
        self.assertTrue(all(row['evidence'] == prose for row in rows))
        self.assertEqual(rows[0]['defanged_value'], 'evil[.]example')

    def test_delivery_failure_preserves_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'sources.json').write_text(json.dumps([SOURCE]))
            state = {'feeds': {'Test': {'initialized':True}}, 'seen':{}, 'pending':{
                'https://publisher.example/a': {'url':'https://publisher.example/a','source':'Test','title':'A','published':'now','discovered':'now'}}}
            bot.save_state(root/'state/state.json', state)
            args = type('Args', (), dict(check_feeds=False,dry_run=False))()
            with patch('osint_digest.core.collector.ROOT',root), patch.dict(os.environ, {'DISCORD_WEBHOOK_URL':'fake','AI_PROVIDER':'none'}), patch('osint_digest.core.collector.discover',return_value=0), patch('osint_digest.core.collector.robots_allowed',return_value=True), patch('osint_digest.core.collector.fetch',return_value=(200,b'<article>'+b'Hello world. '*50+b'</article>',{'Content-Type':'text/html'},'')), patch('osint_digest.core.collector.send_discord',side_effect=TimeoutError):
                self.assertEqual(bot.run(args),1)
            after = json.loads((root/'state/state.json').read_text())
            self.assertFalse(after['seen'])
            self.assertEqual(len(after['pending']),1)
            self.assertEqual(next(iter(after['pending'].values()))['attempts'],1)

    def test_publication_dates(self):
        rss = bot.publication_time('Wed, 07 Oct 2026 22:00:16 +0000')
        self.assertEqual(rss, bot.publication_time('2026-10-07T18:00:16-04:00'))
        self.assertEqual(rss, bot.publication_time('2026-10-07T22:00:16Z'))
        self.assertTrue(rss.startswith('<t:'))
        self.assertEqual(bot.publication_time('Not provided'), 'Not provided')
        self.assertIn('timezone unspecified', bot.publication_time('2026-10-07T22:00:16'))

    def test_discord_presentation_and_json_delivery(self):
        report = {'title': 'x'*250, 'url': 'https://publisher.example/a',
                  'source': 'x'*100, 'published': '2026-10-07T22:00:16Z',
                  'analysis': {k: [{'text': 'x'*350}]*4 for k in bot.SECTIONS},
                  'publisher_excerpt': '', 'coverage': 'x'*500, 'ai_status': 'x'*500,
                  'cves': ['cve-2026-1234', 'CVE-2026-1234'] + [f'CVE-2026-{i}' for i in range(10000, 10100)],
                  'attack_ids': ['T1059.001', 't1059.001'],
                  'iocs': [{'type': 'domain', 'value': 'evil[.]example'}]*100,
                  'ioc_limit_reached': False}
        payload = bot.message_payload(report)
        fields = {f['name']: f['value'] for f in payload['embeds'][0]['fields']}
        self.assertIn('/T1059/001/', fields['MITRE ATT&CK'])
        self.assertNotIn('[.]', fields['MITRE ATT&CK'])
        self.assertEqual(fields['MITRE ATT&CK'].count('[T1059.001]'), 1)
        self.assertIn('||', fields['IOC candidates (100)'])
        self.assertIn('Showing 6 of 100', fields['IOC candidates (100)'])
        self.assertNotIn('Full CSV attached', json.dumps(payload))
        self.assertTrue(all(len(v) <= 1024 for v in fields.values()))
        embed = payload['embeds'][0]
        total = len(embed['title']) + len(embed['author']['name']) + len(embed['footer']['text'])
        total += sum(len(k) + len(v) for k, v in fields.items())
        self.assertLessEqual(total, 6000)
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/123/fake'}), patch('osint_digest.core.collector.urllib.request.urlopen', return_value=io.BytesIO(b'{"id":"123"}')) as send:
            self.assertEqual(bot.send_discord(report), '123')
        request = send.call_args.args[0]
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.get_header('User-agent'), bot.UA)
        self.assertNotIn('attachments', json.loads(request.data))


if __name__ == '__main__':
    unittest.main()
