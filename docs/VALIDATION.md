# Validation record

Earlier validation dates and release-specific results are retained below.

## Desktop 1.8.1: Dashboard filters

Validated on October 11, 2026:

- Moved all seven article filters, active-scope count, keyword help, and reset action to the Dashboard. Removed the separate Filters tab. Wider windows place filters beside the collection controls; smaller windows and larger text stack the cards vertically.
- Windows suite: 176 tests collected, 175 passed, one POSIX-only permissions test skipped. Checks cover Dashboard ownership of every filter, unchanged saved selections and Results/Previews filtering, Ctrl+7 focus on the Dashboard, Tab/arrow navigation, and focus visibility at 200% text in a 640×480 window.
- Reviewed dark/light Dashboard renders at 1040×740 and the enlarged-text layout. Collection, automatic checks, filters, and Activity remain accessible. The packaged startup check also verifies that all filters belong to the Dashboard. Collection and server filtering behavior are unchanged.


## Desktop 1.8.0 and server 1.6.0: independent article scopes

- Windows suite: 176 tests collected, 175 passed, one POSIX-only permissions test skipped. All 119 core/server tests passed in a network-disabled Linux container, including the extracted server bundle. Container acceptance checks passed.
- Seven independent selectors default to All: Sector, Threat actor, Social engineering, Access & exploitation, Malware & impact, Other styles, and Education combinations. Tests cover every supplied alias, whole-word boundaries, context qualifiers, AND across scopes, OR within options, and education concept co-occurrence in either order.
- Shared collector tests verify filtering of full article text before AI and reporting, per-source limits counting only matches, selection changes reconsidering excluded articles, preserved normal deduplication, Dev previews/AI tests, local Results, and two-webhook delivery from one analysis. Old cached reports cannot bypass new filters; their existing analysis is reused after full-body validation. Missing metadata falls back safely in the reader.
- Desktop tests cover migration from sector-only profiles, saving all selectors without saving unfinished credentials, worker flags for every action, filtering Results and Previews, reset without deleting reports, accessible names, Ctrl+7/Tab/arrow navigation, and focus scrolling after form rows wrap at 200% text. Reviewed dark/light Filters layouts and the compact Dashboard.
- Server settings migrate in memory to schema 5, preserving the existing sector and defaulting new scopes to All. Interactive menus expose every option and a reset action. Saved filter combinations apply to all normal/test tasks and enabled webhooks; CLI tests validate independent flags and reject unknown options.
- Builds contain only allowlisted application files. The 21 recorded private configuration/history/preview files remain unchanged, and repository files passed a credential scan. No live AI requests or Discord messages were made. These are keyword relevance filters, not confirmed actor attribution or semantic scoring.

## Desktop 1.7.0 and server 1.5.0: adjustable test timeframe

Validated on October 10, 2026:

- Windows suite: 157 tests collected, 156 passed, one POSIX-only permissions test skipped. All 104 core/server tests passed in a network-disabled Linux container.
- Built Windows 1.7.0 installer/portable packages and the server 1.5.0 source bundle. The packaged Windows executable passed native startup, encryption, tray, accessibility, and test-timeframe checks from a fresh profile outside the repository. The extracted server bundle passed all 104 tests and built its Docker image. Container acceptance checks passed. All 21 tracked private configuration/history/preview files remain unchanged, and the repository passed a credential scan.
- Dev tools provide a persistent 1-365 day test timeframe, defaulting to two days when upgrading an older profile. It applies to previews, AI tests, and explicit manual test collection. Normal collection and automatic checks retain the 48-hour window. Hidden Dev actions remain blocked in the worker.
- Tests verify older articles can be selected within the configured timeframe, unknown/future/out-of-window dates remain excluded, previews leave delivery history unchanged, explicit tests can repeat articles, normal checks return to 48 hours, and age is rechecked after AI and before each webhook. Server commands and interactive menus pass a per-invocation timeframe without changing the schedule.
- The new control has an accessible label, keyboard input, range validation, and immediate persistence without saving unfinished credentials. Dashboard text reflects the active manual test window. Reviewed Dev preferences in dark/light themes and at 200% text in a small window.
- Validation uses offline publisher, AI, and Discord fixtures; no live messages or AI requests were needed. Expanding the window filters entries still present in current publisher feeds and does not implement historical archive crawling.

## Desktop 1.6.0 and server 1.4.0: sector scopes and working article links

Validated on October 10, 2026:

