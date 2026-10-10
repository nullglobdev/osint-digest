import json
from importlib.util import find_spec
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from osint_digest.core import providers as ai
from osint_digest.desktop import settings as settings
from osint_digest.core.sources import make_source


class ModelTests(unittest.TestCase):
    def test_gemini_filters_capabilities_and_follows_pages(self):
        with patch.object(ai, 'get_json', side_effect=[
            {'models': [{'name': 'models/gemini-text', 'supportedGenerationMethods': ['generateContent']},
                        {'name': 'models/embedding', 'supportedGenerationMethods': ['embedContent']},
                        {'name': 'models/gemini-image', 'supportedGenerationMethods': ['generateContent']}],
             'nextPageToken': 'next page'},
            {'models': [{'name': 'models/gemini-other', 'supportedGenerationMethods': ['generateContent']}]}]) as get:
            self.assertEqual(ai.list_models('gemini', 'gemini-secret'), ['gemini-other', 'gemini-text'])
            self.assertIn('pageToken=next+page', get.call_args.args[0])
            self.assertEqual(get.call_args.args[1], {'x-goog-api-key': 'gemini-secret'})
            self.assertNotIn('secret', get.call_args.args[0])

    def test_openai_auth_and_text_filter(self):
        with patch.object(ai, 'get_json', return_value={'data': [{'id': x} for x in
                    ['gpt-test', 'gpt-test-audio', 'gpt-test-codex', 'gpt-test-pro', 'text-embedding-test', 'o3']]}) as get:
            self.assertEqual(ai.list_models('openai', 'openai-secret'), ['gpt-test', 'o3'])
            self.assertEqual(get.call_args.args, ('https://api.openai.com/v1/models',
                                                 {'Authorization': 'Bearer openai-secret'}))

    def test_claude_pagination_and_retired_models(self):
        with patch.object(ai, 'get_json', side_effect=[
            {'data': [{'id': 'claude-text'}, {'id': 'claude-old', 'lifecycle': 'retired'}],
             'has_more': True, 'last_id': 'claude-text'},
            {'data': [{'id': 'claude-next'}], 'has_more': False}]) as get:
            self.assertEqual(ai.list_models('anthropic', 'claude-secret'), ['claude-next', 'claude-text'])
            self.assertIn('after_id=claude-text', get.call_args.args[0])
            self.assertEqual(get.call_args.args[1]['x-api-key'], 'claude-secret')

    def test_local_models_send_no_auth_and_none_makes_no_request(self):
        with patch.object(ai, 'get_json', return_value={'models': [{'name': 'local:8b'}]}) as get:
            self.assertEqual(ai.list_models('ollama', 'must-not-send'), ['local:8b'])
            self.assertEqual(get.call_args.args, ('http://127.0.0.1:11434/api/tags', {}))
            get.reset_mock()
            self.assertEqual(ai.list_models('none'), [])
            get.assert_not_called()

    def test_discovery_never_redirects_credentials(self):
        self.assertIsNone(ai.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test'))


class SourceTests(unittest.TestCase):
    def test_feed_host_added_and_duplicates_rejected(self):
        source = make_source('Custom', 'https://feeds.example.com/rss', 'example.com, www.example.com', [])
        self.assertEqual(source['hosts'], ['feeds.example.com', 'example.com', 'www.example.com'])
        self.assertTrue(source['enabled'])
        with self.assertRaises(ValueError):
            make_source('custom', 'https://other.example.com/rss', '', [source])
        with self.assertRaises(ValueError):
            make_source('Other', source['feed'], '', [source])
        self.assertEqual(make_source('Custom', source['feed'], 'example.com', [source], editing=0)['name'], 'Custom')

    def test_invalid_urls_and_hosts(self):
        for url in ('http://example.com/rss', 'https://localhost/rss', 'https://127.0.0.1/rss',
                    'https://10.0.0.1/rss', 'https://name:pass@example.com/rss',
                    'https://example.com:444/rss', 'https://example.com/rss#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                make_source('Test', url, '', [])
        for host in ('*.example.com', 'localhost', '192.168.1.1', 'https://example.com', 'host.local'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                make_source('Test', 'https://example.com/rss', host, [])


@unittest.skipUnless(os.name == 'nt', 'Desktop targets Windows')
class SettingsTests(unittest.TestCase):
    def test_desktop_openai_and_claude_generate_grounded_summaries(self):
        from osint_digest.core import collector as bot
        article = 'The vendor recommends installing the security update immediately.'
        raw = json.dumps({'summary': [{'text': 'Install the update.', 'evidence': article}]})
        for provider, response, endpoint, auth in (
                ('openai', {'choices': [{'message': {'content': raw}}]}, 'api.openai.com', 'Authorization'),
                ('anthropic', {'content': [{'type': 'text', 'text': raw}]}, 'api.anthropic.com', 'x-api-key')):
            with self.subTest(provider=provider), patch.dict(os.environ), patch.object(bot, 'api_json', return_value=response) as api:
                settings.apply_environment({**settings.DEFAULTS, 'provider': provider, 'model': 'text-model', 'api_key': 'provider-secret'})
                result, status = bot.summarize(article)
                self.assertEqual(result['summary'][0]['evidence'], article)
                self.assertIn(provider, status)
                self.assertIn(endpoint, api.call_args.args[0])
                self.assertIn('provider-secret', api.call_args.args[2][auth])

    def test_legacy_gemini_migration_and_interval_cap_preserve_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings.atomic_json(root / 'settings.json', {'provider': 'gemini', 'model': 'gemini-saved',
                'gemini_key_protected': settings.protect('old-secret'),
                'webhook_protected': settings.protect('https://discord.com/api/webhooks/123/saved'),
                'interval_minutes': 720})
            loaded = settings.load_settings(root)
            self.assertEqual(loaded['api_key'], 'old-secret')
            self.assertEqual(loaded['model'], 'gemini-saved')
            self.assertEqual(loaded['interval_minutes'], 360)
            settings.save_settings(root, loaded)
            stored = (root / 'settings.json').read_text()
            self.assertNotIn('old-secret', stored)
            self.assertNotIn('gemini_key_protected', stored)
            self.assertEqual(settings.load_settings(root), loaded)

    def test_each_provider_uses_only_its_key_and_model(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ):
            root = Path(tmp)
            value = {**settings.DEFAULTS, 'provider': 'openai', 'api_key': 'openai-secret', 'model': 'gpt-test',
                     'profiles': {'gemini': {'api_key': 'gemini-secret', 'model': 'gemini-saved'},
                                  'anthropic': {'api_key': 'claude-secret', 'model': 'claude-saved'}}}
            settings.save_settings(root, value)
            loaded = settings.load_settings(root)
            settings.apply_environment(loaded)
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'openai-secret')
            self.assertEqual(os.environ['AI_MODEL'], 'gpt-test')
            self.assertEqual(os.environ['ALLOW_PAID_AI'], 'true')
            self.assertNotIn('GEMINI_API_KEY', os.environ)
            self.assertNotIn('ANTHROPIC_API_KEY', os.environ)
            for secret in ('gemini-secret', 'claude-secret', 'openai-secret'):
                self.assertNotIn(secret, (root / 'settings.json').read_text())
            self.assertEqual(loaded['profiles']['anthropic']['api_key'], 'claude-secret')

    def test_interval_boundaries(self):
        settings.validate({**settings.DEFAULTS, 'interval_minutes': 360})
        for value in (14, 361):
            with self.assertRaises(ValueError):
                settings.validate({**settings.DEFAULTS, 'interval_minutes': value})


if __name__ == '__main__':
    unittest.main()
