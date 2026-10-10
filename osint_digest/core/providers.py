"""Provider catalog and read-only model discovery; no third-party SDK required."""
import json
import re
import urllib.request
from urllib.parse import urlencode
from osint_digest.core.endpoints import ollama_base_url

PROVIDERS = {'Google Gemini': 'gemini', 'OpenAI': 'openai', 'Anthropic Claude': 'anthropic',
             'Local Ollama': 'ollama', 'Publisher excerpts (no AI)': 'none'}
KEY_ENV = {'gemini': 'GEMINI_API_KEY', 'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}
PORTALS = {'gemini': 'https://aistudio.google.com/apikey',
           'openai': 'https://platform.openai.com/api-keys',
           'anthropic': 'https://platform.claude.com/settings/keys',
           'ollama': 'https://ollama.com/'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Authenticated discovery stays at the fixed provider endpoint.
        return None


def get_json(url, headers):
    request = urllib.request.Request(url, headers={'Accept': 'application/json',
                                                  'User-Agent': 'OSINTDigest/1.1', **headers})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=15) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Model list was too large')
        return json.loads(raw)


def text_model(provider, model):
    name = model.lower()
    if provider == 'openai':
        return (bool(re.match(r'^(?:gpt-|chatgpt-|o\d+(?:-|$)|ft:gpt-)', name))
                and not any(part in name for part in ('audio', 'realtime', 'transcribe', 'tts',
                                                       'image', 'search', 'deep-research', 'codex', '-pro')))
    if provider == 'gemini':
        return not any(part in name for part in ('image', 'tts', 'audio', 'robotics', 'computer-use'))
    return True


def list_models(provider, api_key='', ollama_url='http://127.0.0.1:11434'):
    if provider == 'none':
        return []
    if provider in KEY_ENV and (not api_key or any(ord(c) < 32 or ord(c) == 127 for c in api_key)):
        raise ValueError('Enter a valid API key first')
    endpoints = {'gemini': 'https://generativelanguage.googleapis.com/v1beta/models',
                 'openai': 'https://api.openai.com/v1/models',
                 'anthropic': 'https://api.anthropic.com/v1/models',
                 'ollama': ollama_base_url(ollama_url) + '/api/tags'}
    headers = {'gemini': {'x-goog-api-key': api_key},
               'openai': {'Authorization': 'Bearer ' + api_key},
               'anthropic': {'x-api-key': api_key, 'anthropic-version': '2023-06-01'},
               'ollama': {}}[provider]
    query = {'pageSize': 1000} if provider == 'gemini' else {'limit': 1000} if provider == 'anthropic' else {}
    models, seen_tokens = [], set()
    for _ in range(20):
        data = get_json(endpoints[provider] + ('?' + urlencode(query) if query else ''), headers)
        if provider == 'gemini':
            models.extend(m['name'].removeprefix('models/') for m in data.get('models', [])
                          if 'generateContent' in m.get('supportedGenerationMethods', []))
            token, field = data.get('nextPageToken'), 'pageToken'
        elif provider == 'ollama':
            models.extend(m['name'] for m in data.get('models', []))
            token, field = None, ''
        else:
            models.extend(m['id'] for m in data.get('data', []) if m.get('lifecycle') != 'retired')
            token, field = data.get('last_id') if data.get('has_more') else None, 'after_id'
        if not token:
            break
        if token in seen_tokens:
            raise ValueError('Provider returned repeated model pages')
        seen_tokens.add(token)
        query[field] = token
    else:
        raise ValueError('Provider returned too many model pages')
    return sorted({m for m in models if text_model(provider, m)})
