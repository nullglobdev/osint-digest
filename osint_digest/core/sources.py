"""Validation for user-added RSS/Atom feeds. Network validation remains in bot.fetch."""
import ipaddress
import re
from urllib.parse import urlsplit


def public_host(value):
    host = value.strip().lower().rstrip('.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if (len(host) > 253 or '.' not in host or host.endswith(('.local', '.localhost', '.internal'))
                or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                           for label in host.split('.'))):
            raise ValueError('Use public domain names, such as www.example.com, for allowed hosts.')
    else:
        if not address.is_global or address.version != 4:
            raise ValueError('Use a public domain name for this source.')
    return host


def make_source(name, feed, hosts, sources, editing=None, enabled=True):
    name, feed = name.strip(), feed.strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a source name between 1 and 80 characters.')
    try:
        url = urlsplit(feed)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.port not in (None, 443) or url.fragment or any(c.isspace() for c in feed)):
            raise ValueError()
        feed_host = public_host(url.hostname)
    except ValueError:
        raise ValueError('Enter a public HTTPS RSS or Atom feed URL, without a login or fragment.') from None
    allowed = list(dict.fromkeys([feed_host, *(public_host(h) for h in re.split(r'[,;\s]+', hosts) if h)]))
    for i, source in enumerate(sources):
        if i != editing and (source['name'].casefold() == name.casefold()
                             or source['feed'].rstrip('/') == feed.rstrip('/')):
            raise ValueError('A source with that name or feed URL already exists.')
    return {'name': name, 'feed': feed, 'hosts': allowed, 'enabled': enabled}
