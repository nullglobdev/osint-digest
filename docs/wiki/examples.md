# Copyable examples

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Run Docker commands from an existing configured checkout with a built image. Replace placeholders before use. Start with [Settings](settings.md) for routine changes.

## Inspect without publishing

```sh
sh scripts/server.sh status
sh scripts/server.sh check-feeds
sh scripts/server.sh test-discord
```

Feed checks contact publishers; the Discord check makes read-only requests without messages.

## Preview and AI tests

```sh
sh scripts/server.sh preview
sh scripts/server.sh test-ai --source Huntress
sh scripts/server.sh preview --test-mode --count 2 --test-days 30
```

These do not send to Discord, but may consume AI quota. The last example permits repeats, up to two articles per source within 30 days, retaining filters. It only finds entries still in feeds and does not change saved schedule/history. `--test-days` accepts 1-365. A named source must exist in your profile.

## Deliberately send

These commands **publish messages** to every enabled server destination:

```sh
sh scripts/server.sh new
```

This checks recent unsent articles and due retries. This next example intentionally allows repeated delivery:

```sh
sh scripts/server.sh new --test-mode --count 2 --test-days 30
```

`--count` requires `--test-mode`; it is per source, not a total-message limit. Normal checks retain the 48-hour window. Pause automatic checks to avoid a competing task; busy actions are rejected.

## Windows / Python source preview

From a configured checkout with Python available:

```powershell
py -3 bot.py --dry-run --per-source-limit 5 --max-age-hours 48
```

CLI uses its own `.env`, not GUI/server settings. AI may still run. Windows **Collect new** publishes to Results or its webhook; Dev mode exposes preview/test controls. See [Windows guide](../DESKTOP.md).

Use [maintenance](maintenance.md) for upgrades/backups, not `update` for a setting adjustment.