- Windows suite: 148 tests collected, 147 passed, one POSIX-only permissions test skipped. All 97 core/server tests passed in a network-disabled Linux container. Container acceptance checks also passed.
- Built the Windows 1.6.0 executable, installer, and portable ZIP. The executable passed native packaged startup from outside the repository with a fresh profile: GUI/resources, DPAPI, tray, accessible scope and article-limit controls, 25 scope choices, the 48-hour window, and no credentials. The extracted server 1.4.0 bundle passed all 97 included tests with networking disabled and built its own Docker image successfully.
- The full supplied catalog is covered: 16 sectors, seven education groups, combined Education mode, and None. Tests verify broad education keyword matches, whole-word boundaries, common plurals, explicit parenthetical qualifiers, full-body matching before AI, unmatched articles not consuming limits, scope changes, no-filter defaults, normal deduplication, and Dev/test date and limit enforcement.
- Scope applies to collection, previews, AI tests, local Results, and all server webhooks. Cached reports cannot bypass a changed scope, and existing AI summaries are reused after validation. Previously excluded articles are reconsidered under a different scope or None. Previews leave delivery history unchanged.
- Mouse tests activate original-article, CVE, technique, and sub-technique links through the Qt default-browser opener. Keyboard tests traverse every link with Tab and activate it with Enter. Invalid targets are ignored, browser failures display feedback, and links retain the correct contrast when switching themes.
- Rendered dark/light Results and the Dashboard were reviewed, including the sector selector at 200% text in a small window. Tests verify accessible scope labeling, immediate preference persistence without saving unfinished credentials, and filtering of both Results and Previews without deleting files. Full screen-reader/conformance testing remains a separate manual check.
- Validation uses mock publisher, AI, and Discord transports. No live AI requests or Discord messages were made. All 21 previously recorded private configuration, history, and preview files remain unchanged; repository files passed a credential scan.

## Desktop 1.5.0 and server 1.3.0: per-source limits and recent articles

Validated on October 10, 2026:

- Windows suite: 125 tests collected, 124 passed, one POSIX-only permissions test skipped. All 81 core/server tests passed in the Linux image with networking disabled.
- New regression coverage includes independent limits per source, newest-first selection, normal deduplication across restarts, local Results, Dev/test resends, preview isolation, expired retries, timezone offsets, the exact 48-hour boundary, unknown/future dates, RSS/Atom publication formats, and articles that age out during AI generation. Atom updated timestamps do not override publication age.
- Both editions enforce the same policy. Windows worker tests verify the required limit/window flags and reject resend actions outside Dev mode. Server integration tests cover the per-source limit across multiple webhooks. Older saved article counts migrate to per-source settings without rewriting secrets during loading.
- The Dashboard limit is visible without Dev mode, has an accessible name, saves immediately, and fits the compact layout. Reviewed the rendered 1040×740 Dashboard. Existing theme, keyboard, large-text, and accessibility regression tests passed.
- Built the Windows 1.5.0 executable, installer, and portable ZIP. The packaged executable passed native startup checks from outside the repository with a fresh profile and no Python environment: GUI/resources, encryption, tray, accessible article limit, and empty credentials.
- Rebuilt the Linux image; offline container acceptance passed, including independent webhook receipts, cached-report recovery, persistent settings/history, private files, process locks, backups, and graceful restart. No live Discord messages or AI calls were made. Existing user configuration, history, previews, and the running 1.4.0 app were preserved.

## Server 1.2.0: multiple Discord webhooks

Validated on October 10, 2026:

- Windows suite: 110 tests collected, 109 passed, one POSIX-only permissions test skipped. The 68 core/server tests also passed inside the Linux image with networking disabled.
- Added regression checks for fan-out of a single report, per-webhook receipts and backoff, partial failures, cached reports on retry, adding/pausing/removing/re-adding destinations, token rotation and renaming, legacy history migration before a settings edit, test-mode repeats, preview isolation, connection checks, and credential-safe menus/logging.
- Rebuilt the Docker image and passed offline container acceptance: non-root/read-only operation, private configuration, no bundled GUI or secrets, locking, backups, restart persistence, and stopping between webhooks. On resume, the already acknowledged webhook was skipped and the saved report was reused.
- Completed the real interactive container setup using two fake webhook URLs with network access disabled. Both destinations appeared by name, their URLs stayed hidden, and a paused 360-minute schedule saved successfully. No live Discord messages or AI requests were made.
- Existing local credentials, desktop profile, and delivery/preview files were preserved. Multiple-webhook configuration applies to the server; the desktop and standalone CLI retain their single-webhook settings.

