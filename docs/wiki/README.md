# OSINT Digest wiki

The Docker edition is a headless service managed with terminal menus; it has no web UI. Windows provides a desktop window, tray controls, and local Results.

## Start here

- [Settings and post-install adjustments](settings.md): save changes without rebuilding.
- [Copyable examples](examples.md): inspect, preview, test, and deliberately send.
- [Troubleshooting](troubleshooting.md): missing articles, delivery failures, and busy tasks.
- [Maintenance and recovery](maintenance.md): backups, upgrades, and restore planning.

## How it works

| Topic | What it explains |
|---|---|
| [Digest pipeline](pipeline.md) | Feed entries, reports, and delivery receipts |
| [Sources](sources.md) | Feeds, allowed hosts, and publication dates |
| [Models and AI](models.md) | Publisher excerpts, provider profiles, and Ollama |
| [Filters](filters.md) | Seven scopes and excluded articles |
| [Scheduling](scheduling.md) | Intervals, pausing, concurrency, and reload timing |
| [Discord delivery](discord.md) | Destinations, deduplication, and retries |

## Editions and baseline

These pages describe application code at `2a35ec1` and `34585cb`. Comparing those revisions changes only README and CLI documentation; application code, the server helper, and tests are identical. This source comparison does not prove the revision of an arbitrary running image. Check your source with `git rev-parse HEAD`; older release bundles can differ.

| Edition | Configuration and output |
|---|---|
| Windows installer/portable/GUI source | Windows profile; one optional webhook or local Results; GUI schedule |
| Docker server | Terminal menus; multiple webhooks; persistent `/data`; background schedule |
| Standalone CLI | Private `.env`; one run per command; one webhook or `--local` |
| GitHub Actions | Repository secrets and workflow schedule |

A bare CLI invocation does not enforce the desktop/server cap or age window. Include `--per-source-limit 5 --max-age-hours 48` for comparable behavior.

Detailed references: [Windows](../DESKTOP.md), [container](../CONTAINER.md), [CLI](../CLI.md), [filter catalog](../SCOPES.md). This wiki is repository documentation, not a separate hosted application.
