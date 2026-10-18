# Digest pipeline

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

1. Load enabled sources and a snapshot of settings for this collection.
2. Read RSS/Atom entries, newest first. Normal desktop/server checks use a 48-hour publication window. Missing, invalid, timezone-free, future, and older dates are excluded. An Atom updated timestamp does not make an old published article new.
3. Skip acknowledged deliveries and consider due retries within the same age window.
4. Retrieve article content under source host/access rules and apply selected filters before AI. Nonmatching articles do not consume the per-source cap.
5. Build a report using publisher excerpts or the configured AI provider. Reports include source links, publication time, CVE/ATT&CK references, and IOC candidates; review them against the original source.
6. Deliver to local Results or Discord. The server summarizes once for its enabled destinations, saving each successful destination receipt immediately.
7. Keep pending server deliveries and cached reports for retry; expire articles leaving the age window.

The age window is checked again around processing/delivery, so an article expiring during AI processing may not be posted. Previews do not send or change delivery history, but can consume AI quota.

The cap defaults to 5 per source and accepts 1-100. Ten sources at 5 can select up to 50 articles; two webhooks can produce up to 100 messages. These are upper bounds.

Implementation: [collector](../../osint_digest/core/collector.py), [delivery](../../osint_digest/server/delivery.py). Evidence: [window tests](../../tests/test_collection_window.py), [destination tests](../../tests/test_webhooks.py).
