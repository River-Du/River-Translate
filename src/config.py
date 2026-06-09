"""
配置管理与翻译历史管理
"""

import copy
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---- 默认配置 ----
DEFAULT_MAX_CHARS = 5000
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CLIPBOARD_POLL_MS = 500
MIN_CLIPBOARD_POLL_MS = 100
MAX_CLIPBOARD_POLL_MS = 5000
DEFAULT_HISTORY_MAX_ITEMS = 30
MIN_HISTORY_MAX_ITEMS = 1
MAX_HISTORY_MAX_ITEMS = 200

RANGED_INT_FIELDS = {
    "clipboard_poll_ms": (
        DEFAULT_CLIPBOARD_POLL_MS,
        MIN_CLIPBOARD_POLL_MS,
        MAX_CLIPBOARD_POLL_MS,
    ),
    "history_max_items": (
        DEFAULT_HISTORY_MAX_ITEMS,
        MIN_HISTORY_MAX_ITEMS,
        MAX_HISTORY_MAX_ITEMS,
    ),
}

BOOL_FIELDS = (
    "always_on_top",
    "auto_translate",
    "auto_copy",
    "clipboard_translate",
)


def _coerce_ranged_int(value, default, min_value, max_value):
    if type(value) is int and min_value <= value <= max_value:
        return value
    return default


DEFAULT_CONFIG = {
    "current_engine": "google",
    "source_lang": "auto",
    "target_lang": "zh",
    "always_on_top": False,
    "auto_translate": False,
    "auto_copy": False,
    "clipboard_translate": False,
    "request_timeout_seconds": DEFAULT_REQUEST_TIMEOUT_SECONDS,
    "clipboard_poll_ms": DEFAULT_CLIPBOARD_POLL_MS,
    "history_max_items": DEFAULT_HISTORY_MAX_ITEMS,
    "engines": {
        "google": {"api_key": "", "current_api": "free", "max_chars": DEFAULT_MAX_CHARS},
        "baidu": {"app_id": "", "secret_key": "", "max_chars": DEFAULT_MAX_CHARS},
        "deepl": {"api_key_free": "", "api_key_pro": "", "current_api": "free", "max_chars": DEFAULT_MAX_CHARS},
        "ai1": {
            "name": "自定义AI1",
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "domain": "",
            "max_chars": DEFAULT_MAX_CHARS,
        },
        "ai2": {
            "name": "自定义AI2",
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "domain": "",
            "max_chars": DEFAULT_MAX_CHARS,
        },
    },
}


# ============================================================
#  配置管理
# ============================================================
class ConfigManager:
    """负责 config.json 的读写，缺失时自动补默认值"""

    def __init__(self, path=None):
        self.path = Path(path) if path else BASE_DIR / "user_data" / "config.json"

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._merge_defaults(data)
        except (OSError, json.JSONDecodeError):
            return self._copy_default()

    def save(self, config):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ------- private -------

    def _merge_defaults(self, loaded):
        """严格合并：仅保留默认配置中存在的 key，自动清理过期字段"""
        result = self._copy_default()
        if not isinstance(loaded, dict):
            return result

        loaded_engines = loaded.get("engines", {})
        if not isinstance(loaded_engines, dict):
            loaded_engines = {}

        for key in DEFAULT_CONFIG:
            if key not in loaded:
                continue
            if key != "engines":
                result[key] = loaded[key]
                continue

            for eng, defaults in DEFAULT_CONFIG["engines"].items():
                engine_loaded = loaded_engines.get(eng, {})
                if not isinstance(engine_loaded, dict):
                    continue
                # 仅保留该引擎默认中存在的字段
                result["engines"][eng].update(
                    {field: engine_loaded[field] for field in defaults if field in engine_loaded}
                )
        self._normalize_top_level_fields(result)
        return result

    @staticmethod
    def _normalize_top_level_fields(config):
        timeout = config.get("request_timeout_seconds")
        if type(timeout) is not int or timeout <= 0:
            config["request_timeout_seconds"] = DEFAULT_REQUEST_TIMEOUT_SECONDS
        for field, (default, min_value, max_value) in RANGED_INT_FIELDS.items():
            config[field] = _coerce_ranged_int(config.get(field), default, min_value, max_value)
        for field in BOOL_FIELDS:
            if type(config.get(field)) is not bool:
                config[field] = DEFAULT_CONFIG[field]

    @staticmethod
    def _copy_default():
        return copy.deepcopy(DEFAULT_CONFIG)


# ============================================================
#  翻译历史管理
# ============================================================
class HistoryManager:
    """记录最近 N 条翻译历史，存 history.json"""

    def __init__(self, path=None, max_items=DEFAULT_HISTORY_MAX_ITEMS):
        self.path = Path(path) if path else BASE_DIR / "user_data" / "history.json"
        self.max_items = _coerce_ranged_int(
            max_items,
            DEFAULT_HISTORY_MAX_ITEMS,
            MIN_HISTORY_MAX_ITEMS,
            MAX_HISTORY_MAX_ITEMS,
        )

    def get_all(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict)][: self.max_items]

    def add(self, entry):
        if not isinstance(entry, dict):
            return
        history = self.get_all()
        history.insert(0, entry)
        if len(history) > self.max_items:
            history = history[: self.max_items]
        self._save(history)

    def clear(self):
        self._save([])

    # ------- private -------

    def _save(self, history):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