## Desktop 1.4: compact layout and in-app publishing

Checked October 10, 2026 (America/New_York).

- The desktop defaults to a 1040×740 window with compact controls, a small header, and reduced spacing. Results provides search, a split article reader, formatted publication times, references, and defanged IOC values. Preferences contains appearance/accessibility controls, background behavior, and Dev mode. Preview tools and their worker actions are gated by Dev mode.
- Windows suite: 95 tests collected, 94 passed, one POSIX-only permissions test skipped. New coverage includes durable local publishing without a webhook, deduplication after reloading history, separation from Discord delivery history, recovery from local write failures, preview isolation, worker routing and Dev mode enforcement, Results search/selection, escaped article markup, and compact Dashboard layout.
- Visual checks cover the compact Dashboard, Results reader, and Preferences in dark/light themes, plus 200% text in a smaller window. Existing accessibility tests cover keyboard navigation, focus scrolling, text enlargement, contrast overrides, and accessible control metadata. Full assistive-technology certification remains outside this validation.
- The Windows 1.4 executable passed native packaged startup checks for GUI/resources, DPAPI, tray, and accessibility metadata. Its worker refused a preview with Dev mode disabled. Packaged collector, UI, worker, settings, reader, and theme code were compared with the final source. Installer and portable ZIP builds succeeded.
- The shared collector passed all 53 core/server tests in a network-disabled Linux container, and the updated Docker image passed container acceptance checks. No real Discord posts or AI calls were used. Existing local credentials, delivery history, and previews were verified unchanged.

## Delivery behavior update: desktop 1.3 and server 1.1

Checked October 10, 2026 (America/New_York).

- Normal runs check all enabled sources and attempt every eligible unsent article, including on first discovery. Tests cover more than five deliveries, repeat runs loading history from disk, duplicate URLs shared by feeds, disabled sources, an unavailable publisher, due versus delayed retries, legacy baselines, conditional feed requests, and stale retry entries for already-sent articles.
- Limited repeat delivery requires explicit Test mode in the CLI, desktop controls, or server menu/command. Tests verify all feeds are still checked, a limit may exceed the number of sources, successful test posts are recorded, previews leave history unchanged, and failed repeat tests do not create normal retries. Desktop and server automatic checks always use normal mode.
- Windows suite: 84 tests collected, 83 passed, one POSIX-only permissions test skipped. The core/server suite passed all 50 tests in a network-disabled Linux container. No real Discord messages or AI calls were used.
- The rebuilt Docker image passed offline container acceptance checks for private settings, persistent delivery history after restart, process locking, backup, and graceful shutdown. Normal and Test mode dashboard layouts were visually reviewed in dark and light themes; accessible names follow the changing Send button label.
- The Windows 1.3.0 executable passed packaged startup checks from outside the repository without Python-specific environment settings: GUI/resources, Windows credential encryption, tray, accessibility metadata, and an empty credential profile. The installer and portable ZIP were built. The extracted server 1.1.0 bundle passed all 50 included tests in Linux with networking disabled.
- Existing local credentials, delivery history, and previews (21 previously recorded files) were verified unchanged. Test output lives under ignored `.work/delivery/`.


## Repository organization update

Checked October 10, 2026 (America/New_York).

- Application code now lives in the `osint_digest` package with shared core, desktop, and server subpackages. Root launchers preserve the existing CLI commands. Guides, tests, sources, dependency lists, and Windows packaging files have their own folders.
- The Windows suite collected 75 tests: 74 passed and the POSIX-permissions test was skipped. Regression coverage includes the new `config/sources.json` location and loading an existing server volume's original `server.json` and history without modification.
- Source and newly packaged Windows executables passed native GUI/resource, encryption, tray, and accessibility-metadata startup checks. The packaged executable was tested from a separate working directory without Python-specific environment settings. The relocated Inno Setup definition compiled successfully into an isolated test installer.
- The reorganized Docker image passed the offline container acceptance checks. The rebuilt/extracted server source bundle passed all 43 included core/server tests in Linux with networking disabled. The image excludes the desktop package and local Python bytecode caches.
- Relative documentation links were checked. The publisher-source configuration and 21 existing local credential/state/preview files were verified unchanged. Existing published downloads were preserved; validation builds and historical local test artifacts are grouped under ignored `.work/` folders.

## Headless container edition

Checked October 10, 2026 UTC using Linux containers on Docker Desktop (Engine 29.7.2, Compose 5.5.1) and the Python 3.12 slim Bookworm base image.

