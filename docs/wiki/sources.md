# Sources

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Sources are RSS/Atom feeds, not arbitrary websites or a historical search engine. Defaults live in [sources.json](../../config/sources.json). Windows and Docker keep saved source lists; changing the repository catalog does not replace an existing profile.

```sh
sh scripts/server.sh sources
sh scripts/server.sh check-feeds
```

The Docker menu adds/edits HTTPS feeds, enables/disables publishers, removes entries, and reorders test sampling priority. Supply exact allowed hostnames for article links and redirects; the feed hostname is included automatically. Existing publisher names stay fixed to preserve history. Do not broaden allowed hosts to bypass an unexplained redirect.

`check-feeds` checks enabled feed access without AI or Discord calls. Success does not prove every article page is accessible. Test from the actual deployment because publisher access may differ by network.

On Windows, use **Sources**, select feeds, then **Save sources**. **Add source** accepts a custom feed. Test sampling considers each source's newest eligible entry before its next entry.

No report can mean old/undated entries, inaccessible pages, no filter matches, or already-delivered articles. Preview with filters at All before assuming a feed is broken. Extended test windows reach only articles still in feeds; they do not crawl publisher archives.

Implementation: [source validation](../../osint_digest/core/sources.py), [collector](../../osint_digest/core/collector.py). Evidence: [menu tests](../../tests/test_server.py).
