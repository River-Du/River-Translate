"""
翻译引擎层 - 内置 DeepL / 百度 / 谷歌 / 自定义AI1 / 自定义AI2 五种引擎
零外部依赖：仅使用 Python 标准库
"""

import hashlib
import html
import json
import random
import urllib.request
import urllib.parse
import urllib.error
from abc import ABC, abstractmethod

from config import DEFAULT_REQUEST_TIMEOUT_SECONDS, LANGUAGES

# ============================================================
#  API 语言代码映射
# ============================================================
LANG_DEEPL = {
    "auto": None, "zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO",
    "fr": "FR", "de": "DE", "ru": "RU", "es": "ES",
}

LANG_BAIDU = {
    "auto": "auto", "zh": "zh", "en": "en", "ja": "jp", "ko": "kor",
    "fr": "fra", "de": "de", "ru": "ru", "es": "spa",
}

LANG_GOOGLE = {
    "auto": "auto", "zh": "zh", "en": "en", "ja": "ja", "ko": "ko",
    "fr": "fr", "de": "de", "ru": "ru", "es": "es",
}

DEFAULT_ENGINE_NAMES = {
    "google": "谷歌翻译",
    "baidu": "百度翻译",
    "deepl": "DeepL",
    "ai1": "自定义AI1",
    "ai2": "自定义AI2",
}
ENGINE_NAMES = dict(DEFAULT_ENGINE_NAMES)

BAIDU_AUTH_ERROR_CODES = ("52003", "58000", "58002", "90107")
BAIDU_NETWORK_ERROR_CODES = ("52001", "52002")
BAIDU_QUOTA_ERROR_CODES = ("54003", "54004", "54005")


# ============================================================
#  异常类
# ============================================================
class TranslationError(Exception):
    pass


class NetworkError(TranslationError):
    pass


class AuthError(TranslationError):
    pass


class QuotaError(TranslationError):
    pass


class ParseError(TranslationError):
    pass


# ============================================================
#  基础翻译器
# ============================================================
class BaseTranslator(ABC):
    TIMEOUT = DEFAULT_REQUEST_TIMEOUT_SECONDS

    @abstractmethod
    def translate(self, text, source_lang, target_lang):
        pass

    def _request(self, url, data=None, headers=None, method="POST"):
        headers = headers or {}

        if method.upper() == "GET" and data is not None:
            query = urllib.parse.urlencode(data) if isinstance(data, dict) else str(data)
            sep = "&" if "?" in url else "?"
            url = url + sep + query
            body = None
        elif isinstance(data, dict):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, bytes):
            body = data
        else:
            body = None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=getattr(self, "timeout", self.TIMEOUT)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            self._handle_http_error(e.code, err_body)
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", "")).lower()
            if "timed out" in reason or "timeout" in reason:
                raise NetworkError("请求超时")
            raise NetworkError("网络连接失败，请检查网络")
        except json.JSONDecodeError:
            raise ParseError("响应格式异常，无法解析")
        except TranslationError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "timed out" in msg or "timeout" in msg:
                raise NetworkError("请求超时")
            raise TranslationError(str(e))

    def _handle_http_error(self, code, body):
        if code in (401, 403):
            raise AuthError("API 密钥无效或权限不足")
        if code == 429:
            raise QuotaError("请求过于频繁或配额不足，请稍后再试")
        if code == 456:
            raise QuotaError("翻译配额已用尽")
        try:
            err = json.loads(body)
            error = err.get("error")
            if isinstance(error, dict):
                msg = error.get("message", body)
            elif isinstance(error, str):
                msg = error
            else:
                msg = err.get("message", body)
        except Exception:
            msg = body[:200] if body else "无错误详情"
        raise TranslationError(f"HTTP {code}: {msg}")


