# Validation record

Checked in the build environment on October 9, 2026 UTC.

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
- CISA’s feed returned HTTP 403 and remains disabled in `sources.json`.
- Gemini has now been tested with user credentials as described above; other model adapters, Windows Task Scheduler and GitHub Actions execution remain untested here. Discord transport is covered by mocked tests; this AI test did not exercise live delivery.
- Live article body extraction was sampled for Microsoft and Huntress, not validated across every publisher/layout. There is no measured IOC precision/recall benchmark.
- AI evidence matching checks source substring presence, not logical entailment. Summaries require review.
- The generic extractor does not cover images, PDFs or linked IOC files. See README for other coverage and delivery limitations.

`feed-checks.json` preserves the direct feed probe results. An HTTP/feed success is not a promise that every article on that site can be retrieved.

## Windows desktop packaging

- Built the x64 app with Python 3.12.10 and PyInstaller 6.22.3, and the per-user installer with Inno Setup 6.7.3.
- Source and packaged GUI smoke tests initialized all four tabs, loaded the public source list, verified a DPAPI round trip, and confirmed that a fresh profile has no credentials.
- Installed into an isolated test folder using the actual installer; the installed executable passed the same smoke test.
- Reinstalled the final build, repeated the installed smoke test, and uninstalled successfully. Test profile data was preserved. A packaged launch with no Python-specific environment or PATH passed. Release-file checks found no private credential values or local config/state/preview files, and the portable ZIP passed its integrity check.
- The installed worker successfully fetched all ten enabled publisher feeds. No Discord messages or credentialed AI calls were made during desktop packaging validation.
- GUI tests exercise worker launch, displayed activity, automatic-check scheduling/stopping, and missing-connection validation. Connection setup can scroll at smaller window sizes.
- Automated screenshot inspection could not activate the hidden test window (`failed to activate captured window`). Visual inspection was not completed through that tool.
- This is a locally tested, unsigned Windows build. A separate clean Windows VM and signing certificate were not available for release certification. The installer and portable ZIP are local artifacts, not a published public download.
