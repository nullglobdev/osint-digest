"""Per-user desktop configuration. Secrets use Windows user-scoped DPAPI."""
import base64
import ctypes
from copy import deepcopy
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from osint_digest.core.providers import PROVIDERS, KEY_ENV
from osint_digest.paths import resource_path

APP_NAME = 'OSINT Digest'
VERSION = '1.3.0'
DEFAULTS = {'provider': 'gemini', 'model': 'gemini-3.1-flash-lite',
            'webhook': '', 'api_key': '', 'batch_size': 5, 'interval_minutes': 60,
            'close_to_tray': True, 'profiles': {}, 'theme': 'dark', 'text_scale': 100}
SECRET_KEYS = ('webhook', 'api_key')


def data_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'OSINTDigest'


def initialize(root):
    root.mkdir(parents=True, exist_ok=True)
    sources = root / 'sources.json'
    if not sources.exists():
        sources.write_bytes(resource_path('config/sources.json').read_bytes())
    (root / 'preview').mkdir(exist_ok=True)


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(raw, decrypt=False):
    if os.name != 'nt':
        raise OSError('Desktop credential storage requires Windows')
    buffer = ctypes.create_string_buffer(raw)
    incoming = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not operation(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise OSError('Windows could not unlock the saved credentials for this user')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel32.LocalFree(outgoing.data)


def protect(value):
    return base64.b64encode(_crypt(value.encode('utf-8'))).decode('ascii') if value else ''


def unprotect(value):
    return _crypt(base64.b64decode(value, validate=True), decrypt=True).decode('utf-8') if value else ''


def validate(settings):
    if settings.get('theme', 'dark') not in ('dark', 'light', 'system'):
        raise ValueError('Choose Dark, Light, or Windows theme.')
    if int(settings.get('text_scale', 100)) not in (100, 125, 150, 175, 200):
        raise ValueError('Choose a text size between 100% and 200%.')
    if settings['provider'] not in PROVIDERS.values():
        raise ValueError('Choose a summary provider from the list.')
    if settings['webhook']:
        p = urlsplit(settings['webhook'])
        if (p.scheme != 'https' or p.hostname != 'discord.com' or p.username or p.password
                or p.port not in (None, 443) or p.fragment
                or not re.fullmatch(r'/api/webhooks/\d+/[\w-]+', p.path)):
            raise ValueError('Paste a Discord channel webhook URL from Channel Settings > Integrations > Webhooks.')
    profiles = list(settings.get('profiles', {}).values()) + [settings]
    for profile in profiles:
        if any(ord(c) < 32 or ord(c) == 127 for c in profile.get('api_key', '')):
            raise ValueError('The AI API key must be on a single line without control characters.')
        if profile.get('model') and not re.fullmatch(r'[A-Za-z0-9._:/-]+', profile['model']):
            raise ValueError('Enter a model ID or choose a model from the list.')
    if settings['provider'] == 'gemini' and settings['model'] and not re.fullmatch(r'[A-Za-z0-9._-]+', settings['model']):
        raise ValueError('Choose a Gemini model ID without the models/ prefix.')
    if not 1 <= int(settings['batch_size']) <= 20:
        raise ValueError('Choose a test article limit between 1 and 20.')
    if not 15 <= int(settings['interval_minutes']) <= 360:
        raise ValueError('Choose an automatic check interval between 15 and 360 minutes.')


def load_settings(root):
    path = root / 'settings.json'
    if not path.exists():
        return deepcopy(DEFAULTS)
    data = json.loads(path.read_text(encoding='utf-8'))
    result = {**deepcopy(DEFAULTS), **{k: data[k] for k in DEFAULTS
                                     if k in data and k not in (*SECRET_KEYS, 'profiles')}}
    result['webhook'] = unprotect(data.get('webhook_protected', ''))
    result['profiles'] = {provider: {'model': profile.get('model', ''),
                                    'api_key': unprotect(profile.get('api_key_protected', ''))}
                          for provider, profile in data.get('profiles', {}).items()
                          if provider in PROVIDERS.values()}
    # Migrate v1.0 without assigning a Gemini credential to any other provider.
    if 'gemini_key_protected' in data:
        result['profiles'].setdefault('gemini', {
            'api_key': unprotect(data['gemini_key_protected']),
            'model': result['model'] if result['provider'] == 'gemini' else DEFAULTS['model']})
    profile = result['profiles'].get(result['provider'], {})
    result['api_key'] = profile.get('api_key', '')
    result['model'] = profile.get('model', result['model'])
    result['interval_minutes'] = min(360, int(result['interval_minutes']))
    validate(result)
    return result


def save_settings(root, settings):
    validate(settings)
    data = {k: settings[k] for k in DEFAULTS if k not in (*SECRET_KEYS, 'profiles')}
    data['schema_version'] = 3
    data['webhook_protected'] = protect(settings['webhook'])
    profiles = {**settings.get('profiles', {}), settings['provider']: {
        'model': settings['model'], 'api_key': settings['api_key']}}
    data['profiles'] = {provider: {'model': profile['model'],
                                   'api_key_protected': protect(profile['api_key'])}
                        for provider, profile in profiles.items() if provider in PROVIDERS.values()}
    atomic_json(root / 'settings.json', data)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def apply_environment(settings):
    # The desktop app never imports credentials or provider choices from the shell or repo .env.
    for key in ('DISCORD_WEBHOOK_URL', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
                'AI_PROVIDER', 'AI_MODEL', 'ALLOW_PAID_AI', 'MAX_POSTS', 'OLLAMA_BASE_URL'):
        os.environ.pop(key, None)
    os.environ.update(DISCORD_WEBHOOK_URL=settings['webhook'],
                      AI_PROVIDER=settings['provider'], AI_MODEL=settings['model'],
                      ALLOW_PAID_AI='true' if settings['provider'] in ('openai', 'anthropic') else 'false')
    if settings['provider'] in KEY_ENV:
        os.environ[KEY_ENV[settings['provider']]] = settings['api_key']
