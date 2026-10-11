"""Isolated desktop worker; no credentials in command-line arguments or logs."""
import os
import sys
import urllib.request

from osint_digest.core import collector as bot
from osint_digest.core import scopes
from osint_digest.desktop.settings import initialize, load_settings, apply_environment

ACTIONS = ('feeds', 'ai', 'preview', 'test', 'test-preview', 'new', 'webhook')


class RedactedLog:
    def __init__(self, stream, secrets):
        self.stream = stream
        self.secrets = [s for s in secrets if s]

    def write(self, text):
        for secret in self.secrets:
            text = text.replace(secret, '[hidden]')
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()


def run_worker(root, action):
    initialize(root)
    with (root / 'activity.log').open('w', encoding='utf-8', buffering=1) as log:
        previous = sys.stdout, sys.stderr
        try:
            sys.stdout = sys.stderr = log
            settings = load_settings(root)
            secrets = [settings['webhook'], settings['api_key']]
            secrets.extend(profile.get('api_key', '') for profile in settings['profiles'].values())
            sys.stdout = sys.stderr = RedactedLog(log, secrets)
            apply_environment(settings)
            bot.ROOT = root
            if action not in ACTIONS:
                raise ValueError('Unknown action')
            if action in ('ai', 'preview', 'test', 'test-preview') and not settings['developer_mode']:
                print('Enable Dev mode in Preferences to use previews, AI tests, and repeat delivery.')
                return 1
            if action == 'webhook':
                if not settings['webhook']:
                    print('Add a Discord webhook in Connection first.')
                    return 1
                request = urllib.request.Request(settings['webhook'], headers={'User-Agent': bot.UA})
                with urllib.request.urlopen(request, timeout=20) as response:
                    if response.status != 200:
                        return 1
                print('Discord connection verified. No test message was sent.')
                return 0
            flags = {'feeds': ['--check-feeds'], 'ai': ['--test-ai'],
                     'preview': ['--dry-run'],
                     'test-preview': ['--test-mode', '--dry-run'],
                     'test': ['--test-mode'],
                     'new': []}[action]
            if action in ('new', 'test', 'preview', 'test-preview', 'ai'):
                hours = 48 if action == 'new' else settings['test_lookback_days'] * 24
                flags = [*flags, '--per-source-limit', str(settings['per_source_limit']), '--max-age-hours', str(hours)]
                for key, value in scopes.selection(settings).items():
                    if value:
                        flags = [*flags, '--' + key.replace('_', '-'), value]
            if action in ('new', 'test', 'preview', 'test-preview') and not settings['webhook']:
                flags = [*flags, '--local']
            old_args = sys.argv
            try:
                sys.argv = ['bot.py', *flags]
                return bot.main()
            finally:
                sys.argv = old_args
        except Exception as error:
            print('Task failed: ' + bot.error_label(error))
            print('Check your connection settings and try again. No credentials are included in this log.')
            return 1
        finally:
            sys.stdout, sys.stderr = previous
