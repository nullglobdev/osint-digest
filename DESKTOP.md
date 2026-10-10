# OSINT Digest for Windows

## Install and connect

1. Download `OSINTDigest-Setup-1.2.0-x64.exe` from [GitHub Releases](https://github.com/ry304/osint-digest/releases/latest) and run it. Repository access is required because the repository is private. It installs for your Windows user, without requiring administrator rights. Windows 10/11 x64 is the target platform; Python is bundled.
2. Open **OSINT Digest** from the Start menu.
3. In **Connection**, paste your Discord channel webhook. Choose a summary provider, enter its **AI API key**, click **Refresh models**, and select a model. Click **Save connection**. Existing CLI users can select **Import connection from .env** to fill these fields from their own local file.
4. Click **Test Discord connection** to verify access without sending a message.
5. In **Sources**, enable the publishers you want or use **Add source** to add your own RSS/Atom feed. Use **Move up/down** to set batch priority, then **Save sources**. In **Dashboard**, choose 5 or 10 articles, then use **Preview batch**. Open **Previews** to read the summaries.
6. Click **Send latest batch** when ready. It generates a fresh summary and sends a separate Discord message for each selected article, without CSV or JSON attachments.

The portable alternative is `OSINTDigest-Portable-1.2.0-x64.zip`: extract the entire ZIP and run `OSINTDigest.exe` inside its folder. Keep the `_internal` folder beside the executable. No separate Python installation is needed.

## Everyday use

- **Test AI** summarizes one real article even when nothing is queued, saving a local preview.
- **Preview batch** analyzes the first article from each of the first N selected sources without sending messages. AI quota is still used.
- **Send latest batch** deliberately includes articles you have already sent. Use it for initial posts or testing.
- **Check & send new** checks all selected feeds and sends up to the chosen article limit. The first check establishes a quiet baseline; subsequent checks send newly discovered articles and due retries.
- **Start automatic checks** repeats the new-article check every 15 to 360 minutes. Select a preset or type a whole number. Keep the PC awake and online. Automatic checks are off each time you start the app.
- **Check feeds** tests publisher feed access without using AI or sending Discord messages.

**Run in background** hides the window in the Windows system tray near the clock; existing automatic checks continue. It does not start automatic checks by itself. The **Keep running in the tray when I close the window** option makes the X button do the same and saves immediately. The normal minimize button keeps the app in the taskbar. Click the tray icon to reopen the window, or right-click it to stop checks or exit. Opening the app again also restores its existing window. **Exit** stops future checks and waits for any current task to finish. This is not a Windows service: checks stop after Exit, sign-out, or shutdown and do not run during sleep.

Work runs in a separate hidden process, so the window remains responsive. Progress and errors appear in Activity. If a provider is unavailable, a normal batch can send publisher excerpts; Activity reports how many summaries versus excerpts were produced. AI Test reports a failure when it cannot generate an evidence-checked summary.

The desktop supports **Google Gemini, OpenAI, Anthropic Claude, local Ollama**, and **publisher excerpts without AI**. The generic API key field belongs to the selected provider; each provider keeps its own encrypted key and saved model. Switching providers never sends the previous provider's key to the new provider. Cloud calls use your own quota/billing; choosing OpenAI or Claude enables that provider in the desktop worker. The CLI still requires its explicit `ALLOW_PAID_AI` setting. Ollama must be running locally.

The model list refreshes from the selected provider at startup with a saved key, when you leave the key field, when you switch to a provider with a saved key, or when you click **Refresh models**. Ollama lists locally installed models. Saved model IDs remain editable if discovery is unavailable. The app filters non-text models where provider metadata or model naming identifies them, but listing a model does not guarantee JSON generation support or available quota. Use **Test AI** before sending.

For custom sources, enter a name and public HTTPS RSS/Atom URL. The feed hostname is added automatically. Add exact article and redirect hostnames separated by commas, then apply and **Save sources**. Run **Check feeds** to verify access and parsing. Normal article pages are not feeds. Existing source names stay fixed when editing to preserve delivery history. Disabling or removing a source leaves its history on disk.

## Appearance and accessibility

The workspace uses rounded navy panels, cyan accents, and a static radar illustration. At the top of the window, select **Dark**, **Light**, or **Windows** under Theme. Choose **Text size** from 100% to 200%; preferences save immediately. Windows contrast themes take priority over custom colors.

Use Tab/Shift+Tab to move between controls, Ctrl+1 through Ctrl+4 to switch sections, Ctrl+S to save, and F1 for **Keyboard help**. Focus has a visible outline and scrolls into view. Controls wrap at smaller widths and larger text sizes. The Activity panel has **Pause live activity updates** for reading without new log output appearing; collection continues.

The interface uses Qt controls with accessible names, roles, and states for Windows assistive technology. See [ACCESSIBILITY.md](ACCESSIBILITY.md) for tested features, keyboard instructions, and manual checks still required before claiming full Section 508 conformance.

## Your data

Desktop data lives in `%LOCALAPPDATA%\OSINTDigest`, separate from the CLI project:

- `settings.json`: connection settings; the webhook and each provider's API key are encrypted with Windows user-scoped DPAPI. Version 1.0 Gemini settings migrate automatically.
- `sources.json`: your selected and custom sources, allowed hosts, and source order.
- `state/state.json`: delivery history and queued retries.
- `preview/`: local reports.
- `activity.log`: the most recent operation, with saved credential values redacted.

No developer credentials, article previews, or delivery state are included in the installer. Each user supplies their own credentials. Local CLI history is not imported automatically. Uninstall removes the application and shortcuts but preserves your settings/history. If you want to remove those too, close the app and delete the app-data folder yourself. Moving encrypted settings to another account or computer may require entering credentials again.

This build is not code signed. Windows may display an unknown-publisher or reputation prompt. A public production release should use the publisher's code-signing certificate and be tested on a clean Windows VM. Current downloads are distributed through the private repository's GitHub Releases; they are available only to users with repository access.

## Build a release

Build on Windows x64 with Python 3.12 and [Inno Setup 6](https://jrsoftware.org/isdl.php) installed. Check the compiler's license for your distribution/use. The build tools are not required on end users' PCs.

```powershell
.\build_windows.ps1 -CompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The script creates `.build-venv`, installs the pinned build dependencies, runs the offline tests, generates the app icon, builds the PyInstaller app, compiles the installer, creates a portable ZIP, and writes `dist/SHA256SUMS.txt`.

The unpacked app is `dist/1.2.0/OSINTDigest/OSINTDigest.exe`. Versioned build folders allow an older copy to stay open during a build. Close the older app before reviewing the new version with the same profile. To run from source, install `requirements-desktop.txt` and run `py -3 desktop.py`.

Distribution files:

- `dist/installer/OSINTDigest-Setup-1.2.0-x64.exe`
- `dist/OSINTDigest-Portable-1.2.0-x64.zip`
- `dist/SHA256SUMS.txt`

`OSINTDigest.spec` uses an explicit resource allowlist. Do not add `.env`, app-data folders, `state`, `preview`, or credentials to it. For packaging validation, `OSINTDigest.exe --smoke-test --data-dir <temporary-folder>` initializes the GUI without showing its window, checks packaged resources, Windows encryption, the tray, and accessible field metadata, and writes `smoke-test.json`. It performs no network requests and sends no messages.

Implementation references: [PyInstaller bundling](https://pyinstaller.org/en/stable/usage.html), [Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), [Inno Setup](https://jrsoftware.org/isinfo.php).

Model discovery uses the official [Gemini models API](https://ai.google.dev/api/models), [OpenAI models API](https://developers.openai.com/api/reference/resources/models/methods/list), [Claude models API](https://platform.claude.com/docs/en/api/models/list), and [Ollama tags API](https://docs.ollama.com/api/tags). The UI and tray use [Qt Widgets](https://doc.qt.io/qt-6/qtwidgets-index.html).
