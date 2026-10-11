# OSINT Digest for Windows

For continuous operation on a server without a GUI, use the separate [container edition](CONTAINER.md). The desktop and server share the collector but keep separate configuration and delivery history.

## Install and connect

1. Download the Windows installer from [GitHub Releases](https://github.com/nullglobdev/osint-digest/releases/latest) and run it. The build instructions below produce `OSINTDigest-Setup-1.8.0-x64.exe` for this source version. It installs for your Windows user, without requiring administrator rights. Windows 10/11 x64 is the target platform; Python is bundled.
2. Open **OSINT Digest** from the Start menu.
3. In **Connection**, choose a summary provider and configure its **AI API key** and model, or select **Publisher excerpts** to collect without AI. Leave **Discord webhook URL** blank to publish in the app's **Results** tab. Add a webhook if you want Discord delivery. Click **Save connection**. Existing CLI users can select **Import from .env** to fill these fields from their own local file.
4. If using Discord, **Test Discord connection** verifies access without sending a message.
5. In **Sources**, enable the publishers you want or use **Add source** to add your own RSS/Atom feed, then **Save sources**. Every enabled source is checked.
6. Set **Articles per source** on the Dashboard (1–100, default 5), then click **Collect new**. The header shows the destination: **Publish in Results** or **Publish to Discord**. Discord receives a separate message per article, without CSV or JSON attachments. Local publishing saves the article in Results for reading now or after restarting the app.

The portable alternative is `OSINTDigest-Portable-1.8.0-x64.zip`: extract the entire ZIP and run `OSINTDigest.exe` inside its folder. Keep the `_internal` folder beside the executable. No separate Python installation is needed.

## Everyday use

- **Articles per source** is always visible on the Dashboard and saves immediately. It caps eligible article attempts from each source during every manual or automatic check, including retries, previews, and Dev mode resends. For example, 5 with 10 enabled sources can publish up to 50 articles per check.
- **Filters** provides independent Sector, Threat actor, Social engineering, Access & exploitation, Malware & impact, Other styles, and Education combinations dropdowns. Each defaults to **All**. Every selected scope must match; aliases within an option are alternatives. Filtering happens before AI analysis, and only matches consume article limits. Choices save immediately. Use **View selected keywords** or **Reset all filters**. The Dashboard shows the number of active scopes and an **Article filters** shortcut. See [SCOPES.md](SCOPES.md).
- **Collect new** checks every enabled feed and selects the newest unsent articles published within the last **48 hours**, up to the per-source limit. Successful deliveries are remembered across restarts. Remaining eligible articles wait for later checks; expired retries are removed from the queue.
- **Results** contains articles published locally when the webhook is blank. Search by title or publisher, select an article to read its summary, references and IOC candidates, and click the article, CVE, or ATT&CK links to open them in your default browser. **Open source article** opens the publisher's page too. Tab through the reader's links and press Enter for keyboard access. The reader refreshes as articles arrive and preserves your selected article. Existing results remain available when you add a webhook. The Filters tab also controls this view; reset all filters to show all saved articles again.
- Local publication and Discord delivery have separate histories. Saving an article locally does not mark it sent to Discord. Adding a webhook later can send articles previously published only in the app. Clearing a webhook uses the existing local history again.
- **Preferences → Enable Dev mode** reveals the **Previews** tab and Dashboard **Preview** and **Test AI** actions. Previews use configured AI quota but never publish results or change delivery history. These tools are hidden and cannot run through the desktop worker while Dev mode is off.
- In **Preferences > Developer tools**, enable Dev mode and set **Test article timeframe** to 1-365 days (default 2). This lookback applies to **Preview**, **Test AI**, and **Collect test articles**. Enable **Allow resends for manual tests**, then choose **Collect test articles** on the Dashboard to publish within that timeframe. Normal **Collect new** and automatic checks always use 48 hours. The timeframe saves immediately; Allow resends starts off each time the app opens. All selected scopes and the per-source article limit still apply. Successful tests update delivery history; failed tests do not change normal retries.
- **Start automatic checks** repeats the new-article check every 15 to 360 minutes. Select a preset or type a whole number. Keep the PC awake and online. Automatic checks are off each time you start the app.
- **Check feeds** tests publisher feed access without using AI or sending Discord messages.

**Run in background** hides the window in the Windows system tray near the clock; existing automatic checks continue. It does not start automatic checks by itself. The **Keep running in the tray when I close the window** option makes the X button do the same and saves immediately. The normal minimize button keeps the app in the taskbar. Click the tray icon to reopen the window, or right-click it to stop checks or exit. Opening the app again also restores its existing window. **Exit** stops future checks and waits for any current task to finish. This is not a Windows service: checks stop after Exit, sign-out, or shutdown and do not run during sleep.

Normal collection on the first run and upgrades follows the same limit and 48-hour window. Dev previews and tests use the selected test timeframe. Increasing it only includes older articles still listed in publisher feeds; it does not retrieve a publisher archive. Selection remains newest first, so increase the per-source limit or narrow the source/sector selection if newer articles fill the test limit. Publication dates must include a timezone; missing, invalid, future, and older dates are skipped with a note in Activity. Atom updated dates do not make older articles eligible again. The age is rechecked before publishing, including after AI generation. Existing Results and successful delivery history remain intact. An older saved test article count becomes the new per-source limit on upgrade.

Work runs in a separate hidden process, so the window remains responsive. Progress and errors appear in Activity. If a provider is unavailable, a run can send publisher excerpts; Activity reports how many summaries versus excerpts were produced. AI Test reports a failure when it cannot generate an evidence-checked summary.

The desktop supports **Google Gemini, OpenAI, Anthropic Claude, local Ollama**, and **publisher excerpts without AI**. The generic API key field belongs to the selected provider; each provider keeps its own encrypted key and saved model. Switching providers never sends the previous provider's key to the new provider. Cloud calls use your own quota/billing; choosing OpenAI or Claude enables that provider in the desktop worker. The CLI still requires its explicit `ALLOW_PAID_AI` setting. Ollama must be running locally.

The model list refreshes from the selected provider at startup with a saved key, when you leave the key field, when you switch to a provider with a saved key, or when you click **Refresh models**. Ollama lists locally installed models. Saved model IDs remain editable if discovery is unavailable. The app filters non-text models where provider metadata or model naming identifies them, but listing a model does not guarantee JSON generation support or available quota. Use **Test AI** before sending.

For custom sources, enter a name and public HTTPS RSS/Atom URL. The feed hostname is added automatically. Add exact article and redirect hostnames separated by commas, then apply and **Save sources**. Run **Check feeds** to verify access and parsing. Normal article pages are not feeds. Existing source names stay fixed when editing to preserve delivery history. Disabling or removing a source leaves its history on disk.

## Appearance and accessibility

The compact desktop workspace uses rounded navy panels, cyan accents, a small header, and tighter controls and spacing. Open **Preferences** to select **Dark**, **Light**, or **Windows** under Theme and choose **Text size** from 100% to 200%. Preferences save immediately. Windows contrast themes take priority over custom colors.

Use Tab/Shift+Tab to move between controls, Ctrl+1 through Ctrl+5 for Dashboard, Connection, Sources, Results, and Preferences; Ctrl+6 opens Previews in Dev mode; Ctrl+7 opens Filters. Ctrl+S saves connection/source settings; F1 opens **Keyboard help**. Focus has a visible outline and scrolls into view. Controls wrap at smaller widths and larger text sizes. **Preferences → Pause live activity updates** pauses the Activity log display while collection continues. Background behavior and Dev mode are also in Preferences.

The interface uses Qt controls with accessible names, roles, and states for Windows assistive technology. See [ACCESSIBILITY.md](ACCESSIBILITY.md) for tested features, keyboard instructions, and manual checks still required before claiming full Section 508 conformance.

## Your data

Desktop data lives in `%LOCALAPPDATA%\OSINTDigest`, separate from the CLI project:

- `settings.json`: connection settings; the webhook and each provider's API key are encrypted with Windows user-scoped DPAPI. Version 1.0 Gemini settings migrate automatically.
- `sources.json`: your selected and custom sources, allowed hosts, and source order.
- `state/state.json`: delivery history and queued retries.
- `results/`: durably published local articles shown in Results.
- `state/local-state.json`: local publishing history and retries, separate from Discord's `state/state.json`.
- `preview/`: developer previews; separate from published Results.
- `activity.log`: the most recent operation, with saved credential values redacted.

No developer credentials, article previews, or delivery state are included in the installer. Each user supplies their own credentials. Local CLI history is not imported automatically. Uninstall removes the application and shortcuts but preserves your settings/history. If you want to remove those too, close the app and delete the app-data folder yourself. Moving encrypted settings to another account or computer may require entering credentials again.

This build is not code signed. Windows may display an unknown-publisher or reputation prompt. A production release should use the publisher's code-signing certificate and be tested on a clean Windows VM. Published downloads are distributed through GitHub Releases.

## Build a release

Build on Windows x64 with Python 3.12 and [Inno Setup 6](https://jrsoftware.org/isdl.php) installed. Check the compiler's license for your distribution/use. The build tools are not required on end users' PCs.

```powershell
.\scripts\build_windows.ps1 -CompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The script creates `.build-venv`, installs the pinned build dependencies, runs the offline tests, generates the app icon, builds the PyInstaller app, compiles the installer, creates a portable ZIP, and writes `dist/SHA256SUMS.txt`.

The unpacked app is `dist/1.8.0/OSINTDigest/OSINTDigest.exe`. Versioned build folders allow an older copy to stay open during a build. Close the older app before reviewing the new version with the same profile. To run from source, install `requirements/desktop.txt` and run `py -3 desktop.py`.

Distribution files:

- `dist/installer/OSINTDigest-Setup-1.8.0-x64.exe`
- `dist/OSINTDigest-Portable-1.8.0-x64.zip`
- `dist/SHA256SUMS.txt`

`packaging/windows/OSINTDigest.spec` uses an explicit resource allowlist. Do not add `.env`, app-data folders, `state`, `preview`, or credentials to it. For packaging validation, `OSINTDigest.exe --smoke-test --data-dir <temporary-folder>` initializes the GUI without showing its window, checks packaged resources, Windows encryption, the tray, and accessible field metadata, and writes `smoke-test.json`. It performs no network requests and sends no messages.

Implementation references: [PyInstaller bundling](https://pyinstaller.org/en/stable/usage.html), [Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), [Inno Setup](https://jrsoftware.org/isinfo.php).

Model discovery uses the official [Gemini models API](https://ai.google.dev/api/models), [OpenAI models API](https://developers.openai.com/api/reference/resources/models/methods/list), [Claude models API](https://platform.claude.com/docs/en/api/models/list), and [Ollama tags API](https://docs.ollama.com/api/tags). The UI and tray use [Qt Widgets](https://doc.qt.io/qt-6/qtwidgets-index.html).
