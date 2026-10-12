# Python CLI and scheduling

For installation choices, start with the [README](../README.md). For the graphical app or container service, use the [desktop](DESKTOP.md) or [server](CONTAINER.md) guide. This page covers the standalone `bot.py` collector and the included GitHub Actions workflow.

The collector requires Python 3.11+ and no pip packages. Commands below use Windows's `py -3` launcher; on Linux/macOS, replace it with `python3`. Run them from the repository root.

## Configure the CLI

Copy `.env.example` to `.env` once and edit it locally. Leave existing `.env` files in place when upgrading. Environment variables take precedence over values loaded from `.env`.

| Setting | Purpose |
|---|---|
| `DISCORD_WEBHOOK_URL` | Destination channel webhook; unnecessary for previews or `--local` publishing |
| `AI_PROVIDER` | `none`, `gemini`, `openai`, `anthropic`, or `ollama` |
| `AI_MODEL` | A model ID supported by the selected provider and your account |
| `GEMINI_API_KEY` | Gemini credential |
| `OPENAI_API_KEY` | OpenAI credential |
| `ANTHROPIC_API_KEY` | Claude credential |
| `ALLOW_PAID_AI` | Set to `true` to enable the CLI's OpenAI or Claude adapter |
| `OLLAMA_BASE_URL` | Operator-controlled Ollama endpoint; defaults to `http://127.0.0.1:11434` |

Start with `AI_PROVIDER=none` for publisher excerpts and deterministic IOC/CVE extraction. To enable AI, select a provider, set its key where needed, and choose a compatible model. For Ollama, install and start Ollama and download a model separately. The OpenAI adapter uses Chat Completions with JSON mode, so the selected model must support that API.

Provider quotas, model availability, billing, and data-use terms are set by the provider. The collector cannot determine your billing tier from a key. If AI fails, normal collection can publish a publisher excerpt; it does not switch to another provider automatically.

The CLI reads source definitions from `config/sources.json`. Each source has a name, feed URL, allowed `hosts`, and `enabled` flag. Allowed hosts must include the feed, redirects, and article hosts you intend to retrieve. Use the names from this file with `--test-ai SOURCE`.

## Collect, preview, and test

Normal collection matching desktop/server defaults:

```powershell
py -3 bot.py --per-source-limit 5 --max-age-hours 48
```

Every enabled source is checked. Eligible unsent articles and due retries are processed, up to five attempts per source. Successful deliveries are remembered across restarts. Publication dates must be valid, include a timezone, and fall within the chosen window; future dates are skipped.

**Bare `py -3 bot.py` has no article-count cap or age limit.** This preserves the original CLI behavior and can process many available feed articles on its first run. The desktop and container supply their own saved limits and 48-hour window.

| Task | Command |
|---|---|
| Check feeds without AI or publishing | `py -3 bot.py --check-feeds` |
| Preview eligible articles without sending | `py -3 bot.py --dry-run --per-source-limit 5 --max-age-hours 48` |
| Publish reports locally | `py -3 bot.py --local --per-source-limit 5 --max-age-hours 48` |
| Preview up to 3 articles total, allowing repeats | `py -3 bot.py --test-mode --max-posts 3 --max-age-hours 48 --dry-run` |
| Send up to 3 articles total, allowing repeats | `py -3 bot.py --test-mode --max-posts 3 --max-age-hours 48` |
| Preview up to 5 articles per source from 30 days | `py -3 bot.py --test-mode --per-source-limit 5 --max-age-hours 720 --dry-run` |
| Test AI using recent articles from Unit42 | `py -3 bot.py --test-ai Unit42 --max-age-hours 48` |
| Show every flag and allowed filter value | `py -3 bot.py --help` |

`--per-source-limit` accepts 1–100. `--max-posts` is a separate global test limit of 1–20 and requires `--test-mode`; if both are set, both limits apply. Test mode defaults to five total attempts when neither limit is supplied. The legacy `--batch` flag aliases `--max-posts`. `--backfill` has been removed, and the old `MAX_POSTS` environment value no longer controls normal collection.

Tests check every enabled feed and sample across sources. They can repeat delivered URLs, but each selected URL appears only once within a run. Successful test deliveries update history; failed tests do not change the normal retry queue. Increasing the age window only includes older articles still listed by feeds; it does not crawl a publisher's archive.

`--max-age-hours` accepts 1–48 for normal sending and up to 8760 (365 days) for previews, AI tests, or explicit test mode. Matching article filters still apply. For example:

```powershell
py -3 bot.py --per-source-limit 5 --max-age-hours 48 --sector-scope education --social-scope phishing
```

See the [scope catalog](SCOPES.md) for all seven flags. Omitting a scope means All; every selected scope must match before analysis and publishing.

## Output and delivery history

- `--dry-run` writes JSON/CSV reports to `preview/`. It sends no Discord messages and does not change delivery history. Configured AI still uses its provider quota.
- `--test-ai` writes `preview/ai-test.json` and `preview/ai-test.txt`, even if the selected article was already sent. It sends nothing and changes no delivery state. It tries eligible articles in the chosen source until one matches the filters; omit the source name to use the first enabled source. An AI fallback is a failed AI test with a nonzero exit code.
- `--local` publishes JSON reports in `results/`, with separate history in `state/local-state.json`. These files belong to the checkout, not the Windows app's separate profile.
- Discord delivery history and pending retries live in `state/state.json`. JSON/CSV files are not attached to Discord messages.

