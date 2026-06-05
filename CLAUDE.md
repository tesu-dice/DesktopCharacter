# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DesktopCharacter is a Windows-only Python application that places an always-on-top transparent character on the desktop. The character chats with the user via an LLM (Gemini API or local Ollama), is voiced through TTS (VOICEVOX or Windows Narrator), and passively logs user activity (active window, playing media, time) to enable personal knowledge management features and context-aware conversation.

Primary language is Japanese — code comments, log messages, prompts, UI text, and dev docs are all in Japanese. Preserve this when editing.

## Common Commands

```powershell
# Run the app (uses .venv per README)
python main.py

# Install dependencies
pip install -r requirements.txt
# Additional libs the README mentions but aren't in requirements.txt: pywin32, simpleaudio, google-generativeai, Pillow

# Build a single-file Windows executable (release process)
pyinstaller main.py --noconsole --onefile
```

Python 3.9.13 is required — `winrt` (used to read currently-playing media from the Windows Action Center) only supports Python 3.7–3.9 per the README.

There is no automated test suite. The `tests/` directory contains ad-hoc experimental scripts (RAG prototypes, transcription experiments, Google Calendar trials) — not pytest cases. Manual verification on Windows is the only validation path.

## Release Process (from README §リリース / アップデート手順)

1. Manually debug.
2. Update the user-facing readme (`配布時添付ファイル/readme_説明.html`).
3. Bump `CURRENT_APP_VERSION` in `main.py` (`myapp.app_start_message`, currently format `YYYYMMDD`).
4. Cut a new GitHub release on `tesu-dice/DesktopCharacter_forRelease` — `services/release_check.py` polls that repo's latest tag at startup and shows an update-available popup.
5. Build with `pyinstaller main.py --noconsole --onefile`, copy the bundle to a laptop, verify, then update the Booth product files.

## Architecture

The app is organized around two mechanisms, not direct calls between modules:

**`myapp` as AppContext (`main.py`)** — single instance that owns the `EventBus`, `UserSettings`, and every service/manager. Subsystems get `bus` + `setting` injected in their constructors; they never reach back into `main`.

**`EventBus` (`services/Event_Bus.py`)** — pub/sub with three subscription styles, all of which run listeners in daemon threads (this is intentional, to keep the Tk UI responsive):

- `subscribe(event, fn)` — fan-out listener.
- `subscribe_workflow(trigger, handler, response_event)` — runs `handler`, then auto-publishes its return value under `response_event`. Used to parallelize info-gathering (e.g. window/media/time queried at the same time and then joined).
- `subscribe_when([eventA, eventB, ...], fn)` — only fires once *all* listed events have published; collects their args in declared order and forwards them.

Listeners run in threads, so anything that touches Tk widgets must marshal back via `self.ui.after(...)` or it will crash on Windows.

`main.py:_setup_event_listeners` is the single source of truth for the wiring graph — read it first to understand any data flow. Notable chains:

- **Startup**: `application start` → `ui.start_TTS_Server` (boots VOICEVOX subprocess) → publishes `Start_TTS_Server` → `app_start_message` (version check + AI connection test + popup).
- **User message (no RAG, no ReAct)**: `MessageInput` → `Check_responseMode` → `Response_RAGisOFF` → joined with `MessageInput` → `AI_Manager.response` → `AIGenerateMessage` → `talk_window.add_log` + `ui.Reflect_Text` (TTS + character image).
- **User message with RAG**: `MessageInput` → `make_rag_request` → `Req_RAGInfo` → `UserDataLogger.handle_rag_request` → `RAGisReady` → joined with `MessageInput` → `AI_Manager.response_withRAG`.
- **Periodic activity log** (every 5 min from `myapp.update`): `Req_UserActivityLog` fans out via workflow to `get_activate_window`, `get_plaing_media`, `get_datetime`; their three response events are joined and passed to `UserDataLogger.add_userlog`.
- **Settings change**: `SettingsUpdated` is broadcast — `AI_Manager`, `UI`, and `myapp` all re-init from the new `UserSettings` instance.

### Subsystems

