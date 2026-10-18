# Scheduling

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Desktop/server settings accept intervals of 15-360 minutes and 1-100 articles per source (default 5). The normal publication window stays at 48 hours. A fresh server profile starts paused.

```sh
sh scripts/server.sh settings
sh scripts/server.sh status
```

Enable/pause automatic checks in Settings. The service reloads settings on its idle loop, which waits two seconds between iterations. A running collection retains its initial snapshot until completion. Pausing prevents subsequent checks; it does not cancel an active task.

At service start or when enabling a paused schedule, collection can begin immediately. The next check is scheduled one interval after completion. An interval change recalculates from the previous completion when available. This is an interval scheduler, not wall-clock cron.

One collection runs per volume. A manual action or backup may report busy while a collection owns the lock. The daemon waits and retries when another task is active. Invalid enabled configuration pauses checks with a configuration error.

Closing SSH leaves Docker running. The restart policy is `unless-stopped`; a deliberately stopped service needs to be started again. The host must remain awake and online.

Windows uses **Check every** and **Start automatic checks**. **Run in background** keeps the tray process running; closing that process ends checks. The standalone CLI runs once and exits. External schedules and Actions are covered in the [CLI guide](../CLI.md). Independent installations keep independent history and can duplicate shared-channel posts.

Implementation: [`serve`](../../osint_digest/server/app.py). Evidence: [reload/concurrency tests](../../tests/test_server.py).
