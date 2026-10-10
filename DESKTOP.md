# OSINT Digest for Windows

## Install and connect

1. Download `OSINTDigest-Setup-1.0.0-x64.exe` from [GitHub Releases](https://github.com/ry304/osint-digest/releases/latest) and run it. Repository access is required because the repository is private. It installs for your Windows user, without requiring administrator rights. Windows 10/11 x64 is the target platform; Python is bundled.
2. Open **OSINT Digest** from the Start menu.
3. In **Connection**, paste your Discord channel webhook and Gemini API key, then click **Save connection**. Existing CLI users can select **Import connection from .env** to fill these fields from their own local file.
4. Click **Test Discord connection** to verify access without sending a message.
5. In **Sources**, select the publishers you want. In **Dashboard**, choose 5 or 10 articles, then use **Preview batch**. Open **Previews** to read the summaries.
6. Click **Send latest batch** when ready. It generates a fresh summary and sends a separate Discord message for each selected article, without CSV or JSON attachments.

The portable alternative is `OSINTDigest-Portable-1.0.0-x64.zip`: extract the entire ZIP and run `OSINTDigest.exe` inside its folder. Keep the `_internal` folder beside the executable. No separate Python installation is needed.

## Everyday use

- **Test AI** summarizes one real article even when nothing is queued, saving a local preview.
- **Preview batch** analyzes the first article from each of the first N selected sources without sending messages. AI quota is still used.
- **Send latest batch** deliberately includes articles you have already sent. Use it for initial posts or testing.
- **Check & send new** checks all selected feeds and sends up to the chosen article limit. The first check establishes a quiet baseline; subsequent checks send newly discovered articles and due retries.
- **Start automatic checks** repeats the new-article check at the selected interval. Keep the app open, the PC awake, and the connection available. Closing the app stops the timer; automatic checks are off each time you open the app.
- **Check feeds** tests publisher feed access without using AI or sending Discord messages.

Work runs in a separate hidden process, so the window remains responsive. Progress and errors appear in Activity. Let a task finish before closing. If a provider is unavailable, a normal batch can send publisher excerpts; Activity reports how many summaries versus excerpts were produced. AI Test reports a failure when it cannot generate an evidence-checked summary.

The desktop interface supports Gemini, publisher excerpts without AI, and local Ollama. The original CLI still supports its additional providers. Gemini uses your own provider quota/billing. Ollama must be running locally with the selected model installed.

## Your data

Desktop data lives in `%LOCALAPPDATA%\OSINTDigest`, separate from the CLI project:

- `settings.json`: connection settings; the webhook and Gemini key are encrypted with Windows user-scoped DPAPI.
- `sources.json`: your selected sources.
- `state/state.json`: delivery history and queued retries.
- `preview/`: local reports.
- `activity.log`: the most recent operation, with saved credential values redacted.

No developer credentials, article previews, or delivery state are included in the installer. Each user supplies their own credentials. Local CLI history is not imported automatically. Uninstall removes the application and shortcuts but preserves your settings/history. If you want to remove those too, close the app and delete the app-data folder yourself. Moving encrypted settings to another account or computer may require entering credentials again.

This build is not code signed. Windows may display an unknown-publisher or reputation prompt. A public production release should use the publisher's code-signing certificate and be tested on a clean Windows VM. Current downloads are distributed through the private repository's GitHub Releases; they are available only to users with repository access.

## Build a release

Build on Windows x64 with Python 3.12 (including Tcl/Tk) and [Inno Setup 6](https://jrsoftware.org/isdl.php) installed. Check the compiler's license for your distribution/use. The build tools are not required on end users' PCs.

```powershell
.\build_windows.ps1 -CompilerPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
```

The script creates `.build-venv`, installs the pinned build dependencies, runs the offline tests, generates the app icon, builds the PyInstaller app, compiles the installer, creates a portable ZIP, and writes `dist/SHA256SUMS.txt`.

Distribution files:

- `dist/installer/OSINTDigest-Setup-1.0.0-x64.exe`
- `dist/OSINTDigest-Portable-1.0.0-x64.zip`
- `dist/SHA256SUMS.txt`

`OSINTDigest.spec` uses an explicit resource allowlist. Do not add `.env`, app-data folders, `state`, `preview`, or credentials to it. For packaging validation, `OSINTDigest.exe --smoke-test --data-dir <temporary-folder>` creates a withdrawn GUI, checks packaged resources and Windows encryption, and writes `smoke-test.json`. It performs no network requests and sends no messages.

Implementation references: [PyInstaller bundling](https://pyinstaller.org/en/stable/usage.html), [Windows DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), [Inno Setup](https://jrsoftware.org/isinfo.php).
