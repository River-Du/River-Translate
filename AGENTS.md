# AGENTS.md

## Run

```bash
python src/main.py
```

Python 3.8+ required. No install step — run directly from repo root. `run.bat` uses `pythonw` (no console window).

No tests, linter, type checker, or CI exist in this repo. Changes are verified by running the app manually.

## Architecture

Three source files in `src/`, zero external dependencies (Python stdlib only):

```
src/
├── config.py      — ConfigManager + HistoryManager + all defaults/constants
├── translator.py  — BaseTranslator ABC + 5 engine implementations + create_translator()
└── main.py        — tkinter UI: TranslatorApp, SettingsDialog, HistoryDialog
user_data/         — config.json and history.json (auto-generated at runtime, gitignored)
```

`config.py` `BASE_DIR` points to project root when run from source, and to the exe directory when frozen by PyInstaller. `RESOURCE_DIR` points to bundled resources in frozen mode. User data lives in `user_data/` relative to `BASE_DIR`. `save()` auto-creates the directory.

## Key conventions

- **No pip dependencies.** Keep the app on Python stdlib modules only.
- **Windows target.** DPI awareness via `ctypes.windll`, font is `Microsoft YaHei UI`.
- **Threading model.** Translation runs in `daemon=True` threads. UI updates via `root.after(0, callback)`. Never touch tkinter widgets from worker threads.
- **Config is king.** `config.json` is auto-generated on first run. `_merge_defaults` enforces strict key matching — old keys from renamed fields are silently dropped. If you rename a config field, users must delete `config.json`.
- **ENGINE_NAMES is mutable at runtime.** AI1/AI2 display names come from config's `name` field and are synced to the global `ENGINE_NAMES` dict via `_sync_ai_names()`. The engine combo reads `ENGINE_NAMES.values()`.

## Engine layer (`translator.py`)

- Unified language codes (`zh`, `en`, etc.) mapped to API-specific codes via `LANG_*` dicts. Add new languages in `config.py` `LANGUAGES` and every engine language map in `translator.py`; DeepL has separate source and target maps because target English must use a regional code. `VALID_LANGUAGE_CODES` is derived from `LANGUAGES`.
- `OpenAITranslator` handles AI1; `AI2Translator` inherits from it. Domain field injected into system prompt if non-empty.
- Google free: `translate.googleapis.com/translate_a/single` (GET, no auth). Cloud: `language/translate/v2` (POST, API key in header).
- DeepL and Google use `current_api` field (not `api_type`) to select interface variant.

## Settings dialog (`SettingsDialog`)

- All tab frames created at init, shown/hidden via `pack_forget`. Widget references persist across tab switches.
- `_collect_values()` reads ALL tabs unconditionally (not just active) — prevents data loss on tab switch.
- Uses `_make_row` for AI tabs (label+entry same row) vs `_make_stacked_entry` for built-in engine tabs (label above entry). Match the pattern when adding fields.

## UI layout (`TranslatorApp._setup_ui`)

- Bottom bar packed first with `side=tk.BOTTOM` to prevent being pushed off-screen when window shrinks.
- Translate button is `tk.Button` (not ttk) for color control — stays enabled during translation, switches to terminate mode.
- Auto-translate debounce: `root.after(1000)` cancelled on each keystroke. History restore cancels pending auto-translate to avoid overwriting.

## Gotchas

- `user_data/` may contain API keys and translation text — `.gitignore` excludes the whole directory.
- `run.bat` uses `pythonw` (no console). If Python is not in PATH, user must adjust.
- Baidu API requires MD5 signature: `hashlib.md5(appid + text + salt + secret_key)`.
- When adding a new engine: update `ENGINES` dict, `ENGINE_NAMES`, `DEFAULT_CONFIG`, `SettingsDialog.TABS/TAB_LABELS`, `_make_tab_frame`, `_collect_values`, and `_sync_ai_names` if it has a `name` field.
- `DEFAULT_CONFIG` in `config.py` is the single source of truth for all config keys. `_merge_defaults` walks it strictly — any key not in `DEFAULT_CONFIG` is dropped on load. If you rename a config field, users must delete `config.json`.
- Translation uses a `_translation_id` counter and current text checks to discard stale results when input changes mid-request or the user terminates translation.
- Request config, including current engine config and `request_timeout_seconds`, is deep-copied before passing to worker threads to avoid races with the settings dialog.
- `ConfigManager.load()` normalizes `current_engine`, `source_lang`, and `target_lang` to valid values; history restore still uses local UI fallbacks for old records.
- `_unique_engine_name` deduplicates AI display names against built-in engine names, appending a numeric suffix if needed.
- `build.bat` deletes the entire `dist/` before each build — any `user_data/` inside it (from a previous packaged run) is lost.
