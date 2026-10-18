# Settings and post-install adjustments

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Replace account, host, and checkout placeholders:

```sh
ssh USER@DOCKER_HOST
cd /path/to/osint-digest
sh scripts/server.sh settings
```

Choose a setting and save. Focused menus:

```sh
sh scripts/server.sh sources
sh scripts/server.sh models
sh scripts/server.sh filters
sh scripts/server.sh webhooks
```

Use an interactive terminal; do not add `-T` to menus or pipe credentials. Keys/webhooks use hidden-input prompts. Ctrl+C cancels an unfinished edit. Stale editing sessions cannot silently overwrite a newer saved configuration.

**Saved changes reload without restarting or rebuilding.** Idle changes appear within seconds; active collections finish with their original snapshot. For multiple edits, pause automatic checks, save, preview, then re-enable when ready. Do not rerun `setup` or `update` for routine adjustments.

```sh
sh scripts/server.sh status
sh scripts/server.sh logs
```

Ctrl+C exits log viewing without stopping the service. Status hides saved secrets, but names/paths and logs can still be private; review before sharing.

| Edition | Data location |
|---|---|
| Docker | `/data/server.json`, state and previews in `osint-digest_digest-data` |
| Windows GUI | `%LOCALAPPDATA%\OSINTDigest`; account-encrypted credentials |
| Standalone CLI | Private `.env`, `state/`, `preview/`, `results/` in the checkout |

The server imports neither `.env` nor desktop profiles. Linux credentials are plaintext in the protected volume (config mode 0600, directories 0700), accessible to host/Docker administrators. Keep backups private. A different Compose project name makes a separate volume and apparent fresh settings. Never use `docker compose down -v` to preserve configuration/history.

Continue with [maintenance](maintenance.md).
