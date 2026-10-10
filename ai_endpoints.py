"""Validation for an explicitly configured, operator-owned Ollama server."""
from urllib.parse import urlsplit


def ollama_base_url(value):
    value = value.strip().rstrip('/')
    try:
        url = urlsplit(value)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.port == 0
                or any(c.isspace() or ord(c) < 32 for c in value)):
            raise ValueError()
        _ = url.port
    except ValueError:
        raise ValueError('Use an HTTP(S) Ollama base URL without credentials, query, or fragment.') from None
    return value
