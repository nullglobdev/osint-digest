"""Per-user desktop configuration. Secrets use Windows user-scoped DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

APP_NAME = 'OSINT Digest'
VERSION = '1.0.0'
DEFAULTS = {'provider': 'gemini', 'model': 'gemini-3.1-flash-lite',
            'webhook': '', 'gemini_key': '', 'batch_size': 5, 'interval_minutes': 60}
SECRET_KEYS = ('webhook', 'gemini_key')


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / name


def data_directory():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'OSINTDigest'


def initialize(root):
    root.mkdir(parents=True, exist_ok=True)
    sources = root / 'sources.json'
    if not sources.exists():
        sources.write_bytes(resource_path('sources.json').read_bytes())
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
    if settings['provider'] not in ('gemini', 'none', 'ollama'):
        raise ValueError('Choose Gemini, publisher excerpts, or local Ollama.')
    if settings['webhook']:
        p = urlsplit(settings['webhook'])
        if (p.scheme != 'https' or p.hostname != 'discord.com' or p.username or p.password
                or p.port not in (None, 443) or p.fragment
                or not re.fullmatch(r'/api/webhooks/\d+/[\w-]+', p.path)):
            raise ValueError('Paste a Discord channel webhook URL from Channel Settings > Integrations > Webhooks.')
    if '\n' in settings['gemini_key'] or '\r' in settings['gemini_key']:
        raise ValueError('The Gemini API key must be on a single line.')
    if settings['provider'] == 'gemini' and not re.fullmatch(r'[A-Za-z0-9._-]+', settings['model']):
        raise ValueError('Enter a Gemini API model name, for example gemini-3.1-flash-lite.')
    if settings['provider'] == 'ollama' and not settings['model'].strip():
        raise ValueError('Enter the name of a model installed in Ollama.')
    if not 1 <= int(settings['batch_size']) <= 20:
        raise ValueError('Choose between 1 and 20 articles.')
    if not 15 <= int(settings['interval_minutes']) <= 1440:
        raise ValueError('Choose an automatic check interval between 15 and 1440 minutes.')


def load_settings(root):
    path = root / 'settings.json'
    if not path.exists():
        return dict(DEFAULTS)
    data = json.loads(path.read_text(encoding='utf-8'))
    result = {**DEFAULTS, **{k: data[k] for k in DEFAULTS if k in data and k not in SECRET_KEYS}}
    for key in SECRET_KEYS:
        result[key] = unprotect(data.get(key + '_protected', ''))
    validate(result)
    return result


def save_settings(root, settings):
    validate(settings)
    data = {k: settings[k] for k in DEFAULTS if k not in SECRET_KEYS}
    for key in SECRET_KEYS:
        data[key + '_protected'] = protect(settings[key])
    atomic_json(root / 'settings.json', data)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def apply_environment(settings):
    # The desktop app never imports credentials or provider choices from the shell or repo .env.
    for key in ('DISCORD_WEBHOOK_URL', 'GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
                'AI_PROVIDER', 'AI_MODEL', 'ALLOW_PAID_AI', 'MAX_POSTS'):
        os.environ.pop(key, None)
    os.environ.update(DISCORD_WEBHOOK_URL=settings['webhook'], GEMINI_API_KEY=settings['gemini_key'],
                      AI_PROVIDER=settings['provider'], AI_MODEL=settings['model'],
                      ALLOW_PAID_AI='false', MAX_POSTS=str(settings['batch_size']))
