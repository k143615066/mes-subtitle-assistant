# MES Subtitle Assistant

Internal subtitle-processing application for TreeMES marketing videos. It accepts a Chinese SRT file, automatically optimizes the Chinese wording, lets the user proofread it, then produces English subtitles and a readable English subtitle version.

## User Workflow

1. Start the application.
2. Open `http://localhost:15000` in a browser.
3. Upload a Chinese `.srt` subtitle file.
4. Wait for the AI Chinese subtitle optimization.
5. Review and correct the Chinese subtitles.
6. Download the three delivered files:
   - `中文_<name>.srt`
   - `英文_<name>.srt`
   - `英文_可读优化版_<name>.srt`

The readable English version is the recommended English delivery file. It groups fragmented English into readable subtitle units while preserving the original meaning and timing span.

For a Chinese end-user guide, see [USER_GUIDE_CN.md](USER_GUIDE_CN.md).

## Required Before First Use

- Python 3.10 or later
- A DeepSeek API key
- Internet access to the configured DeepSeek API endpoint

The application is a local web service bound to `127.0.0.1`. Subtitle files stay on the user's computer; the subtitle text is sent to DeepSeek for Chinese optimization, English translation, and English readability optimization using the configured API key.

## API Key Setup

1. Copy `.env.example` to a new file named `.env` in the project root.
2. Set the following value in `.env`:

```text
DeepSeek_Key=your_actual_api_key
```

Never share or commit `.env`.

## Repository Deployment

This repository is the distribution format for colleagues. Each colleague clones the project to their own computer, creates a local `.env` file with their authorized API key, and starts the application locally. The editable MES glossary is part of the repository, so approved terminology changes can be committed and shared through the normal Git workflow.

Do not commit local runtime data or secrets. The included `.gitignore` excludes `.env`, uploaded subtitles, generated subtitles, logs, local models, Python virtual environments, and release archives.

## GitHub Publishing

Create an empty GitHub repository. Do not initialize it with a README, `.gitignore`, or license, because this project already includes those files. Then connect this local project and push its `main` branch:

```bash
git remote add origin https://github.com/<account-or-organization>/<repository>.git
git push -u origin main
```

Repository settings:

- This distribution repository is **Public**, so colleagues can download or clone it without a GitHub account. Anyone can view its source code and bundled MES terminology, so do not add confidential customer information or internal materials that are not approved for public sharing.
- Do not add `.env` or API keys to GitHub. Each user creates their own local `.env` from `.env.example`.
- Colleagues only need a GitHub account if they will directly push glossary or code changes. For normal use, they can open the public repository in Codex and ask it to clone and start the project.
- Use the `main` branch as the shared release branch. Review and commit glossary edits before asking colleagues to pull updates.

## Windows

Double-click [start_server.bat](00_Server/start_server.bat). The first startup creates a local Python environment and installs the dependencies. When the browser address is displayed, open `http://localhost:15000`.

## macOS

In Terminal, from the project root, run:

```bash
chmod +x 00_Server/start_server.sh
./00_Server/start_server.sh
```

The script creates `00_Server/.venv`, installs dependencies, loads `.env`, and starts the service. Open `http://localhost:15000`.

If macOS reports that Python is missing, install Python 3.10 or later first. The subtitle workflow itself is cross-platform.

## Editable TreeMES Glossary

The default terminology is a separate editable file:

[TreeMES_MES_Glossary.md](00_Server/data/glossary/TreeMES_MES_Glossary.md)

Edit the table's `中文术语` and `推荐英文` columns to add or change preferred translations. The file is loaded automatically for Chinese optimization, English translation, and English readability optimization.

The initial glossary contains 130 TreeMES terms consolidated from the approved English MES product overview, operation guides, Smart Light installation guides, and independent ESOP solution materials. The application also provides a `MES术语库` page for adding, editing, searching, and deleting terms without opening the Markdown file. Changes are written back to this repository file, so they can later be shared through Git commits.

The glossary page is intentionally a shared project resource, not a separate per-user upload. When one colleague updates terminology, review the changed Markdown file and commit it to GitHub so other colleagues can pull the update. Concurrent edits to the same term should be resolved through Git before use.

## Release Scope

This colleague-facing release includes only the required workflow: SRT upload, AI Chinese optimization, Chinese proofreading, English translation, English readability optimization, three-file download, and editable MES glossary management. It does not include audio/video transcription, custom glossary upload, history, feedback, correction corpus management, manual subtitle splitting, time-axis merging, or runtime quality-report downloads.

## Project Files

```text
00_Server/app/                   Flask application
00_Server/data/glossary/         Editable default MES glossary
00_Server/start_server.bat       Windows launcher
00_Server/start_server.sh        macOS launcher
.env.example                     Safe environment configuration template
```

Runtime uploads, generated subtitles, logs, local environments, legacy local models, and API keys are deliberately excluded from version control and the release package.