# ============================================================
#  DeepL 翻译器（免费/付费接口各自独立 API Key）
# ============================================================
class DeepLTranslator(BaseTranslator):
    def __init__(self, config):
        self.current_api = config.get("current_api", "free")
        if self.current_api not in ("free", "pro"):
            self.current_api = "free"
        if self.current_api == "pro":
            self.api_key = str(config.get("api_key_pro") or "")
        else:
            self.api_key = str(config.get("api_key_free") or "")

    def translate(self, text, source_lang, target_lang):
        if not self.api_key:
            raise AuthError("请先配置 DeepL API 密钥")

        host = "api-free.deepl.com" if self.current_api == "free" else "api.deepl.com"
        url = f"https://{host}/v2/translate"

        params = {"text": text, "target_lang": LANG_DEEPL.get(target_lang, target_lang.upper())}
        src = LANG_DEEPL.get(source_lang)
        if src:
            params["source_lang"] = src

        body = urllib.parse.urlencode(params).encode("utf-8")
        headers = {
            "Authorization": f"DeepL-Auth-Key {self.api_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        result = self._request(url, body, headers)
        translations = result.get("translations", [])
        if not translations:
            raise ParseError("未获得翻译结果")

        try:
            translated = translations[0]["text"]
        except (KeyError, TypeError):
            raise ParseError("DeepL API 响应格式异常")

        return html.unescape(translated)


# ============================================================
#  百度翻译器
# ============================================================
class BaiduTranslator(BaseTranslator):
    def __init__(self, config):
        self.app_id = str(config.get("app_id") or "")
        self.secret_key = str(config.get("secret_key") or "")

    def translate(self, text, source_lang, target_lang):
        if not self.app_id or not self.secret_key:
            raise AuthError("请先配置百度翻译 AppID 和 SecretKey")

        url = "https://fanyi-api.baidu.com/api/trans/vip/translate"

        salt = str(random.randint(32768, 65536))
        src = LANG_BAIDU.get(source_lang, source_lang)
        tgt = LANG_BAIDU.get(target_lang, target_lang)

        sign_raw = self.app_id + text + salt + self.secret_key
        sign = hashlib.md5(sign_raw.encode("utf-8")).hexdigest()

        params = {
            "q": text, "from": src, "to": tgt,
            "appid": self.app_id, "salt": salt, "sign": sign,
        }

        body = urllib.parse.urlencode(params).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        result = self._request(url, body, headers)

        if "error_code" in result:
            code = str(result.get("error_code", ""))
            msg = result.get("error_msg", "未知错误")
            if code == "54001":
                raise AuthError("百度翻译签名错误，请检查 SecretKey")
            if code in BAIDU_AUTH_ERROR_CODES:
                raise AuthError(f"百度翻译认证失败: {msg}")
            if code in BAIDU_NETWORK_ERROR_CODES:
                raise NetworkError(f"百度翻译服务异常: {msg}")
            if code in BAIDU_QUOTA_ERROR_CODES:
                raise QuotaError(f"百度翻译频率或配额受限: {msg}")
            raise TranslationError(f"百度翻译错误 ({code}): {msg}")

        trans_list = result.get("trans_result", [])
        if not trans_list:
            raise ParseError("未获得翻译结果")

        parts = [item.get("dst", "") for item in trans_list if isinstance(item, dict)]
        translation = "\n".join(part for part in parts if part)
        if not translation:
            raise ParseError("百度翻译响应格式异常")

        return html.unescape(translation)


# ============================================================
#  OpenAI 格式翻译器（兼容 OpenAI / Ollama / vLLM 等）
# ============================================================
class OpenAITranslator(BaseTranslator):
    def __init__(self, config):
        self.api_key = str(config.get("api_key") or "")
        self.base_url = str(config.get("base_url") or "").strip().rstrip("/")
        self.model = str(config.get("model") or "").strip()
        self.domain = str(config.get("domain") or "")

    def translate(self, text, source_lang, target_lang):
        if not self.base_url:
            raise AuthError("请先配置 Base URL")
        if not self.model:
            raise AuthError("请先配置 Model")

        url = self._chat_completions_url()

        src_name = LANGUAGES.get(source_lang, source_lang)
        tgt_name = LANGUAGES.get(target_lang, target_lang)

        if source_lang == "auto":
            system_prompt = f"你是一个翻译助手。请将用户输入的文本翻译为{tgt_name}，只输出译文，不要添加任何解释或额外内容。"
        else:
            system_prompt = f"你是一个翻译助手。请将用户输入的{src_name}文本翻译为{tgt_name}，只输出译文，不要添加任何解释或额外内容。"

        if self.domain:
            system_prompt += f"翻译时请遵循{self.domain}领域的专业术语和表达风格。"

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        result = self._request(url, body, headers)

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ParseError("响应格式异常，请检查 Base URL 和 Model 是否正确")
        if not isinstance(content, str):
            raise ParseError("响应格式异常，请检查 Base URL 和 Model 是否正确")
        return html.unescape(content.strip())

    def _chat_completions_url(self):
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"


# ============================================================
#  AI 2（与 AI 1 结构相同，独立配置）
# ============================================================
class AI2Translator(OpenAITranslator):
    """与 AI1 共用 OpenAI 兼容实现，但读取独立的 AI2 配置。"""


# ============================================================
#  谷歌翻译器（免费公共接口 / Cloud Translation API）
# ============================================================
class GoogleTranslator(BaseTranslator):
    def __init__(self, config):
        self.api_key = str(config.get("api_key") or "")
        self.current_api = config.get("current_api", "free")
        if self.current_api not in ("free", "cloud"):
            self.current_api = "free"

    def translate(self, text, source_lang, target_lang):
        src = LANG_GOOGLE.get(source_lang, source_lang)
        tgt = LANG_GOOGLE.get(target_lang, target_lang)

        if self.current_api == "cloud":
            return self._translate_cloud(text, src, tgt)
        return self._translate_free(text, src, tgt)

    def _translate_free(self, text, src, tgt):
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": text}
        headers = {"User-Agent": "Mozilla/5.0"}

        result = self._request(url, params, headers=headers, method="GET")

        if not isinstance(result, list) or not result or not result[0]:
            raise ParseError("未获得翻译结果")

        segments = result[0]
        translation = "".join(item[0] for item in segments if item and item[0])

        if not translation:
            raise ParseError("翻译结果为空")

        return html.unescape(translation)

    def _translate_cloud(self, text, src, tgt):
        if not self.api_key:
            raise AuthError("请先配置 Google Cloud API Key")

        url = "https://translation.googleapis.com/language/translate/v2"
        body = {"q": text, "target": tgt, "format": "text"}
        if src != "auto":
            body["source"] = src

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
        }

        result = self._request(url, body, headers, method="POST")

        try:
            translations = result["data"]["translations"]
            if not translations:
                raise ParseError("未获得翻译结果")
            t = translations[0]
            return html.unescape(t["translatedText"])
        except (KeyError, IndexError, TypeError):
            raise ParseError("Google Cloud API 响应格式异常，请检查 API Key")


# ============================================================
#  工厂
# ============================================================
ENGINES = {
    "google": GoogleTranslator,
    "baidu": BaiduTranslator,
    "deepl": DeepLTranslator,
    "ai1": OpenAITranslator,
    "ai2": AI2Translator,
}


def create_translator(engine_name, config):
    engine_config = config.get("engines", {}).get(engine_name, {})
    cls = ENGINES.get(engine_name)
    if cls is None:
        raise TranslationError(f"不支持的翻译引擎: {engine_name}")
    translator = cls(engine_config)
    timeout = config.get("request_timeout_seconds", translator.TIMEOUT)
    if type(timeout) is int and timeout > 0:
        translator.timeout = timeout
    else:
        translator.timeout = translator.TIMEOUT
    return translator