- `services/config_controller.py` — `UserSettings` flattens the nested JSON in `config.json` into a `path → SettingItem` map (e.g. `"ApplicationSettings.Permission.UserActivityLog"`). Defaults live in `get_default_data()`; `config.json` is merged on top. Always read via `setting.get_setting_value("dotted.path")` and never via raw dict access.
- `ai/AI_main.py` — `AI_Manager` is the AI facade. It picks a backend (`AI_geminiAPI` or `AI_ollama`) per `LLMSettings.Service`, owns conversation history, builds the system prompt from `Character_setting.txt` plus the filenames in `立ち絵/<Folder>/` (the AI is told to prefix replies with `<filename>：` so `UI.Reflect_Text` can swap the character image), and implements the ReAct loop in `react_planing()`.
- `ai_tools/` — pluggable tool system for ReAct. `ToolExecutor` discovers any `BaseTool` subclass in any `.py` in this directory at startup. A tool is only exposed to the LLM if `ApplicationSettings.Permission.<tool.name>` is `True` in settings — the permission key must match the tool's `name` property.
- `services/WindowsInfoCollecter.py` — Windows-only context capture (`win32gui` for active window, `winrt` for now-playing media, `screeninfo` for multi-monitor geometry).
- `services/UserDataLogger.py` — per-day JSON in `user_logs/YYYY-MM-DD.json` with three buckets (`logs`, `hourlogs`, `daylogs`). The hourly/daily summary path goes through the AI: `Req_UserSummaryLog_context` → `AI_Manager.response_onetime` → `add_summary_log`.
- `ui/UI_main.py` — `UI` extends `tk.Tk`, runs as a transparent fullscreen always-on-top window (uses `-transparentcolor` with `#888888` background) so the character image floats freely. Drag, right-click menu, and TTS dispatch live here. `UI_talk`, `UI_settings`, `UI_characterImage` are child windows/widgets.
- `ui/TTS_VoiceVoxEngine.py` / `TTS_WindowsNarratorManager.py` — TTS backends. VOICEVOX is launched as a subprocess (`engine_process`) at startup if `VoiceSettings.VOICEVOX.autorun` is true; it must be cleanly shut down via the configured path.

### Adding a new ReAct tool

1. Create `ai_tools/<my_tool>.py` with a class extending `BaseTool` (see `ai_tools/tool_base.py`). Implement `name`, `description`, `args_schema`, `execute(args)`.
2. Add a matching boolean to `ApplicationSettings.Permission.<name>` in `services/config_controller.py:get_default_data()` and (if you want it on by default) `config.json`. `ToolExecutor.init_tools_descriptions()` hides any tool whose permission flag is missing/false.
3. No registration step needed — `ToolExecutor._discover_tools()` finds it automatically.

### Adding a new event-driven flow

Wire it in `main.py:_setup_event_listeners`, not inside the producer or consumer module. Producers `publish`, consumers `subscribe` — they should not know about each other. Use `subscribe_workflow` when you need a response event auto-published, and `subscribe_when` when multiple inputs must converge.

## Reference Docs in This Repo

- `README.md` — concept, install notes, release procedure, history.
- `gemini.md` — instructions originally written for Gemini-based assistants; relevant guidance: prefer reading files over modifying them when answering questions, and produce diffs/separate files rather than direct edits when the user hasn't explicitly authorized changes.
- `開発予定/ARCHITECTURE_REFACTORING.md` — the design rationale behind the `myapp` + `EventBus` split (already implemented).
- `開発予定/DEVELOPMENT_GUIDE.md` — RAG feature walkthrough used as a template for new-feature work.
- `開発ログ/` — historical decision logs by topic (EventBus introduction, user data collection, ReAct implementation, settings UI rework).

## Things to Watch For

- `config.json` currently contains a real Gemini API key. Do not echo it back, log it, or include it in commits. If you edit `config.json` for any reason, leave the key field alone.
- The codebase has many `debug=-1` parameters threaded through call sites — `-1` means off; `0` or higher enables indented `print()` tracing. Preserve this convention when modifying signatures.
- File paths in code use forward slashes and project-relative paths (e.g. `立ち絵/<Folder>`). The app uses a `basedir` block that handles both regular and PyInstaller-frozen execution — copy that pattern if you add a new entry point.
- Japanese folder/file names (`立ち絵`, `開発ログ`, `開発予定`, `配布時添付ファイル`) are load-bearing — `AI_Manager.load_imgs` reads from `立ち絵/<Folder>` by string. Don't rename them.
