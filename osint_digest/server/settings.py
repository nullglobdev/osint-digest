"""Portable server configuration: private files, atomic saves, and process locks."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from osint_digest.core.endpoints import ollama_base_url
from osint_digest.core.providers import PROVIDERS, KEY_ENV
from osint_digest.core.sources import make_source
from osint_digest.core import scopes
from osint_digest.paths import resource_path

DEFAULTS = {'schema_version': 5, 'provider': 'none', 'profiles': {}, 'webhooks': [],
            'legacy_webhook_id': '',
            'per_source_limit': 5, 'interval_minutes': 60, 'enabled': False,
            'ollama_url': 'http://host.docker.internal:11434', 'sources': [], **scopes.DEFAULTS}
ENV_KEYS = ('DISCORD_WEBHOOK_URL', 'AI_PROVIDER', 'AI_MODEL', 'ALLOW_PAID_AI',
            'MAX_POSTS', 'OLLAMA_BASE_URL', *KEY_ENV.values())


class BusyError(RuntimeError):
    pass


class SettingsError(ValueError):
    pass


@contextmanager
def file_lock(path):
    """Do not unlink lock files: other processes may hold the same inode."""
    with Path(path).open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise BusyError('Another operation is using this data folder. Try again shortly.') from None
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise BusyError('Another operation is using this data folder. Try again shortly.') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path, data):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize(root):
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ('state', 'preview', 'backups'):
        (root / name).mkdir(mode=0o700, exist_ok=True)
    with file_lock(root / '.config.lock'):
        if not (root / 'server.json').exists():
            config = deepcopy(DEFAULTS)
            config['sources'] = json.loads(resource_path('config/sources.json').read_text(encoding='utf-8'))
            atomic_json(root / 'server.json', config)


def webhook_id(webhook):
    """Stable across token rotation; never store the secret URL in delivery history."""
    try:
        url = urlsplit(webhook)
        if (not isinstance(webhook, str) or url.scheme != 'https' or url.hostname != 'discord.com'
                or url.username or url.password or url.port not in (None, 443) or url.query or url.fragment
                or not re.fullmatch(r'/api/webhooks/\d+/[\w-]+', url.path)
                or any(c.isspace() for c in webhook)):
            raise ValueError()
        return url.path.split('/')[3]
    except (ValueError, TypeError, AttributeError):
        raise SettingsError('Enter a Discord channel webhook URL from Channel Settings > Integrations.') from None


def validate_webhooks(webhooks):
    if not isinstance(webhooks, list):
        raise SettingsError('Webhooks must be a list; use the Webhooks menu.')
    ids, names = set(), set()
    for target in webhooks:
        if not isinstance(target, dict):
            raise SettingsError('Invalid webhook; use the Webhooks menu.')
        name = target.get('name')
        if (not isinstance(name, str) or not name.strip() or len(name) > 80
                or any(not c.isprintable() for c in name)):
            raise SettingsError('Webhook names must contain 1–80 printable characters.')
        if type(target.get('enabled')) is not bool:
            raise SettingsError('Each webhook must be enabled or disabled.')
        identity = webhook_id(target.get('url'))
        if identity in ids or name.strip().casefold() in names:
            raise SettingsError('Each webhook must have a unique name and Discord webhook ID.')
        ids.add(identity)
        names.add(name.strip().casefold())


def active_webhooks(config):
    return [target for target in config['webhooks'] if target['enabled']]


def validate(config):
    if config.get('schema_version') != 5:
        raise SettingsError('Unsupported server configuration version; use a compatible app version.')
    try:
        scopes.selection(config)
    except ValueError as error:
        raise SettingsError(str(error)) from None
    if config.get('provider') not in PROVIDERS.values():
        raise SettingsError('Choose a supported AI provider.')
    for key, low, high in (('per_source_limit', 1, 100), ('interval_minutes', 15, 360)):
        if type(config.get(key)) is not int or not low <= config[key] <= high:
            raise SettingsError(f'{key} must be a whole number from {low} to {high}.')
    if type(config.get('enabled')) is not bool:
        raise SettingsError('Automatic checks must be enabled or disabled.')
    if 'webhook' in config:
        raise SettingsError('Use the webhooks list for server settings; reopen the Webhooks menu.')
    validate_webhooks(config.get('webhooks'))
    legacy_id = config.get('legacy_webhook_id', '')
    if not isinstance(legacy_id, str) or (legacy_id and not re.fullmatch(r'\d+', legacy_id)):
        raise SettingsError('Invalid legacy webhook history reference.')
    try:
        ollama_base_url(config.get('ollama_url', ''))
    except (ValueError, AttributeError):
        raise SettingsError('Use an HTTP(S) Ollama URL without credentials, query, or fragment.') from None
    if not isinstance(config.get('profiles'), dict):
        raise SettingsError('Invalid AI profiles; run setup again.')
    for provider, profile in config['profiles'].items():
        if provider not in KEY_ENV and provider != 'ollama':
            raise SettingsError('Unknown AI profile.')
        if not isinstance(profile, dict):
            raise SettingsError('Invalid AI profile.')
        key, model = profile.get('api_key', ''), profile.get('model', '')
        if not isinstance(key, str) or any(ord(c) < 32 or ord(c) == 127 for c in key):
            raise SettingsError('API keys must be single-line text.')
        pattern = r'[A-Za-z0-9._-]+' if provider == 'gemini' else r'[A-Za-z0-9._:/-]+'
        if not isinstance(model, str) or (model and not re.fullmatch(pattern, model)):
            raise SettingsError('Enter a valid model ID; omit the models/ prefix for Gemini.')
        if type(profile.get('allow_paid', False)) is not bool:
            raise SettingsError('AI billing opt-in must be true or false.')
    sources = config.get('sources')
    if not isinstance(sources, list):
        raise SettingsError('Sources must be a list.')
    checked = []
    for source in sources:
        try:
            if type(source.get('enabled', True)) is not bool or not isinstance(source['hosts'], list):
                raise ValueError()
            checked.append(make_source(source['name'], source['feed'], ','.join(source['hosts']), checked,
                                       enabled=source.get('enabled', True)))
            if checked[-1]['hosts'] != source['hosts']:
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SettingsError('Invalid or duplicate source; use the Sources menu to correct it.') from None


def load_config(root):
    raw = (Path(root) / 'server.json').read_bytes()
    try:
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError()
        if config.get('schema_version') == 1:
            # Migrate in memory. Keep the original identity even if the operator
            # changes destinations before the next run imports old receipts.
            webhook = config.pop('webhook', '')
            if not isinstance(webhook, str):
                raise SettingsError('Invalid legacy webhook setting.')
            config['legacy_webhook_id'] = webhook_id(webhook) if webhook else ''
            config['webhooks'] = [{'name': 'Primary', 'url': webhook, 'enabled': True}] if webhook else []
            config['schema_version'] = 2
        if config.get('schema_version') == 2:
            config['schema_version'] = 3
        if config.get('schema_version') == 3:
            config['schema_version'] = 4
        if config.get('schema_version') == 4:
            config['schema_version'] = 5
        for key in scopes.LABELS:
            config.setdefault(key, '')
        config.setdefault('per_source_limit', config.get('max_posts', 5))
        config.pop('max_posts', None)
        validate(config)
    except (ValueError, TypeError, KeyError) as error:
        if isinstance(error, SettingsError):
            raise
        raise SettingsError('Cannot read server.json. Restore a backup or correct the file.') from None
    return config, hashlib.sha256(raw).hexdigest()


def save_config(root, config, revision):
    validate(config)
    with file_lock(Path(root) / '.config.lock'):
        _, current = load_config(root)
        if current != revision:
            raise SettingsError('Settings changed in another session. Reopen this menu before saving.')
        atomic_json(Path(root) / 'server.json', config)


def require_ready(config, action='new'):
    if action in ('new', 'batch', 'test-discord') and not active_webhooks(config):
        raise SettingsError('Add and enable at least one Discord webhook in the Webhooks menu first.')
    provider = config['provider']
    if action in ('check-feeds', 'test-discord'):
        return
    if not any(s.get('enabled', True) for s in config['sources']):
        raise SettingsError('Enable at least one source.')
    if action == 'test-ai' and provider == 'none':
        raise SettingsError('Choose an AI provider before testing AI.')
    profile = config['profiles'].get(provider, {})
    if provider != 'none' and not profile.get('model'):
        raise SettingsError('Choose a model for the selected provider.')
    if provider in KEY_ENV and not profile.get('api_key'):
        raise SettingsError('Add the selected provider\'s AI API key.')
    if provider in ('openai', 'anthropic') and not profile.get('allow_paid'):
        raise SettingsError('Enable usage billing for this provider in the connection menu, or choose another provider.')


@contextmanager
def configured_environment(config):
    previous = {key: os.environ.get(key) for key in ENV_KEYS}
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    provider = config['provider']
    profile = config['profiles'].get(provider, {})
    os.environ.update(AI_PROVIDER=provider, AI_MODEL=profile.get('model', ''),
                      DISCORD_WEBHOOK_URL='',
                      ALLOW_PAID_AI='true' if profile.get('allow_paid') else 'false',
                      OLLAMA_BASE_URL=config['ollama_url'])
    if provider in KEY_ENV:
        os.environ[KEY_ENV[provider]] = profile.get('api_key', '')
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
