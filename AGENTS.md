# AGENTS.md

## Run

```bash
python src/main.py
```

## Architecture

Three source files in `src/`, zero external dependencies (Python stdlib only):

```
src/
├── config.py      — ConfigManager + HistoryManager + all defaults/constants
├── translator.py  — BaseTranslator ABC + 5 engine implementations + create_translator()
└── main.py        — tkinter UI: TranslatorApp, SettingsDialog, HistoryDialog
user_data/         — config.json and history.json (auto-generated at runtime, gitignored)
```

Entry point: `python src/main.py` (or `run.bat` which `cd`s into `src/` then uses `pythonw`).

`config.py` `BASE_DIR` points to project root (`src/`'s parent). User data lives in `user_data/` relative to that root. `save()` auto-creates the directory.

## Key conventions

- **No pip dependencies.** Keep the app on Python stdlib modules only.
- **Windows target.** DPI awareness via `ctypes.windll`, font is `Microsoft YaHei UI`.
- **Threading model.** Translation runs in `daemon=True` threads. UI updates via `root.after(0, callback)`. Never touch tkinter widgets from worker threads.
- **Config is king.** `config.json` is auto-generated on first run. `_merge_defaults` enforces strict key matching — old keys from renamed fields are silently dropped. If you rename a config field, users must delete `config.json`.
- **ENGINE_NAMES is mutable at runtime.** AI1/AI2 display names come from config's `name` field and are synced to the global `ENGINE_NAMES` dict via `_sync_ai_names()`. The engine combo reads `ENGINE_NAMES.values()`.

## Engine layer (`translator.py`)

- Each engine maps unified language codes (`zh`, `en`, etc.) to API-specific codes via `LANG_*` dicts. Add new languages in all 4 dicts.
- `OpenAITranslator` handles AI1; `AI2Translator` inherits from it (`name = "ai2"`). Domain field is injected into system prompt if non-empty.
- Google free endpoint is `translate.googleapis.com/translate_a/single` (GET, no auth). Cloud endpoint is `language/translate/v2` (POST, API key in header).
- DeepL and Google use `current_api` config field (not `api_type`) to select interface variant.
- `BaseTranslator._request()` handles GET (params → URL query) and POST (data → body). Timeout comes from top-level `request_timeout_seconds` (default: 30s).

## Settings dialog (`SettingsDialog`)

- All tab frames created at init, shown/hidden via `pack_forget`. Widget references persist across tab switches.
- `_collect_values()` reads ALL tabs unconditionally (not just active). This is intentional — prevents data loss on tab switch.
- `_build_ui()` creates `settings_status` and bottom buttons before the initial `_switch_tab()` call, so `_switch_tab()` can update status/test button state directly.
- Dialog height must accommodate the tallest tab (AI1/AI2 with name/key/url/model/domain/max_chars). Current: 500px.

## UI layout (`TranslatorApp._setup_ui`)

- Bottom bar packed first with `side=tk.BOTTOM` to prevent being pushed off-screen when window shrinks.
- Input/output `tk.Text` widgets fill remaining space (`fill=BOTH, expand=True`).
- Translate button is `tk.Button` (not ttk) for reliable color control (`bg="#0078D4"`). It stays enabled during translation and switches to terminate mode.
- Auto-translate debounce: `root.after(1000)` cancelled on each keystroke. History restore cancels pending auto-translate to avoid overwriting.
- Clipboard translation polls clipboard text using the configured `clipboard_poll_ms` interval and translates new text immediately.

## Gotchas

- `user_data/` may contain API keys and translation text — `.gitignore` excludes the whole directory.
- `run.bat` uses `pythonw` (no console). If Python is not in PATH, user must adjust.
- Baidu API requires MD5 signature: `hashlib.md5(appid + text + salt + secret_key)`.
- When adding a new engine: update `ENGINES` dict, `ENGINE_NAMES`, `DEFAULT_CONFIG`, `SettingsDialog.TABS/TAB_LABELS`, `_make_tab_frame`, `_collect_values`, and `_sync_ai_names` if it has a `name` field.
- The `json` import was removed from main.py — do not re-add unless needed.
- `DEFAULT_CONFIG` in `config.py` is the single source of truth for all config keys and their defaults. `_merge_defaults` walks it strictly — any key not in `DEFAULT_CONFIG` is dropped on load.
- Translation uses a `_translation_id` counter and current text checks to discard stale results when input changes mid-request or the user terminates translation. Clipboard translation queues a follow-up request when a translation is active.
- `_sanitize_config()` runs on startup and after settings save to clamp `current_engine`, `source_lang`, and `target_lang` to valid values.
- `_skip_next_auto_translate` flag prevents Enter-triggered translate from firing a second time via the auto-translate debounce. History restore also sets this flag.
- `_pending_translate_after_current` queues a follow-up translate when input changes during an active translation (clipboard or auto mode). `_finish_translation` drains this queue.
- Request config, including current engine config and `request_timeout_seconds`, is copied before passing to worker threads to avoid races with the settings dialog.
- `_unique_engine_name` deduplicates AI display names against built-in engine names, appending a numeric suffix if needed.
