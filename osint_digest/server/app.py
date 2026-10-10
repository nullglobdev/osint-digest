#!/usr/bin/env python3
"""Headless OSINT Digest service and terminal administration commands."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import tarfile
import threading
import time
import urllib.request

from osint_digest.core import collector as bot
from osint_digest.core.providers import NoRedirect
from osint_digest.server.settings import (BusyError, SettingsError, atomic_json, configured_environment,
                             file_lock, initialize, load_config, require_ready)

ACTIONS = ('check-feeds', 'test-ai', 'preview', 'batch', 'new', 'test-discord')


def utc(timestamp=None):
    return datetime.fromtimestamp(timestamp or time.time(), timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def log(text):
    print(f'[{utc()}] {text}', flush=True)


class RedactedStream:
    def __init__(self, stream, config):
        self.stream = stream
        self.secrets = [config['webhook'], *(p.get('api_key', '') for p in config['profiles'].values())]

    def write(self, text):
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, '[hidden]')
        return self.stream.write(text)

    def flush(self):
        self.stream.flush()


def run_action(root, action, count=None, source='*', stop=None, *, test_mode=False):
    if action not in ACTIONS:
        raise SettingsError('Unknown collector action.')
    if (count is not None or action == 'batch') and not test_mode:
        raise SettingsError('Limited or repeat articles require --test-mode. Use new for all unsent articles.')
    if test_mode and action not in ('new', 'batch', 'preview'):
        raise SettingsError('Test mode applies only to new, preview, or batch.')
    stop = stop or threading.Event()
    # Shares the collector lock with other server commands using this volume.
    with file_lock(root / '.run.lock'):
        config, _ = load_config(root)
        require_ready(config, action)
        count = (config['max_posts'] if count is None else count) if test_mode else None
        if count is not None and not 1 <= count <= 20:
            raise SettingsError('Article count must be between 1 and 20.')
        previous_root = bot.ROOT
        try:
            bot.ROOT = root
            bot.ROBOTS.clear()
            with configured_environment(config), redirect_stdout(RedactedStream(sys.stdout, config)), redirect_stderr(RedactedStream(sys.stderr, config)):
                log('Starting ' + action)
                if action == 'test-discord':
                    request = urllib.request.Request(config['webhook'], headers={'User-Agent': bot.UA})
                    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
                        code = int(response.status != 200)
                    print('Discord connection verified. No message sent.' if not code else 'Discord check failed.')
                else:
                    args = argparse.Namespace(check_feeds=action == 'check-feeds',
                        test_ai=source if action == 'test-ai' else None, dry_run=action == 'preview',
                        test_mode=test_mode, max_posts=count)
                    code = bot.run(args, sources=config['sources'], stop_requested=stop.is_set)
                atomic_json(root / 'last-run.json', {'action': action, 'test_mode': test_mode, 'finished_at': utc(),
                                                     'exit_code': code, 'stopped': stop.is_set()})
                log(f'{action} finished with exit code {code}.')
                return code
        finally:
            bot.ROOT = previous_root


class Heartbeat:
    """Liveness continues during a slow provider request; it is not delivery success."""
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.state = {'phase': 'starting', 'started_at': utc(), 'next_check': None}
        self.thread = threading.Thread(target=self._run, daemon=True)

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            atomic_json(self.root / 'runtime.json', {**self.state, 'heartbeat': time.time()})

    def _run(self):
        while not self.done.wait(10):
            try:
                self.update()
            except OSError:
                # A stale heartbeat marks the container unhealthy if storage fails.
                pass

    def __enter__(self):
        self.update()
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.done.set()
        self.thread.join(timeout=2)
        self.update(phase='stopped', next_check=None)


def serve(root, stop):
    with file_lock(root / '.service.lock'), Heartbeat(root) as status:
        log('Headless service started. Use the settings command to configure or pause checks.')
        revision, old_config = None, None
        last_finished, next_due = None, 0
        last_error = None
        while not stop.is_set():
            try:
                config, current = load_config(root)
                if config['enabled']:
                    require_ready(config)
                if current != revision:
                    if old_config is None or not old_config['enabled']:
                        next_due = 0
                    elif old_config['interval_minutes'] != config['interval_minutes'] and last_finished is not None:
                        next_due = last_finished + config['interval_minutes'] * 60
                    revision, old_config = current, deepcopy(config)
                    log(f"Settings loaded: automatic checks {'on' if config['enabled'] else 'paused'}; interval {config['interval_minutes']} minutes.")
                last_error = None
                if not config['enabled']:
                    status.update(phase='paused', next_check=None)
                elif time.monotonic() >= next_due:
                    status.update(phase='running', next_check=None)
                    try:
                        code = run_action(root, 'new', stop=stop)
                    except BusyError:
                        next_due = time.monotonic() + 5
                        status.update(phase='waiting-for-task', next_check=utc(time.time() + 5))
                    else:
                        last_finished = time.monotonic()
                        next_due = last_finished + config['interval_minutes'] * 60
                        status.update(phase='idle', last_exit_code=code, last_finished=utc(),
                                      next_check=utc(time.time() + config['interval_minutes'] * 60))
                else:
                    status.update(phase='idle', next_check=utc(time.time() + max(0, next_due - time.monotonic())))
            except (SettingsError, OSError, ValueError) as error:
                description = str(error) if isinstance(error, SettingsError) else bot.error_label(error)
                if description != last_error:
                    log('Checks paused: ' + description)
                    last_error = description
                status.update(phase='configuration-error', next_check=None)
            stop.wait(2)
        log('Service stopped; completed deliveries and queued work are retained.')
    return 0


def health(root):
    try:
        state = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
        age = time.time() - state['heartbeat']
        return 0 if 0 <= age < 90 and state['phase'] not in ('stopped', 'configuration-error') else 1
    except (OSError, ValueError, KeyError, TypeError):
        return 1


def show_status(root):
    config, _ = load_config(root)
    profile = config['profiles'].get(config['provider'], {})
    print('OSINT Digest server')
    print(f"Automatic checks: {'enabled' if config['enabled'] else 'paused'}")
    print(f"Interval: {config['interval_minutes']} minutes | Test article limit: {config['max_posts']}")
    print('Normal checks: all enabled sources, all unsent articles. Test mode is manual only.')
    print(f"Provider: {config['provider']} | Model: {profile.get('model') or '(none)'}")
    print(f"Discord webhook: {'saved' if config['webhook'] else 'not configured'} | AI key: {'saved' if profile.get('api_key') else 'not configured'}")
    print(f"Sources: {sum(s.get('enabled', True) for s in config['sources'])} enabled / {len(config['sources'])} total")
    print('Service: ' + ('running (heartbeat current)' if health(root) == 0 else 'stopped, unhealthy, or not started'))
    for name in ('runtime.json', 'last-run.json'):
        path = root / name
        if path.exists():
            print(name + ': ' + json.dumps(json.loads(path.read_text(encoding='utf-8'))))


def backup(root):
    with file_lock(root / '.run.lock'), file_lock(root / '.config.lock'):
        name = 'osint-digest-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tar.gz'
        target = root / 'backups' / name
        with target.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name in ('server.json', 'state', 'preview'):
                archive.add(root / name, arcname=name)
        print('Backup saved to ' + str(target) + ' (contains credentials; store privately).')
        return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.getenv('OSINT_DATA_DIR', 'server-data')))
    commands = parser.add_subparsers(dest='command', required=True)
    for action in ('serve', 'setup', 'settings', 'sources', 'models', 'status', 'health', 'backup', *ACTIONS):
        command = commands.add_parser(action)
        if action in ('batch', 'preview', 'new'):
            command.add_argument('--test-mode', action='store_true', help='Allow repeats in a limited manual test')
            command.add_argument('--count', type=int, help='Test article limit, 1-20; requires --test-mode')
        if action == 'test-ai':
            command.add_argument('--source', default='*', help='Optional publisher name')
    args = parser.parse_args(argv)
    root = args.data_dir.resolve()
    if args.command == 'health':
        return health(root)
    if args.command in ('setup', 'settings', 'sources', 'models') and not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('This command needs an interactive terminal. Use docker compose run --rm digest ' + args.command + ' (without -T).', file=sys.stderr)
        return 2
    if os.name != 'nt':
        os.umask(0o077)
    stop = threading.Event()
    for name in ('SIGTERM', 'SIGINT'):
        signal.signal(getattr(signal, name), lambda *_: stop.set())
    try:
        initialize(root)
        if args.command == 'serve':
            return serve(root, stop)
        if args.command in ('setup', 'settings', 'sources', 'models'):
            # Interactive commands retain normal Ctrl+C behavior at prompts.
            signal.signal(signal.SIGINT, signal.default_int_handler)
            from osint_digest.server.setup import administer
            administer(root, args.command)
        elif args.command == 'status':
            show_status(root)
        elif args.command == 'backup':
            backup(root)
        else:
            return run_action(root, args.command, getattr(args, 'count', None), getattr(args, 'source', '*'), stop,
                              test_mode=getattr(args, 'test_mode', False))
        return 0
    except BusyError as error:
        print(str(error), file=sys.stderr)
        return 75
    except SettingsError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled; unfinished settings were not saved.')
        return 130
    except Exception as error:
        print('Server operation failed: ' + bot.error_label(error) + '. Check settings, storage access, and connectivity.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
