# Discord delivery

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Create a channel webhook in Discord's integration settings and enter its URL only through credential prompts. The URL is a credential: keep it out of commands, Git, screenshots, and support reports.

```sh
sh scripts/server.sh webhooks
sh scripts/server.sh test-discord
```

Docker destinations can be added, renamed, replaced, enabled/disabled, and removed. Each enabled destination receives the same articles; there is no per-channel source/filter routing. Sending/automatic checks require at least one enabled destination. Pause before disabling all of them.

`test-discord` uses read-only requests and sends no messages. It tests access, not guaranteed future delivery.

## Receipts and retries

Server history follows webhook IDs and articles. Renaming, token rotation for the same ID, disabling, and removing/re-adding preserve history. Different webhooks in one channel each post independently.

One destination's failure does not prevent others receiving a report. Failed destinations retry during subsequent normal checks, with backoff starting at one hour and reaching at most one day. Cached reports avoid another AI call. Retries expire outside the 48-hour window. Newly added destinations receive still-eligible feed/queued articles without repeating successful delivery to existing destinations.

Delivery is at least once: a crash after Discord accepts a post but before its receipt is written can cause a duplicate. Explicit resend tests also allow repeats.

Windows and standalone CLI use one webhook; Windows may leave it blank for local Results. Installations have separate history.

Reports include original links, publication time, summary/excerpt, CVE/ATT&CK references, and IOC candidates. Discord has no JSON/CSV attachments; IOC previews use spoiler text. Validate indicators and generated claims against the source.

Implementation: [delivery](../../osint_digest/server/delivery.py). Evidence: [webhook tests](../../tests/test_webhooks.py).