- The Windows suite collected 73 tests: 72 passed and the POSIX-permissions test was skipped. The Linux container suite collected 52 core/server/model tests: 48 passed and four Windows-only desktop settings tests were skipped. Linux tests ran with networking disabled and a read-only application filesystem.
- Server tests cover fresh paused setup, inherited credential isolation, provider-specific keys, billing opt-in, configuration validation and concurrent-edit detection, custom sources and model selection, private Linux file modes, paused-service configuration reload, duplicate-process locks, health status, backups, preview/history isolation, credential redaction, and finishing the current post before stopping.
- Built the actual image and ran the supplied Compose service with an isolated test volume. Verified UID/GID 10001, mode 0600 configuration, read-only application files, no Qt/GUI dependencies, and no private developer configuration in the image.
- `python scripts/test_container.py` passed offline container acceptance checks for persistent settings/history after restart, rejection of a second daemon sharing the volume, noninteractive password-input refusal, mocked end-to-end delivery and queue recovery, backup, and clean SIGTERM shutdown. All test containers had networking disabled; no real Discord messages or AI calls were made.
- The real interactive `docker compose run --rm digest setup` wizard completed in a terminal, preserved hidden webhook input, and saved a 360-minute interval and paused schedule. The running service loaded the changed settings without rebuilding its image.
- The downloadable server source archive was extracted into an isolated folder, built successfully as its own Docker image, and passed all 41 bundled core/server tests inside a network-disabled Linux container. The archive uses an explicit allowlist and Linux shell line endings.
- Live AI/provider generation and Discord posting were not retested for this container edition. ARM64 and a separate production Linux host were not tested. The existing collector's at-least-once delivery and extraction limitations still apply.

## Desktop 1.2.0 interface update

- All 52 offline tests passed in the pinned Windows build environment. The Qt interface preserves provider credentials, model discovery, source configuration, worker routing, scheduling, and tray behavior.
- New widget tests check keyboard navigation, section shortcuts, source toggling, accessible names/roles and password/disabled states, changing Start/Stop button names, text enlargement to 200%, focus scrolling at 640 x 480, and pausing log updates even when a new task starts. Appearance changes save without committing unfinished connection edits.
- Both navy/dark and light palettes pass automated checks for text contrast of at least 4.5:1 and control/focus boundaries against their surrounding surfaces of at least 3:1. Windows contrast-theme override logic is tested with a mocked platform preference.
- Rendered offscreen previews of all four sections in both themes and an enlarged-text view were inspected. These are Qt-rendered artifacts, not captures of the running Windows desktop. The review found and corrected font sizing and scrolling issues.
- Portable and installed 1.2 executables passed native Windows GUI/resource, DPAPI, system-tray, and accessible API-key-field metadata checks with a fresh profile and no Python-specific environment or PATH. No AI or Discord requests were made.
- The installer installed into an isolated workspace folder and uninstalled successfully, with application closing explicitly disabled during the test. The portable ZIP passed integrity, required Qt plugin/artwork/license, private-file exclusion, and local-credential exclusion checks.
- Native Narrator/NVDA interaction, actual Windows contrast/DPI changes, and a complete manual accessibility review remain untested. This release implements accessibility improvements; it is not a completed ACR or a claim of full Section 508 conformance. See [ACCESSIBILITY.md](ACCESSIBILITY.md).
- This remains an unsigned Windows build. Qt/PySide6/Shiboken 6.12.0 replace the previous Tk/pystray interface; the shared runtime libraries and license notices are included.

## Desktop 1.1.0 update

- All 45 tests passed in the pinned Windows build environment. New coverage includes provider-specific credential isolation, legacy Gemini settings migration, model discovery and pagination, invalid custom sources, source ordering and persistence, the 360-minute limit, tray lifecycle, and orderly exit with an active worker.
- OpenAI and Claude desktop generation paths passed mocked end-to-end adapter tests, including grounded output and provider authentication. Live calls to those providers were not tested because their keys were not supplied.
- Live Gemini model discovery returned 32 text-model candidates, including the configured model. Model discovery did not generate a summary or send a Discord message.
- Final portable and installed executables passed GUI/resource, DPAPI, and real Windows tray startup checks with a fresh profile and no Python-specific environment or PATH. Fresh profiles contained no credentials.
- The 1.1.0 installer installed into an isolated workspace test folder and uninstalled successfully. Existing application data and the running 1.0 app were preserved.
- The portable ZIP passed its integrity check. Source files and the unpacked ZIP were checked against local credential values; private settings, .env, state, and preview paths were excluded. The tray library is bundled as replaceable source with its license notices.
- Visual screenshot review could not run: the Computer Use helper returned "native pipe is unavailable" / Windows error 2, including after reconnecting. GUI behavior is covered by automated tests; a complete visual review remains outstanding.

