# Troubleshooting

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Start with:

```sh
sh scripts/server.sh status
sh scripts/server.sh logs
```

Ctrl+C exits log viewing. Do not paste complete logs/configuration into issues; remove credentials and private names/paths first.

| Symptom | What to inspect |
|---|---|
| No automatic posts | Schedule enabled, service running, enabled webhook, valid provider settings; host awake/online |
| Healthy but no delivery | Health checks heartbeat/configuration, not publisher access, quota, or Discord delivery; inspect last-run status/logs |
| No eligible articles | Publication window, valid timezone-aware dates, enabled feeds, filters, and existing receipts |
| Feed check fails | Run `check-feeds` from this deployment; check URL and exact redirect/article hosts |
| Busy data folder | Another collection or backup owns the lock; pause future checks and wait; do not delete lock files |
| Saved edit seems ignored | Active collection retains its snapshot; wait until idle, confirm save and correct Compose project/volume |
| Stale editing-session error | Reload settings and reapply the intended edit; do not overwrite the newer configuration |
| AI failure | Provider/model availability, key, quota, billing opt-in, or Ollama endpoint reachability |
| Discord failure | Run `test-discord`; inspect enabled destinations and retry backoff; rotate credentials through the menu if needed |
| Apparent empty profile after update | Check unchanged Compose project name and original volume before configuring a replacement |
| Repeated posts | Test mode, distinct webhooks in one channel, separate installations, restored old history, or crash before receipt save |
| All destinations disabled | Pause checks, enable a valid destination, then resume |

For no-results diagnosis, preview with scopes at All and review eligible dates. To examine older feed entries without sending:

```sh
sh scripts/server.sh preview --test-mode --count 1 --test-days 30
```

This can consume AI quota and only finds entries still in feeds. It does not change saved scheduling or delivery history.

The menu requires an interactive terminal: use `docker compose run --rm digest settings` without `-T` if invoking Compose directly. Docker commands need permission to access the existing engine; do not solve an access failure by exposing its socket or printing credentials.

For a damaged volume or incompatible downgrade, use [recovery guidance](maintenance.md). Avoid deleting state to fix missing posts: it removes delivery receipts and can cause duplicates.