Do not delete delivery state to test AI or repeat a few articles; use the explicit test commands. Keep `.env`, preview files, and local state out of Git.

## Schedule on your computer

The CLI checks once and exits. Use the desktop's automatic checks or the container for built-in scheduling, or configure your operating system's scheduler below.

### Windows Task Scheduler

Create a task with an hourly trigger (or repeat every 30 minutes). Use the Windows account that owns the checkout. For a checkout at `C:\Tools\osint-digest`:

| Action field | Value |
|---|---|
| Program/script | Full Python executable path, shown by `py -3 -c "import sys; print(sys.executable)"` |
| Arguments | `"C:\Tools\osint-digest\bot.py" --per-source-limit 5 --max-age-hours 48` |
| Start in | `C:\Tools\osint-digest` |

Enable **Run task as soon as possible after a scheduled start is missed** and **Do not start a new instance** when already running. The PC must be awake and connected. A process lock also prevents simultaneous local runs.

### Linux cron

Use `crontab -e` and add an hourly entry, replacing the paths with your installation:

```cron
17 * * * * /usr/bin/python3 /absolute/path/osint-digest/bot.py --per-source-limit 5 --max-age-hours 48 >> /absolute/path/osint-digest/bot.log 2>&1
```

Use the account that owns the checkout and `.env`. Application resource paths are resolved from the project directory, so the cron working directory does not need to be that folder.

## GitHub Actions

This method runs the standalone CLI on GitHub-hosted runners using [.github/workflows/osint.yml](../.github/workflows/osint.yml). It does not run the Windows app or Docker service.

1. Fork this repository or copy the complete source into a repository you control. Enable Actions there. Do not upload your `.env` or local application data.
2. Under **Settings → Secrets and variables → Actions → Secrets**, add `DISCORD_WEBHOOK_URL`. Add the appropriate provider key secret if using AI: `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`.
3. Under **Variables**, set `AI_PROVIDER` to `none` or your cloud provider, and set `AI_MODEL` if using AI. The CLI's OpenAI/Claude adapters also require the variable `ALLOW_PAID_AI=true`. Local Ollama requires a separately reachable server and is not installed by this workflow.
4. To use the same article policy as desktop/server, edit the workflow's **Run collector** command before the first run:

   ```yaml
   run: python bot.py --per-source-limit 5 --max-age-hours 48
   ```

   The checked-in workflow currently runs bare `python bot.py`, which has no age or article-count limit. Keep the surrounding `env` settings and remaining workflow steps.

5. Ensure the workflow is allowed to write repository contents. It commits `state/state.json` after each run to remember deliveries and retries. Branch rules can prevent that commit; use a dedicated repository whose policies permit this workflow.
6. Open **Actions → OSINT Digest → Run workflow** on the default branch. This is a live collection run and sends eligible articles to the configured webhook.
7. After checking the result, set the repository variable `ENABLE_SCHEDULE=true` to enable scheduled checks. The included cron expression, `17 * * * *`, requests an hourly run at minute 17 UTC. Scheduled collection is otherwise off by default.

**Repository visibility matters:** committed state includes public article URLs, source status, timestamps, retry metadata, and Discord message IDs. In a public repository, that state is public. Credentials belong in Actions secrets and are not written to that state file. Check your account's runner usage and billing settings before enabling a schedule.

Scheduled workflows run from the default branch and may be delayed or dropped under load. GitHub can disable schedules in public repositories after 60 days without repository activity. Monitor workflow results rather than relying on exact delivery times. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The workflow has concurrency control and attempts to persist state even after partial collection failures. A failed state push needs attention because later runs may repeat deliveries. Avoid separate deployments sharing the same destination unless independent posts are intended.

## Reliability and troubleshooting

| Symptom | Check |
|---|---|
| No articles are sent | Review logs, the age window, selected filters, enabled sources, and prior delivery history. Use `--check-feeds` for feed access. |
| No AI output after enabling a provider | Run `--test-ai` with an enabled source. Normal collection does not regenerate previously sent articles. Check the key, model, quota, and CLI opt-in where required. |
| Duplicate messages | Check for multiple deployments, a lost state file, or failed GitHub state commits. Delivery is at least once: a crash after Discord accepts a message but before state is saved can repeat it. |
| A publisher fails | Other sources continue. Verify feed and article host allowlists; queued normal failures retain retry delays. CISA is disabled by default following a failed access check. |
| A preview contains unexpected IOCs | Read the original article. Extraction also finds benign services and shared infrastructure; candidates are not confirmed malicious indicators. |

Feed entries can disappear before a deployment discovers them. The collector watches new URLs; it does not detect edits to an already delivered article or merge different publishers' coverage of the same incident. HTML extraction does not read images, screenshots, PDFs, linked IOC files, or JavaScript-only content. It never follows extracted IOC URLs.

Pages are capped at 4 MB, IOC candidates at 2,000, and AI input at 24,000 characters. AI claims require supporting source substrings, but that check does not prove the claim follows from its evidence. Review important findings against the original article. Share short summaries and attribution rather than complete article copies.

Run offline tests with `python -m unittest -v`. See the [validation record](VALIDATION.md) for completed checks and limitations.