The records below describe earlier collector and 1.0 packaging validation.

## Passed

- Python compilation.
- 28 offline unit tests (`python -m unittest -v`), including AI testing with an empty delivery queue, failure reporting, preservation of delivery history, 5/10-source batches, dry-run behavior, partial batch delivery recovery, Windows console encoding, defanging limited to indicator values, Windows encrypted credential storage, desktop task routing, and automatic-check controls.
- A five-source batch preview generated live Gemini summaries for Microsoft, Google, Huntress, Proofpoint and SOCRadar. This exposed a Windows console encoding failure in preview logging, which was fixed and verified by replaying the five saved live results without additional API calls. Final replay: 5 previews, 5 AI summaries, 0 errors. Delivery state remained byte-for-byte unchanged and no batch messages were posted during validation.
- Live RSS XML retrieval from all ten enabled publishers; the collector parsed publisher-allowlisted article URLs from all ten.
- A live, no-AI, no-Discord dry run queued one article from each source without changing delivery state.
- Huntress article extraction produced 14 IOC candidates from the sampled article. Candidate count is not a precision or recall score.
- Microsoft’s first extraction selected recommendation cards. This was fixed by preferring the publisher’s content container and adding a regression test. Reprocessing the same retrieved HTML then extracted 40,051 characters and 42 IOC candidates from the main article body.
- Mocked failed delivery retained the queued article with retry metadata and did not mark it sent.
- A separate mocked successful delivery recorded the returned message ID and removed the queue entry.
- Discord payload generation respects tested embed field/aggregate sizes, suppresses mentions, and sends an embed without file attachments.
- On October 8, 2026 (America/New_York), `py -3 bot.py --test-ai` successfully called Gemini `gemini-3.1-flash-lite` on a live Microsoft article. It returned 3 summary, 2 affected, 1 actor, 3 technique and 3 action claims whose evidence passed substring validation. The article exceeded the AI input limit, so the head/tail truncation notice appeared as expected. The SHA-256 of `state/state.json` was identical before and after. No Discord message was sent by this test.

## Observed limitations

- Google’s feed was accessible, but its sampled article returned a short “Site Unavailable” page in this environment. Article processing rejected it and retained it for retry. Deployment from another host may differ.
- CISA’s feed returned HTTP 403 and remains disabled in `config/sources.json`.
- Gemini has now been tested with user credentials as described above; other model adapters, Windows Task Scheduler and GitHub Actions execution remain untested here. Discord transport is covered by mocked tests; this AI test did not exercise live delivery.
- Live article body extraction was sampled for Microsoft and Huntress, not validated across every publisher/layout. There is no measured IOC precision/recall benchmark.
- AI evidence matching checks source substring presence, not logical entailment. Summaries require review.
- The generic extractor does not cover images, PDFs or linked IOC files. See README for other coverage and delivery limitations.

[validation/feed-checks.json](validation/feed-checks.json) preserves the direct feed probe results. An HTTP/feed success is not a promise that every article on that site can be retrieved.

## Windows desktop packaging

- Built the x64 app with Python 3.12.10 and PyInstaller 6.22.3, and the per-user installer with Inno Setup 6.7.3.
- Source and packaged GUI smoke tests initialized all four tabs, loaded the public source list, verified a DPAPI round trip, and confirmed that a fresh profile has no credentials.
- Installed into an isolated test folder using the actual installer; the installed executable passed the same smoke test.
- Reinstalled the final build, repeated the installed smoke test, and uninstalled successfully. Test profile data was preserved. A packaged launch with no Python-specific environment or PATH passed. Release-file checks found no private credential values or local config/state/preview files, and the portable ZIP passed its integrity check.
- The installed worker successfully fetched all ten enabled publisher feeds. No Discord messages or credentialed AI calls were made during desktop packaging validation.
- GUI tests exercise worker launch, displayed activity, automatic-check scheduling/stopping, and missing-connection validation. Connection setup can scroll at smaller window sizes.
- Automated screenshot inspection could not activate the hidden test window (`failed to activate captured window`). Visual inspection was not completed through that tool.
- This is a locally tested, unsigned Windows build. A separate clean Windows VM and signing certificate were not available for release certification. The installer and portable ZIP are local artifacts, not a published public download.
