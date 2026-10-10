# Validation record

Desktop 1.2 was checked on October 9, 2026 (America/New_York). Earlier validation dates are retained below.

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
