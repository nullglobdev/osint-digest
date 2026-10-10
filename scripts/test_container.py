"""Offline container acceptance checks. Uses only temporary, uniquely named resources.

Build first: docker compose build
Run: python scripts/test_container.py
No publisher, AI, or Discord network access is available to the test containers.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

IMAGE = 'osint-digest-server:local'


def docker(*args, script=None, expected=0):
    result = subprocess.run(['docker', *args], input=script, text=True, capture_output=True, timeout=60)
    if result.returncode != expected:
        raise AssertionError(f'Docker command failed ({result.returncode}): {result.stderr}\n{result.stdout}')
    return result.stdout


def main():
    suffix = uuid.uuid4().hex[:10]
    name, volume = 'osint-test-' + suffix, 'osint-test-data-' + suffix
    docker('volume', 'create', '--label', 'osint-digest.test=true', volume)
    options = ['--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt',
               'no-new-privileges:true', '--tmpfs', '/tmp:mode=1777', '-v', volume + ':/data']
    try:
        docker('run', '-d', '--name', name, *options, IMAGE)
        for _ in range(40):
            result = subprocess.run(['docker', 'exec', name, 'python', '/app/server.py', 'health'],
                                     capture_output=True, timeout=10)
            if result.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise AssertionError('Service did not become healthy')
        docker('exec', '-i', name, 'python', '-', script='''
from pathlib import Path
import importlib.util, os, stat
from server_settings import load_config, save_config
root = Path('/data')
assert os.getuid() == 10001
assert stat.S_IMODE((root / 'server.json').stat().st_mode) == 0o600
assert not Path('/app/.env').exists()
assert importlib.util.find_spec('PySide6') is None
assert not Path('/app/settings.json').exists()
config, revision = load_config(root)
assert not config['enabled'] and not config['webhook']
config['max_posts'], config['interval_minutes'] = 10, 360
save_config(root, config, revision)
(root / 'state' / 'marker').write_text('persistent history')
try:
    Path('/app/write-test').write_text('forbidden')
except OSError:
    pass
else:
    raise AssertionError('Root filesystem must be read-only')
''')
        # A second daemon on the same volume must fail instead of posting twice.
        docker('run', '--rm', *options, IMAGE, 'serve', expected=75)
        # Noninteractive setup must refuse input rather than echo credentials.
        output = docker('run', '--rm', '-i', *options, IMAGE, 'setup', script='never-echo-this\n', expected=2)
        assert 'never-echo-this' not in output
        # Exercise real collector state transitions and graceful stop with mocked transports.
        docker('exec', '-i', name, 'python', '-', script='''
import io, json, threading
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
import bot, server
from server_settings import load_config, save_config
root = Path('/data')
config, revision = load_config(root)
config['webhook'] = 'https://discord.com/api/webhooks/123/offline-test'
config['sources'] = [{'name':'Test', 'feed':'https://publisher.example/rss', 'hosts':['publisher.example'], 'enabled':True}]
save_config(root, config, revision)
pending = {f'https://publisher.example/{i}': {'source':'Test', 'url':f'https://publisher.example/{i}', 'title':str(i), 'discovered':str(i), 'published':''} for i in range(2)}
bot.save_state(root / 'state/state.json', {'feeds':{}, 'pending':pending, 'seen':{}})
stop = threading.Event()
def sent(report):
    stop.set()
    return 'offline-message'
with patch.object(bot, 'discover', return_value=0), patch.object(bot, 'article_report', return_value={'analysis':None, 'ai_status':'No AI'}), patch.object(bot, 'send_discord', side_effect=sent), redirect_stdout(io.StringIO()):
    assert server.run_action(root, 'new', stop=stop) == 0
state = json.loads((root / 'state/state.json').read_text())
assert len(state['seen']) == 1 and len(state['pending']) == 1
with redirect_stdout(io.StringIO()):
    archive = server.backup(root)
assert archive.exists()
config, revision = load_config(root)
config['webhook'] = ''
save_config(root, config, revision)
''')
        docker('stop', '--time', '15', name)
        details = json.loads(docker('inspect', name))[0]
        assert details['State']['ExitCode'] == 0, 'SIGTERM shutdown must be clean'
        docker('start', name)
        docker('exec', '-i', name, 'python', '-', script='''
import json
from pathlib import Path
from server_settings import load_config
root = Path('/data')
config, _ = load_config(root)
assert config['max_posts'] == 10 and config['interval_minutes'] == 360
assert not config['webhook'] and not config['enabled']
assert (root / 'state/marker').read_text() == 'persistent history'
state = json.loads((root / 'state/state.json').read_text())
assert len(state['seen']) == 1 and len(state['pending']) == 1
''')
        print('Container acceptance passed: non-root/read-only runtime, private settings, no GUI or credentials in image,')
        print('configuration persistence, process locking, safe terminal behavior, delivery-state recovery, backup, and graceful restart.')
    finally:
        # Only the exact resources created above are removed; no pruning or shared data changes.
        subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=30)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
