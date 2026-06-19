"""
配置管理与翻译历史管理
"""

import copy
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = BASE_DIR

APP_ICON_PATH = RESOURCE_DIR / "assets" / "app.ico"

# ---- 默认配置 ----
DEFAULT_MAX_CHARS = 5000
MIN_ENGINE_MAX_CHARS = 100
MAX_ENGINE_MAX_CHARS = 100000
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CLIPBOARD_POLL_MS = 500
MIN_CLIPBOARD_POLL_MS = 100
MAX_CLIPBOARD_POLL_MS = 5000
DEFAULT_HISTORY_MAX_ITEMS = 50
MIN_HISTORY_MAX_ITEMS = 1
MAX_HISTORY_MAX_ITEMS = 200

LANGUAGES = {
    "auto": "自动检测",
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "ru": "俄语",
    "es": "西班牙语",
}
VALID_LANGUAGE_CODES = tuple(LANGUAGES)

CONFIG_INT_FIELDS = {
    "request_timeout_seconds": (DEFAULT_REQUEST_TIMEOUT_SECONDS, 1, None),
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

ENGINE_INT_FIELDS = {
    "max_chars": (DEFAULT_MAX_CHARS, MIN_ENGINE_MAX_CHARS, MAX_ENGINE_MAX_CHARS),
}

INT_FIELD_SPECS = {**CONFIG_INT_FIELDS, **ENGINE_INT_FIELDS}

BOOL_FIELDS = (
    "always_on_top",
    "auto_translate",
    "auto_copy",
    "clipboard_translate",
)

ENGINE_API_MODES = {
    "google": ("free", "cloud"),
    "deepl": ("free", "pro"),
}

HISTORY_STRING_FIELDS = (
    "source_text",
    "source_lang",
    "target_text",
    "target_lang",
    "engine",
    "time",
)

HISTORY_DEDUPE_FIELDS = (
    "source_text",
    "source_lang",
    "target_lang",
    "engine",
)


def _int_in_range(value, min_value, max_value):
    if type(value) is not int:
        return False
    if value < min_value:
        return False
    return max_value is None or value <= max_value


def _coerce_choice(value, choices, default):
    return value if isinstance(value, str) and value in choices else default


def coerce_config_int(field, value):
    default, min_value, max_value = INT_FIELD_SPECS[field]
    if _int_in_range(value, min_value, max_value):
        return value
    return default


def parse_config_int(field, value):
    _default, min_value, max_value = INT_FIELD_SPECS[field]
    try:
        parsed = int(str(value).strip())
    except (ValueError, TypeError):
        raise ValueError(config_int_requirement(field))
    if _int_in_range(parsed, min_value, max_value):
        return parsed
    raise ValueError(config_int_requirement(field))


def config_int_requirement(field):
    _default, min_value, max_value = INT_FIELD_SPECS[field]
    if max_value is None and min_value == 1:
        return "大于 0 的整数"
    if max_value is None:
        return f"大于等于 {min_value} 的整数"
    return f"{min_value} ~ {max_value} 的整数"


DEFAULT_CONFIG = {
    "current_engine": "google",
    "source_lang": "auto",
    "target_lang": "auto",
    "always_on_top": True,
    "auto_translate": True,
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
            "base_url": "",
            "model": "",
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
            return True
        except OSError:
            return False

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
        self._normalize_config(result)
        return result

    @staticmethod
    def _normalize_config(config):
        for field in CONFIG_INT_FIELDS:
            config[field] = coerce_config_int(field, config.get(field))
        for field in BOOL_FIELDS:
            if type(config.get(field)) is not bool:
                config[field] = DEFAULT_CONFIG[field]
        config["current_engine"] = _coerce_choice(
            config.get("current_engine"),
            DEFAULT_CONFIG["engines"],
            DEFAULT_CONFIG["current_engine"],
        )
        config["source_lang"] = _coerce_choice(
            config.get("source_lang"),
            VALID_LANGUAGE_CODES,
            DEFAULT_CONFIG["source_lang"],
        )
        config["target_lang"] = _coerce_choice(
            config.get("target_lang"),
            VALID_LANGUAGE_CODES,
            DEFAULT_CONFIG["target_lang"],
        )

        ConfigManager._normalize_engine_fields(config)

    @staticmethod
    def _normalize_engine_fields(config):
        engines = config.get("engines", {})
        if not isinstance(engines, dict):
            config["engines"] = ConfigManager._copy_default()["engines"]
            return

        for engine, defaults in DEFAULT_CONFIG["engines"].items():
            engine_config = engines.get(engine)
            if not isinstance(engine_config, dict):
                engines[engine] = copy.deepcopy(defaults)
                continue

            for field, default in defaults.items():
                value = engine_config.get(field)
                if field == "max_chars":
                    engine_config[field] = coerce_config_int("max_chars", value)
                elif field == "current_api":
                    modes = ENGINE_API_MODES.get(engine, ())
                    engine_config[field] = value if isinstance(value, str) and value in modes else default
                elif isinstance(default, str) and not isinstance(value, str):
                    engine_config[field] = default

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
        self.max_items = coerce_config_int("history_max_items", max_items)

    def get_all(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        history = []
        for entry in data:
            if isinstance(entry, dict):
                history.append(self._normalize_entry(entry))
        return history[: self.max_items]

    def add(self, entry):
        if not isinstance(entry, dict):
            return
        history = self.get_all()
        normalized = self._normalize_entry(entry)
        dedupe_key = self._dedupe_key(normalized)
        history = [item for item in history if self._dedupe_key(item) != dedupe_key]
        history.insert(0, normalized)
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

    @staticmethod
    def _normalize_entry(entry):
        normalized = dict(entry)
        for field in HISTORY_STRING_FIELDS:
            value = normalized.get(field, "")
            if value is None:
                normalized[field] = ""
            else:
                normalized[field] = value if isinstance(value, str) else str(value)
        return normalized

    @staticmethod
    def _dedupe_key(entry):
        return tuple(entry.get(field, "") for field in HISTORY_DEDUPE_FIELDS)
