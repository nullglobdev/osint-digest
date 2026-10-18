# Persistence, backups, updates, and recovery

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

The Docker image and data volume have separate lifecycles. Keep Compose project name `osint-digest` to reuse `osint-digest_digest-data`. Rebuilding retains data; `docker compose down -v` deletes it.

## Backup

Pause automatic checks and wait for the active task to finish:

```sh
sh scripts/server.sh backup
```

This locks collection/configuration and archives `server.json`, `state/`, and `preview/` under `/data/backups/`. Old backups are excluded. If busy, wait and retry. Copy the printed archive to a private location outside the volume/repository:

```sh
docker compose cp digest:/data/backups/ARCHIVE-NAME.tar.gz /private/backup/ARCHIVE-NAME.tar.gz
```

Create the private destination directory first. The service container must exist for `compose cp`. Backups contain credentials: restrict access, encrypt appropriately, and verify an off-host copy. A backup in the original volume alone does not protect against volume loss. Monitor space; backups and previews are not automatically pruned by this command.

## Upgrade only when intended

Review release notes/revision, record `git rev-parse HEAD`, inspect `git status --short`, preserve edits, and back up. In a clean Git checkout tracking the intended branch:

```sh
sh scripts/server.sh stop
git pull --ff-only
```

Continue only if pull succeeds and the resulting revision is the intended update:

```sh
sh scripts/server.sh update
sh scripts/server.sh status
```

`update` rebuilds checked-out source with a refreshed base image and recreates the service; it does not pull Git. Stop on dirty source or a failed pull, without resetting local work. Archive installs use a reviewed replacement bundle instead of Git, keeping the same Compose project name. Re-enable checks if paused and inspect logs/last-run status.

Stop requests graceful completion/retained queued work; Compose allows five minutes before forced termination. Health alone does not prove successful delivery.

## Recovery

There is no `server.sh restore` command. Stop the service, preserve the current volume privately, then restore a trusted archive with your Docker-volume recovery tooling. Restore `server.json`, `state/`, and `preview/` under `/data`, preserving UID/GID 10001 and restrictive permissions. Start and inspect status/logs. Keep automatic checks paused until the recovered configuration is reviewed. Do not substitute Windows `settings.json` for server configuration.

Use code compatible with the backup schema. Saving upgraded settings can migrate configuration (current server version 5); blindly using older code is not a safe rollback. Restore a matching pre-upgrade backup with compatible application code. Older history can repeat posts sent after the backup.

Windows editions share `%LOCALAPPDATA%\OSINTDigest`. Close the window and tray process before backing up the profile/upgrading. Account-encrypted credentials are not portable to another account or Linux. Run the new installer, or extract a portable ZIP to a fresh folder while retaining the profile. See [Windows guide](../DESKTOP.md).

Implementation: [backup/runtime](../../osint_digest/server/app.py), [Compose](../../compose.yaml), [schema](../../osint_digest/server/settings.py).
