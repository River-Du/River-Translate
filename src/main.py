"""
翻译APP - 主界面 (tkinter)
零外部依赖，启动即用
"""

import sys
from pathlib import Path
_src_dir = str(Path(__file__).resolve().parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import copy
import ctypes
import threading
import unicodedata
from datetime import datetime
import tkinter as tk
from tkinter import ttk

from config import (
    CONFIG_INT_FIELDS,
    ConfigManager,
    HistoryManager,
    LANGUAGES,
    DEFAULT_CONFIG,
    DEFAULT_CLIPBOARD_POLL_MS,
    DEFAULT_HISTORY_MAX_ITEMS,
    DEFAULT_MAX_CHARS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    coerce_config_int,
    config_int_requirement,
    parse_config_int,
)
from translator import (
    ENGINE_NAMES,
    DEFAULT_ENGINE_NAMES,
    TranslationError,
    AuthError,
    create_translator,
)

# ---- 字体配置 ----
FONT = ("Microsoft YaHei UI", 11)
FONT_BOLD = ("Microsoft YaHei UI", 11, "bold")
FONT_BTN = ("Microsoft YaHei UI", 13, "bold")

MAIN_WINDOW_WIDTH = 600
MAIN_WINDOW_HEIGHT = 640
MAIN_WINDOW_MIN_WIDTH = 536
MAIN_WINDOW_MIN_HEIGHT = 440
SETTINGS_WINDOW_WIDTH = MAIN_WINDOW_WIDTH
SETTINGS_WINDOW_HEIGHT = 500
HISTORY_WINDOW_WIDTH = MAIN_WINDOW_WIDTH
HISTORY_WINDOW_HEIGHT = 440

AI_ENGINE_CODES = ("ai1", "ai2")
BUILTIN_ENGINE_CODES = ("google", "baidu", "deepl")
SOURCE_LANGUAGE_DISPLAY = dict(LANGUAGES)
TARGET_LANGUAGE_DISPLAY = dict(LANGUAGES)
TARGET_LANGUAGE_DISPLAY["auto"] = "自动中英"
SOURCE_DISPLAY_TO_LANGUAGE = {display: code for code, display in SOURCE_LANGUAGE_DISPLAY.items()}
TARGET_DISPLAY_TO_LANGUAGE = {display: code for code, display in TARGET_LANGUAGE_DISPLAY.items()}
HELP_TEXT = (
    "欢迎使用 River 翻译\n\n"
    "轻量纯文本翻译工具，适合短句、段落和剪贴板快速翻译。\n\n"
    "【翻译】\n"
    "Enter：翻译\n"
    "Ctrl / Shift + Enter：换行\n"
    "Escape：清空；翻译中终止\n\n"
    "【语言】\n"
    "源语言可自动检测；目标“自动中英”按首个有效字符选择中文或英语。\n"
    "⇄：交换语言和输入/输出；任一语言为自动时不可用。\n\n"
    "【引擎】\n"
    "谷歌免费接口可直接使用；百度、DeepL、自定义 AI 需先配置。\n\n"
    "【自动功能】\n"
    "剪贴板翻译：新剪贴板文本自动翻译\n"
    "自动翻译：停止输入约 1 秒后翻译\n"
    "自动复制：完成后复制译文\n"
    "窗口置顶：主窗口保持在前\n\n"
    "【历史与设置】\n"
    "历史可回填并自动去重；通用设置可调整超时时间、剪贴板周期和历史上限。"
)

# ---- Windows DPI 感知 ----
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


# ============================================================
#  主窗口
# ============================================================
class TranslatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("River翻译  V1.3")
        self.root.minsize(MAIN_WINDOW_MIN_WIDTH, MAIN_WINDOW_MIN_HEIGHT)
        self.root.geometry(f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}")

        # 配置 & 历史
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load()
        self.history_mgr = HistoryManager(max_items=self.config.get("history_max_items", DEFAULT_HISTORY_MAX_ITEMS))
        self.clipboard_poll_ms = self.config.get("clipboard_poll_ms", DEFAULT_CLIPBOARD_POLL_MS)
        self._get_clipboard_sequence_number = self._init_clipboard_sequence_api()

        # 同步 AI 名称到引擎列表
        self._sync_ai_names()

        # 运行时状态
        self._closed = False
        self._translating = False
        self._auto_translate_job = None
        self._clipboard_last_sequence = None
        self._pending_translate_after_current = False
        self._skip_next_auto_translate = False
        self._translation_id = 0
        self._active_text = ""

        # 建 UI
        self._setup_style()
        self._setup_ui()
        self._bind_keys()

        # 加载完毕后应用置顶 + 聚焦输入框
        self.root.after(80, self._apply_topmost_on_start)
        self.root.after(120, lambda: self.input_text.focus_set())
        self.root.after(150, self._on_input_change)
        self.root.after(180, self._poll_clipboard)

    # ========== 样式 ==========

    def _setup_style(self):
        style = ttk.Style()
        for theme in ("vista", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("TButton", font=FONT)
        style.configure("TCheckbutton", font=FONT)
        style.configure("TCombobox", font=FONT)
        style.configure("TLabel", font=FONT)
        style.configure("TRadiobutton", font=FONT)
        style.configure("TEntry", font=FONT)
        style.configure("Disabled.TButton", foreground="#999999")
        self.root.option_add("*TCombobox*Listbox.font", FONT)

    # ========== UI 搭建 ==========

    def _setup_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # ---- 底部栏（先锚定到最底部，防止窗口缩小时被吞） ----
        bottom = ttk.Frame(main)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)

        self.translate_btn = tk.Button(bottom, text="翻译", width=8,
                                       command=self._on_translate_button,
                                       bg="#0078D4", fg="white", font=FONT_BTN,
                                       activebackground="#106EBE", activeforeground="white",
                                       relief=tk.FLAT, padx=8, pady=6)
        self.translate_btn.pack(side=tk.LEFT, padx=2, pady=2)

        opt_frame = ttk.Frame(bottom)
        opt_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        opt_left = ttk.Frame(opt_frame)
        opt_left.pack(side=tk.LEFT)
        opt_right = ttk.Frame(opt_frame)
        opt_right.pack(side=tk.LEFT, padx=(34, 0), anchor=tk.N)

        self.clipboard_translate_var = tk.BooleanVar(value=self.config.get("clipboard_translate", False))
        ttk.Checkbutton(opt_left, text="剪贴板翻译",
                        variable=self.clipboard_translate_var,
                        command=self._on_clipboard_translate_toggle).pack(anchor=tk.W)

        self.auto_translate_var = tk.BooleanVar(value=self.config.get("auto_translate", False))
        ttk.Checkbutton(opt_left, text="自动翻译",
                        variable=self.auto_translate_var,
                        command=self._on_auto_translate_toggle).pack(anchor=tk.W)

        self.auto_copy_var = tk.BooleanVar(value=self.config.get("auto_copy", False))
        ttk.Checkbutton(opt_right, text="自动复制",
                        variable=self.auto_copy_var,
                        command=self._save_config).pack(anchor=tk.NW)

        self.topmost_var = tk.BooleanVar(value=self.config.get("always_on_top", False))
        self.topmost_cb = ttk.Checkbutton(opt_right, text="窗口置顶", variable=self.topmost_var,
                                          command=self._toggle_topmost)
        self.topmost_cb.pack(anchor=tk.NW)

        # ---- 行1: 语言选择 ----
        lang_frame = ttk.Frame(main)
        lang_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(lang_frame, text="源语言:", font=FONT).pack(side=tk.LEFT)

        self.src_var = tk.StringVar(value=self._source_code_to_display(self.config.get("source_lang", "auto")))
        self.src_combo = ttk.Combobox(lang_frame, textvariable=self.src_var,
                                      values=list(SOURCE_LANGUAGE_DISPLAY.values()), state="readonly",
                                      width=7, font=FONT)
        self.src_combo.pack(side=tk.LEFT, padx=(4, 8))
        self.src_combo.bind("<<ComboboxSelected>>", self._on_lang_select)

        self.swap_btn = ttk.Button(lang_frame, text="⇄", width=3, command=self._do_swap)
        self.swap_btn.pack(side=tk.LEFT, padx=4)
        self._refresh_swap_button_state()

        ttk.Label(lang_frame, text="目标语言:", font=FONT).pack(side=tk.LEFT, padx=(8, 0))
        self.tgt_var = tk.StringVar(
            value=self._target_code_to_display(
                self.config.get("target_lang", DEFAULT_CONFIG["target_lang"])
            )
        )
        tgt_choices = [TARGET_LANGUAGE_DISPLAY[c] for c in TARGET_LANGUAGE_DISPLAY]
        self.tgt_combo = ttk.Combobox(lang_frame, textvariable=self.tgt_var,
                                      values=tgt_choices, state="readonly",
                                      width=7, font=FONT)
        self.tgt_combo.pack(side=tk.LEFT, padx=(4, 4))
        self.tgt_combo.bind("<<ComboboxSelected>>", self._on_lang_select)

        # ---- 行2: 引擎 + 窗口置顶 ----
        engine_frame = ttk.Frame(main)
        engine_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(engine_frame, text="翻译引擎:", font=FONT).pack(side=tk.LEFT)

        eng_display = ENGINE_NAMES.get(self.config["current_engine"], ENGINE_NAMES[DEFAULT_CONFIG["current_engine"]])
        self.engine_var = tk.StringVar(value=eng_display)
        self.engine_combo = ttk.Combobox(engine_frame, textvariable=self.engine_var,
                                         values=list(ENGINE_NAMES.values()),
                                         state="readonly", width=9, font=FONT)
        self.engine_combo.pack(side=tk.LEFT, padx=(4, 8))
        self.engine_combo.bind("<<ComboboxSelected>>", self._on_engine_select)

        self.settings_btn = ttk.Button(engine_frame, text="⚙ 设置", width=9, command=self._open_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=2)

        self.help_window = None
        self.help_btn = ttk.Button(engine_frame, text="❔", width=3, command=self._open_help)
        self.help_btn.pack(side=tk.LEFT, padx=(2, 0))

        # ---- 分隔 ----
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 6))

        # ---- 行3~6: 输入/输出区域 ----
        text_pane = tk.PanedWindow(
            main,
            orient=tk.VERTICAL,
            borderwidth=0,
            sashwidth=10,
            sashrelief=tk.GROOVE,
            showhandle=False,
        )
        text_pane.pack(fill=tk.BOTH, expand=True)

        input_area = ttk.Frame(text_pane)
        output_area = ttk.Frame(text_pane)
        text_pane.add(input_area, stretch="always", minsize=90)
        text_pane.add(output_area, stretch="always", minsize=90)

        # ---- 输入区域头（标签 + 字数） ----
        in_header = ttk.Frame(input_area)
        in_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(in_header, text="输入文本", font=FONT_BOLD).pack(side=tk.LEFT)
        self.char_label = ttk.Label(in_header, text="0/5000", font=FONT, foreground="gray")
        self.char_label.pack(side=tk.RIGHT)

        # ---- 输入框 ----
        in_frame = ttk.Frame(input_area)
        in_frame.pack(fill=tk.BOTH, expand=True)

        self.input_text = tk.Text(in_frame, wrap=tk.WORD, font=FONT, height=6,
                                  relief=tk.SOLID, borderwidth=1, undo=True,
                                  background="#FFFDF7")
        in_scroll = ttk.Scrollbar(in_frame, orient=tk.VERTICAL, command=self.input_text.yview)
        self.input_text.configure(yscrollcommand=in_scroll.set)
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        in_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.input_text.bind("<KeyRelease>", self._on_input_change)
        self.input_text.bind("<Shift-Return>", self._on_input_newline)
        self.input_text.bind("<Control-Return>", self._on_input_newline)
        self.input_text.bind("<Return>", self._on_input_enter)

        # ---- 输出区域头（标签 + 操作按钮） ----
        out_header = ttk.Frame(output_area)
        out_header.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(out_header, text="翻译结果", font=FONT_BOLD).pack(side=tk.LEFT)

        self.copy_btn = ttk.Button(out_header, text="📋 复制", width=9, command=self._do_copy)
        self.copy_btn.pack(side=tk.RIGHT, padx=2)

        self.clear_btn = ttk.Button(out_header, text="❌ 清空", width=9, command=self._do_clear)
        self.clear_btn.pack(side=tk.RIGHT, padx=2)

        self.history_btn = ttk.Button(out_header, text="📜 历史", width=9, command=self._open_history)
        self.history_btn.pack(side=tk.RIGHT, padx=2)

        # ---- 输出框 ----
        out_frame = ttk.Frame(output_area)
        out_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = tk.Text(out_frame, wrap=tk.WORD, font=FONT, height=6,
                                   relief=tk.SOLID, borderwidth=1, state=tk.DISABLED,
                                   background="#F3F7FB")
        out_scroll = ttk.Scrollbar(out_frame, orient=tk.VERTICAL, command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=out_scroll.set)
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        out_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_text.tag_configure("error", foreground="#CC0000")
        self.output_text.tag_configure("loading", foreground="#888888")

    # ========== 快捷键 ==========

    def _bind_keys(self):
        self.root.bind("<Escape>", self._on_global_clear)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_global_clear(self, event=None):
        if self._translating:
            self._terminate_translation()
            return "break"
        self._do_clear()
        return "break"

    def _on_input_enter(self, event):
        self._skip_next_auto_translate = True
        self._do_translate()
        return "break"

    def _on_input_newline(self, event=None):
        self.input_text.insert(tk.INSERT, "\n")
        self._on_input_change()
        return "break"

    def _on_close(self):
        self._closed = True
        self._cancel_auto_translate()
        self._translation_id += 1
        self._save_config()
        self.root.destroy()

    # ========== 语言/引擎切换 ==========

    def _source_code_to_display(self, code):
        return SOURCE_LANGUAGE_DISPLAY.get(code, SOURCE_LANGUAGE_DISPLAY["auto"])

    def _target_code_to_display(self, code):
        return TARGET_LANGUAGE_DISPLAY.get(code, TARGET_LANGUAGE_DISPLAY["auto"])

    def _source_display_to_code(self, display):
        return SOURCE_DISPLAY_TO_LANGUAGE.get(display, "auto")

    def _target_display_to_code(self, display):
        return TARGET_DISPLAY_TO_LANGUAGE.get(display, "auto")

    def _get_engine_code(self):
        for c, n in ENGINE_NAMES.items():
            if n == self.engine_var.get():
                return c
        return DEFAULT_CONFIG["current_engine"]

    def _on_lang_select(self, event=None):
        self._refresh_swap_button_state()
        self._save_config()
        self._on_input_change()

    def _on_engine_select(self, event=None):
        self._save_config()
        self._on_input_change()

    def _on_input_change(self, event=None):
        self._update_char_count()

        text = self.input_text.get("1.0", "end-1c")

        # 自动翻译：输入停止 1 秒后触发
        self._cancel_auto_translate()
        if self._skip_next_auto_translate:
            self._skip_next_auto_translate = False
            return
        if self.auto_translate_var.get() and text.strip():
            self._auto_translate_job = self.root.after(1000, self._do_translate)

    def _update_char_count(self):
        text = self.input_text.get("1.0", "end-1c")
        n = len(text)
        limit = self._get_max_chars()
        self.char_label.configure(
            text=f"{n}/{limit}",
            foreground="red" if n >= limit * 0.85 else "gray",
        )

    def _cancel_auto_translate(self):
        if self._auto_translate_job is not None:
            try:
                self.root.after_cancel(self._auto_translate_job)
            except tk.TclError:
                pass
            self._auto_translate_job = None

    def _cancel_translation_state(self):
        self._pending_translate_after_current = False
        self._translation_id += 1
        self._active_text = ""
        if self._translating:
            self._set_translating(False)

    def _terminate_translation(self):
        if not self._translating:
            return
        self._cancel_auto_translate()
        self._cancel_translation_state()
        self._set_output_message("已终止翻译")

    def _on_auto_translate_toggle(self):
        self._save_config()
        self._pending_translate_after_current = False
        if self.auto_translate_var.get():
            self._on_input_change()
        else:
            self._cancel_auto_translate()

    def _on_clipboard_translate_toggle(self):
        self._save_config()
        if self.clipboard_translate_var.get():
            self._reset_clipboard_baseline()

    def _poll_clipboard(self):
        if self._closed:
            return

        if self.clipboard_translate_var.get():
            sequence = self._get_clipboard_sequence()
            if sequence is not None:
                if self._clipboard_last_sequence is None:
                    self._clipboard_last_sequence = sequence
                elif sequence != self._clipboard_last_sequence:
                    self._clipboard_last_sequence = sequence
                    text = self._get_clipboard_text()
                    if text is not None:
                        self._translate_clipboard_text(text)

        self.root.after(self.clipboard_poll_ms, self._poll_clipboard)

    def _reset_clipboard_baseline(self):
        self._clipboard_last_sequence = self._get_clipboard_sequence()

    def _init_clipboard_sequence_api(self):
        if sys.platform != "win32":
            return None
        try:
            get_sequence = ctypes.windll.user32.GetClipboardSequenceNumber
            get_sequence.restype = ctypes.c_uint
            return get_sequence
        except (AttributeError, OSError):
            return None

    def _get_clipboard_sequence(self):
        if self._get_clipboard_sequence_number is None:
            return None
        try:
            return int(self._get_clipboard_sequence_number())
        except OSError:
            return None

    def _get_clipboard_text(self):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return None

    def _translate_clipboard_text(self, text):
        if not text or not text.strip():
            return
        if text == self.input_text.get("1.0", "end-1c"):
            return

        self._cancel_auto_translate()
        self._pending_translate_after_current = False
        self._skip_next_auto_translate = True
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", text)
        self._on_input_change()
        if self._translating:
            self._pending_translate_after_current = True
        else:
            self._do_translate()

    def _get_max_chars(self):
        code = self._get_engine_code()
        try:
            value = int(self.config.get("engines", {}).get(code, {}).get("max_chars", DEFAULT_MAX_CHARS))
        except (ValueError, TypeError):
            return DEFAULT_MAX_CHARS
        return coerce_config_int("max_chars", value)

    def _save_config(self):
        self.config["current_engine"] = self._get_engine_code()
        self.config["source_lang"] = self._source_display_to_code(self.src_var.get())
        self.config["target_lang"] = self._target_display_to_code(self.tgt_var.get())
        self.config["always_on_top"] = self.topmost_var.get()
        self.config["auto_translate"] = self.auto_translate_var.get()
        self.config["auto_copy"] = self.auto_copy_var.get()
        self.config["clipboard_translate"] = self.clipboard_translate_var.get()
        return self.config_mgr.save(self.config)

    # ========== 置顶 ==========

    def _apply_topmost_on_start(self):
        if self.topmost_var.get():
            self.root.attributes("-topmost", True)

    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())
        self._save_config()

    # ========== 核心翻译流程 ==========

    def _on_translate_button(self):
        if self._translating:
            self._terminate_translation()
        else:
            self._do_translate()

    def _do_translate(self):
        if self._translating:
            text = self.input_text.get("1.0", "end-1c").strip()
            if text and text != self._active_text:
                self._pending_translate_after_current = True
            return
        self._cancel_auto_translate()

        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            self._set_output_message("请输入要翻译的文本", error=True)
            return

        max_chars = self._get_max_chars()
        if len(text) > max_chars:
            self._set_output_message(f"文本过长（{len(text)}/{max_chars}），请精简后重试", error=True)
            return

        self._save_config()

        engine = self._get_engine_code()
        src_code = self._source_display_to_code(self.src_var.get())
        tgt_code = self._target_display_to_code(self.tgt_var.get())
        request_tgt_code = self._resolve_target_lang_for_request(tgt_code, text)

        # 深拷贝当前请求配置，避免子线程与设置弹窗竞态
        engine_cfg = copy.deepcopy(self.config.get("engines", {}).get(engine, {}))
        request_config = {
            "request_timeout_seconds": self.config.get(
                "request_timeout_seconds",
                DEFAULT_REQUEST_TIMEOUT_SECONDS,
            ),
            "engines": {engine: engine_cfg},
        }
        self._translation_id += 1
        request_id = self._translation_id
        self._active_text = text

        self._set_translating(True)
        self._set_output_message("翻译中...")

        t = threading.Thread(target=self._translate_worker,
                             args=(engine, request_config, text, src_code, request_tgt_code, tgt_code, request_id),
                             daemon=True)
        t.start()

    def _translate_worker(self, engine, request_config, text, src_code, request_tgt_code, display_tgt_code, request_id):
        try:
            translator = create_translator(engine, request_config)
            result = translator.translate(text, src_code, request_tgt_code)

            self._schedule_on_main(
                self._on_translate_ok,
                result,
                engine,
                src_code,
                display_tgt_code,
                text,
                request_id,
            )
        except AuthError as e:
            self._schedule_on_main(self._on_auth_error, str(e), text, request_id)
        except TranslationError as e:
            self._schedule_on_main(self._on_translate_fail, str(e), text, request_id)
        except Exception as e:
            self._schedule_on_main(self._on_translate_fail, str(e), text, request_id)

    def _resolve_target_lang_for_request(self, target_lang, text):
        if target_lang != "auto":
            return target_lang
        return "en" if self._first_effective_char_is_chinese(text) else "zh"

    def _first_effective_char_is_chinese(self, text):
        for ch in text:
            if not self._is_effective_lang_char(ch):
                continue
            return self._is_chinese_char(ch)
        return False

    def _is_effective_lang_char(self, ch):
        category = unicodedata.category(ch)
        return category[0] == "L"

    def _is_chinese_char(self, ch):
        codepoint = ord(ch)
        return (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x2A6DF
            or 0x2A700 <= codepoint <= 0x2B73F
            or 0x2B740 <= codepoint <= 0x2B81F
            or 0x2B820 <= codepoint <= 0x2CEAF
            or 0x2CEB0 <= codepoint <= 0x2EBEF
            or 0x30000 <= codepoint <= 0x3134F
        )

    def _schedule_on_main(self, callback, *args):
        if self._closed:
            return
        try:
            self.root.after(0, callback, *args)
        except (tk.TclError, RuntimeError):
            pass

    def _on_translate_ok(self, result, engine, src_code, tgt_code, submitted_text, request_id):
        if self._is_stale_translation(submitted_text, request_id):
            if (
                request_id == self._translation_id
                and not self._pending_translate_after_current
                and not self._auto_translate_job
            ):
                self._set_output_message("输入内容已更改，已忽略本次翻译结果")
            self._finish_translation(request_id)
            return

        self._replace_output(result)

        # 自动复制
        if self.auto_copy_var.get():
            self._copy_to_clipboard(result)

        # 记历史
        src_text = self.input_text.get("1.0", "end-1c").strip()
        self.history_mgr.add({
            "source_text": src_text,
            "source_lang": src_code,
            "target_text": result,
            "target_lang": tgt_code,
            "engine": engine,
            "time": datetime.now().isoformat(timespec="seconds"),
        })

        self._finish_translation(request_id)

    def _on_auth_error(self, msg, submitted_text, request_id):
        if self._is_stale_translation(submitted_text, request_id):
            self._finish_translation(request_id)
            return
        self._set_output_message(msg or "请先配置 API 密钥", error=True)
        self._finish_translation(request_id)

    def _on_translate_fail(self, msg, submitted_text, request_id):
        if self._is_stale_translation(submitted_text, request_id):
            self._finish_translation(request_id)
            return
        self._set_output_message(f"错误: {msg}", error=True)
        self._finish_translation(request_id)

    def _is_stale_translation(self, submitted_text, request_id):
        if request_id != self._translation_id:
            return True
        current_text = self.input_text.get("1.0", "end-1c").strip()
        return current_text != submitted_text

    def _finish_translation(self, request_id):
        if request_id != self._translation_id:
            return
        self._active_text = ""
        self._set_translating(False)
        if not self._pending_translate_after_current:
            return
        self._pending_translate_after_current = False
        if self.input_text.get("1.0", "end-1c").strip():
            self.root.after(0, self._do_translate)

    def _set_translating(self, translating):
        self._translating = translating
        combo_state = tk.DISABLED if translating else "readonly"
        if translating:
            self.translate_btn.configure(
                text="终止翻译", state=tk.NORMAL, bg="#D83B01", activebackground="#A4262C"
            )
        else:
            self.translate_btn.configure(
                text="翻译", state=tk.NORMAL, bg="#0078D4", activebackground="#106EBE"
            )
        self.engine_combo.configure(state=combo_state)
        self.src_combo.configure(state=combo_state)
        self.tgt_combo.configure(state=combo_state)
        if translating:
            self.swap_btn.configure(state=tk.DISABLED, style="Disabled.TButton")
        else:
            self._refresh_swap_button_state()

    def _refresh_swap_button_state(self):
        disabled = (
            self._translating
            or self._source_display_to_code(self.src_var.get()) == "auto"
            or self._target_display_to_code(self.tgt_var.get()) == "auto"
        )
        state = tk.DISABLED if disabled else tk.NORMAL
        style = "Disabled.TButton" if disabled else "TButton"
        self.swap_btn.configure(state=state, style=style)

    def _set_output_message(self, msg, error=False):
        tag = "error" if error else "loading"
        self._replace_output(msg, tag=tag)

    def _replace_output(self, text, tag=None):
        self.output_text.configure(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", text)
        if tag:
            self.output_text.tag_add(tag, "1.0", tk.END)
        self.output_text.configure(state=tk.DISABLED)

    # ========== 其他操作 ==========

    def _do_swap(self):
        if self._translating:
            return
        src = self.src_var.get()
        tgt = self.tgt_var.get()
        if self._source_display_to_code(src) == "auto" or self._target_display_to_code(tgt) == "auto":
            return

        self.src_var.set(tgt)
        self.tgt_var.set(src)
        self._refresh_swap_button_state()

        in_text = self.input_text.get("1.0", "end-1c")
        out_text = self.output_text.get("1.0", "end-1c")

        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", out_text)

        self._replace_output(in_text)

        self._on_input_change()
        self._save_config()

    def _do_copy(self):
        text = self.output_text.get("1.0", "end-1c").strip()
        if not text:
            return
        self._copy_to_clipboard(text)

    def _copy_to_clipboard(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            return False
        if self.clipboard_translate_var.get():
            self._reset_clipboard_baseline()
        return True

    def _do_clear(self):
        self._cancel_auto_translate()
        self._cancel_translation_state()
        self.input_text.delete("1.0", tk.END)
        self._replace_output("")
        self._update_char_count()

    # ========== 设置弹窗 ==========

    def _open_settings(self):
        current_engine = self._get_engine_code()
        SettingsDialog(self.root, self.config, self.config_mgr, self._on_settings_saved, current_engine)

    def _open_help(self):
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            self.help_window.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.help_window = win
        win.title("帮助")
        win.resizable(False, False)
        win.transient(self.root)

        main = ttk.Frame(win, padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        text_frame = ttk.Frame(main)
        text_frame.pack(fill=tk.BOTH, expand=True)

        help_text_widget = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=FONT,
            width=58,
            height=18,
            relief=tk.SOLID,
            borderwidth=1,
            padx=8,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=help_text_widget.yview)
        help_text_widget.configure(yscrollcommand=scrollbar.set)
        help_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        help_text_widget.insert("1.0", HELP_TEXT)
        help_text_widget.configure(state=tk.DISABLED)

        button_row = ttk.Frame(main)
        button_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(button_row, text="关闭", command=self._close_help).pack(side=tk.RIGHT)
        win.protocol("WM_DELETE_WINDOW", self._close_help)
        self._center_child_window(win, 560, 430)

    def _close_help(self):
        if self.help_window is None:
            return
        try:
            self.help_window.destroy()
        except tk.TclError:
            pass
        self.help_window = None

    def _center_child_window(self, window, width, height):
        window.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _on_settings_saved(self, new_config):
        self.config = new_config
        self._sync_ai_names()
        self.clipboard_poll_ms = self.config.get("clipboard_poll_ms", DEFAULT_CLIPBOARD_POLL_MS)
        self.history_mgr.max_items = self.config.get("history_max_items", DEFAULT_HISTORY_MAX_ITEMS)

        self.src_var.set(self._source_code_to_display(self.config.get("source_lang", "auto")))
        self.tgt_var.set(
            self._target_code_to_display(
                self.config.get("target_lang", DEFAULT_CONFIG["target_lang"])
            )
        )
        self.topmost_var.set(self.config.get("always_on_top", False))
        self.auto_translate_var.set(self.config.get("auto_translate", False))
        self.auto_copy_var.set(self.config.get("auto_copy", False))
        self.clipboard_translate_var.set(self.config.get("clipboard_translate", False))
        self.root.attributes("-topmost", self.topmost_var.get())

        self.engine_combo.configure(values=list(ENGINE_NAMES.values()))
        current_code = self.config.get("current_engine", DEFAULT_CONFIG["current_engine"])
        self.engine_var.set(ENGINE_NAMES.get(current_code, ENGINE_NAMES[DEFAULT_CONFIG["current_engine"]]))
        self._refresh_swap_button_state()
        self._on_input_change()

    def _sync_ai_names(self):
        for key in BUILTIN_ENGINE_CODES:
            name = DEFAULT_ENGINE_NAMES[key]
            ENGINE_NAMES[key] = name

        used = {DEFAULT_ENGINE_NAMES[key] for key in BUILTIN_ENGINE_CODES}
        for key in AI_ENGINE_CODES:
            default = DEFAULT_CONFIG["engines"][key]["name"]
            name = self.config.get("engines", {}).get(key, {}).get("name", "").strip()
            unique_name = self._unique_engine_name(name or default, default, used)
            self.config["engines"][key]["name"] = unique_name
            ENGINE_NAMES[key] = unique_name
            used.add(unique_name)

    def _unique_engine_name(self, name, default, used):
        if name not in used:
            return name
        if default not in used:
            return default
        idx = 2
        while f"{default} {idx}" in used:
            idx += 1
        return f"{default} {idx}"

    def _safe_engine_code(self, code, default=DEFAULT_CONFIG["current_engine"]):
        return code if code in ENGINE_NAMES else default

    def _safe_lang_code(self, code, default="auto"):
        if code not in LANGUAGES:
            return default
        return code

    # ========== 历史弹窗 ==========

    def _open_history(self):
        history = self.history_mgr.get_all()
        HistoryDialog(self.root, history, self.history_mgr, self._on_history_select)

    def _on_history_select(self, entry):
        if entry is None:
            return
        self._cancel_auto_translate()
        self._cancel_translation_state()
        self._skip_next_auto_translate = True

        src_code = self._safe_lang_code(entry.get("source_lang"), default="auto")
        tgt_code = self._safe_lang_code(
            entry.get("target_lang"),
            default=DEFAULT_CONFIG["target_lang"],
        )
        engine = self._safe_engine_code(entry.get("engine"))

        self.src_var.set(self._source_code_to_display(src_code))
        self.tgt_var.set(self._target_code_to_display(tgt_code))
        self._refresh_swap_button_state()
        eng_name = ENGINE_NAMES.get(engine, ENGINE_NAMES[DEFAULT_CONFIG["current_engine"]])
        self.engine_var.set(eng_name)
        self.config["current_engine"] = engine

        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", entry.get("source_text", ""))

        self._replace_output(entry.get("target_text", ""))

        self._on_input_change()
        # 回填历史时取消自动翻译，避免覆盖历史记录
        self._cancel_auto_translate()
        self._save_config()

    # ========== 运行 ==========

    def run(self):
        self.root.mainloop()


# ============================================================
#  设置弹窗
# ============================================================
class SettingsDialog:
    TABS = ["general", "google", "baidu", "deepl", "ai1", "ai2"]
    GENERAL_FIELDS = (
        ("request_timeout_seconds", "超时时间"),
        ("clipboard_poll_ms", "剪贴板周期"),
        ("history_max_items", "历史上限"),
    )
    TAB_LABELS = {
        "general": "通用",
        "deepl": "DeepL",
        "baidu": "百度",
        "google": "谷歌",
        "ai1": "AI 1",
        "ai2": "AI 2",
    }
    API_MODES = {"google": ("free", "cloud"), "deepl": ("free", "pro")}

    def __init__(self, parent, config, config_mgr, callback, initial_tab="google"):
        self.config = copy.deepcopy(config)
        self.config_mgr = config_mgr
        self.callback = callback
        self.initial_tab = initial_tab if initial_tab in self.TABS else DEFAULT_CONFIG["current_engine"]
        self.general_entries = {}
        self.entries = {}
        self.api_types = {}
        self.max_entries = {}
        self._closed = False
        self._test_id = 0

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("设置")
        self.dialog.resizable(True, True)
        self.dialog.minsize(SETTINGS_WINDOW_WIDTH, SETTINGS_WINDOW_HEIGHT)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._close)

        self._build_ui()
        self._center_on_parent(parent)

    def _close(self):
        if self._closed:
            return
        self._closed = True
        self._test_id += 1
        try:
            self.dialog.destroy()
        except tk.TclError:
            pass

    def _center_on_parent(self, parent):
        self.dialog.update_idletasks()
        w, h = SETTINGS_WINDOW_WIDTH, SETTINGS_WINDOW_HEIGHT
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- UI ----------

    def _build_ui(self):
        main = ttk.Frame(self.dialog, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # 引擎切换按钮
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 4))

        self.active_tab = tk.StringVar(value=self.initial_tab)
        for code in self.TABS:
            ttk.Radiobutton(btn_frame, text=self.TAB_LABELS[code],
                            variable=self.active_tab, value=code,
                            command=self._switch_tab).pack(side=tk.LEFT, padx=6)

        # 分隔：选项卡 ↔ 设置内容
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 0))
        tk.Frame(main, height=2, bg="#555555").pack(fill=tk.X, pady=(1, 0))
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(1, 5))

        footer = ttk.Frame(main)
        footer.pack(side=tk.BOTTOM, fill=tk.X)

        self.settings_status = ttk.Label(footer, text="", foreground="gray", font=FONT)
        self.settings_status.pack(anchor=tk.W, pady=(12, 4))

        bottom = ttk.Frame(footer)
        bottom.pack(fill=tk.X)

        self.test_btn = ttk.Button(bottom, text="测试连接", command=self._test_connection)
        self.test_btn.pack(side=tk.LEFT)

        ttk.Button(bottom, text="保存", command=self._save).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bottom, text="取消", command=self._close).pack(side=tk.RIGHT, padx=2)

        # 内容区：提前创建所有 tab frame，用 pack_forget 隐藏
        self.content_area = ttk.Frame(main)
        self.content_area.pack(fill=tk.BOTH, expand=True)

        self.tab_frames = {}
        for code in self.TABS:
            f = self._make_tab_frame(code)
            self.tab_frames[code] = f

        self._switch_tab()

    def _make_tab_frame(self, code):
        f = ttk.Frame(self.content_area)

        if code == "general":
            self._make_general_tab(f)
            return f

        cfg = self.config["engines"].get(code, {})

        if code == "deepl":
            self.api_types[code] = tk.StringVar(value=self._api_mode(code, cfg.get("current_api")))
            self._make_radio(f, "Free API (api-free.deepl.com)", self.api_types[code], "free")
            self.entries[(code, "api_key_free")] = self._make_stacked_entry(
                f, "Free API Key:", cfg.get("api_key_free", ""), show="*"
            )
            ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
            self._make_radio(f, "Pro API (api.deepl.com)", self.api_types[code], "pro")
            self.entries[(code, "api_key_pro")] = self._make_stacked_entry(
                f, "Pro API Key:", cfg.get("api_key_pro", ""), show="*"
            )

        elif code == "baidu":
            self.entries[(code, "app_id")] = self._make_stacked_entry(f, "AppID:", cfg.get("app_id", ""))
            self.entries[(code, "secret_key")] = self._make_stacked_entry(
                f, "SecretKey:", cfg.get("secret_key", ""), show="*"
            )

        elif code == "google":
            self.api_types[code] = tk.StringVar(value=self._api_mode(code, cfg.get("current_api")))
            self._make_radio(f, "免费接口", self.api_types[code], "free")
            ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
            self._make_radio(f, "Cloud Translation API", self.api_types[code], "cloud")
            self.entries[(code, "api_key")] = self._make_stacked_entry(
                f, "API Key:", cfg.get("api_key", ""), show="*"
            )

        elif code in AI_ENGINE_CODES:
            self._make_ai_tab(f, code, cfg)

        self.max_entries[code] = self._add_max_chars_to_tab(f, cfg)

        return f

    def _make_general_tab(self, parent):
        for field, label in self.GENERAL_FIELDS:
            default = CONFIG_INT_FIELDS[field][0]
            self.general_entries[field] = self._make_row(
                parent,
                f"{label}:",
                self.config.get(field, default),
            )

    def _make_ai_tab(self, parent, code, cfg):
        defaults = DEFAULT_CONFIG["engines"][code]
        self.entries[(code, "name")] = self._make_row(parent, "名称:", cfg.get("name", ""))
        self.entries[(code, "api_key")] = self._make_row(
            parent, "API Key:", cfg.get("api_key", ""), show="*"
        )
        self.entries[(code, "base_url")] = self._make_row(
            parent, "Base URL:", cfg.get("base_url", defaults["base_url"])
        )
        self.entries[(code, "model")] = self._make_row(
            parent, "Model:", cfg.get("model", defaults["model"])
        )
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        self.entries[(code, "domain")] = self._make_row(parent, "领域/风格:", cfg.get("domain", ""))

    def _api_mode(self, code, value):
        modes = self.API_MODES[code]
        return value if value in modes else modes[0]

    def _make_radio(self, parent, text, variable, value):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Radiobutton(frame, text=text, variable=variable, value=value).pack(anchor=tk.W)

    def _make_stacked_entry(self, parent, label, default="", show=None):
        ttk.Label(parent, text=label).pack(anchor=tk.W)
        entry = ttk.Entry(parent, font=FONT, width=52, show=show)
        entry.insert(0, str(default))
        entry.pack(fill=tk.X, pady=(2, 10))
        return entry

    def _add_max_chars_to_tab(self, f, cfg):
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 6))
        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="最大字数:", width=10).pack(side=tk.LEFT)
        max_entry = ttk.Entry(row, font=FONT)
        max_entry.insert(0, str(cfg.get("max_chars", DEFAULT_MAX_CHARS)))
        max_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return max_entry

    def _make_row(self, parent, label, default="", show=None):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, width=10).pack(side=tk.LEFT)
        entry = ttk.Entry(row, font=FONT, show=show)
        entry.insert(0, str(default))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return entry

    def _switch_tab(self):
        self._test_id += 1
        for code, frame in self.tab_frames.items():
            frame.pack_forget()
        self.tab_frames[self.active_tab.get()].pack(fill=tk.BOTH, expand=True)
        self.settings_status.configure(text="")
        state = tk.DISABLED if self.active_tab.get() == "general" else tk.NORMAL
        self.test_btn.configure(state=state)

    # ---------- 读取/写入 ----------

    def _collect_values(self):
        """将所有 tab 的当前值写入 self.config"""
        if not self._collect_general_values():
            return False

        for code in self.TABS:
            if code != "general":
                if not self._collect_engine_values(code):
                    return False
        return True

    def _collect_general_values(self):
        for field, label in self.GENERAL_FIELDS:
            value = self._read_config_int(self.general_entries[field], field, label)
            if value is None:
                return False
            self.config[field] = value
        self.settings_status.configure(text="", foreground="gray")
        return True

    def _collect_engine_values(self, code):
        for (entry_code, field), entry in self.entries.items():
            if entry_code == code:
                self.config["engines"][code][field] = entry.get().strip()

        if code in self.api_types:
            self.config["engines"][code]["current_api"] = self._api_mode(code, self.api_types[code].get())

        if code in self.max_entries:
            max_chars = self._read_config_int(self.max_entries[code], "max_chars", "最大字数", code)
            if max_chars is None:
                return False
            self.config["engines"][code]["max_chars"] = max_chars

        if code in AI_ENGINE_CODES:
            self._apply_ai_defaults(code)
        return True

    def _apply_ai_defaults(self, code):
        defaults = DEFAULT_CONFIG["engines"][code]
        self.config["engines"][code]["name"] = self.config["engines"][code]["name"] or defaults["name"]
        self.config["engines"][code]["base_url"] = (
            self.config["engines"][code]["base_url"] or defaults["base_url"]
        )
        self.config["engines"][code]["model"] = self.config["engines"][code]["model"] or defaults["model"]

    def _save(self):
        if not self._collect_values():
            return
        if not self._validate_engine_names():
            return
        if not self.config_mgr.save(self.config):
            self.settings_status.configure(
                text="配置保存失败，请检查 user_data 目录写入权限。",
                foreground="red",
            )
            return
        self.callback(self.config)
        self._close()

    def _validate_engine_names(self):
        used = {}
        for code in BUILTIN_ENGINE_CODES:
            used[ENGINE_NAMES[code]] = code
        for code in AI_ENGINE_CODES:
            name = self.config["engines"][code]["name"]
            if name in used:
                entry = self.entries[(code, "name")]
                self._show_input_error(entry, f"名称“{name}”已被其他引擎使用", code)
                return False
            used[name] = code
        return True

    def _read_config_int(self, entry, field, label, tab="general"):
        try:
            return parse_config_int(field, entry.get())
        except ValueError:
            requirement = config_int_requirement(field)
            return self._show_input_error(entry, f"{label}请输入{requirement}", tab)

    def _show_input_error(self, entry, message, tab):
        if self.active_tab.get() != tab:
            self.active_tab.set(tab)
            self._switch_tab()
        self.settings_status.configure(text=message, foreground="red")
        entry.focus_set()
        entry.selection_range(0, tk.END)
        return None

    # ---------- 测试连接 ----------

    def _test_connection(self):
        code = self.active_tab.get()
        if code == "general":
            return
        timeout = self._read_config_int(
            self.general_entries["request_timeout_seconds"],
            "request_timeout_seconds",
            "超时时间",
        )
        if timeout is None:
            return
        self.config["request_timeout_seconds"] = timeout
        if not self._collect_engine_values(code):
            return
        config_snapshot = copy.deepcopy(self.config)
        self._test_id += 1
        test_id = self._test_id
        self.settings_status.configure(text="测试中...", foreground="gray")
        self.test_btn.configure(state=tk.DISABLED)

        def worker():
            try:
                tr = create_translator(code, config_snapshot)
                result = tr.translate("hello", "auto", "zh")
                self._schedule_test_result(self._on_test_ok, result, test_id)
            except Exception as e:
                self._schedule_test_result(self._on_test_fail, str(e), test_id)

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_test_result(self, callback, *args):
        if self._closed:
            return
        try:
            self.dialog.after(0, callback, *args)
        except (tk.TclError, RuntimeError):
            pass

    def _on_test_ok(self, result, test_id):
        if self._closed or test_id != self._test_id or not self.dialog.winfo_exists():
            return
        short = result[:30] + "..." if len(result) > 30 else result
        self.settings_status.configure(text=f"连接成功: {short}", foreground="green")
        self.test_btn.configure(state=tk.NORMAL)

    def _on_test_fail(self, msg, test_id):
        if self._closed or test_id != self._test_id or not self.dialog.winfo_exists():
            return
        self.settings_status.configure(text=f"连接失败: {msg}", foreground="red")
        self.test_btn.configure(state=tk.NORMAL)


# ============================================================
#  历史弹窗
# ============================================================
class HistoryDialog:
    def __init__(self, parent, history, history_mgr, callback):
        self.history = history
        self.history_mgr = history_mgr
        self.callback = callback

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("翻译历史")
        self.dialog.resizable(True, True)
        self.dialog.minsize(400, 280)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()
        self._center_on_parent(parent)

    def _center_on_parent(self, parent):
        self.dialog.update_idletasks()
        w, h = HISTORY_WINDOW_WIDTH, HISTORY_WINDOW_HEIGHT
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.dialog.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        main = ttk.Frame(self.dialog, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # 底部栏先锚定，窗口缩小时优先保留状态和操作按钮。
        bf = ttk.Frame(main)
        bf.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        self.status_label = ttk.Label(bf, text="", foreground="gray")
        self.status_label.pack(side=tk.LEFT)

        self.restore_btn = ttk.Button(bf, text="回填", command=self._on_select)
        self.restore_btn.pack(side=tk.RIGHT)
        self.clear_history_btn = ttk.Button(bf, text="清空历史", command=self._clear)
        self.clear_history_btn.pack(side=tk.RIGHT, padx=2)

        # Treeview 样式：增高行 + 字体
        style = ttk.Style()
        style.configure("History.Treeview", font=FONT, rowheight=34)
        style.configure("History.Treeview.Heading", font=FONT_BOLD)

        # Treeview：两列——原文（自适应）+ 时间（固定居右）
        lf = ttk.Frame(main)
        lf.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(lf, columns=("source", "time"), show="headings",
                                 selectmode="browse", style="History.Treeview")
        self.tree.heading("source", text="翻译原文")
        self.tree.heading("time", text="时间")
        self.tree.column("source", minwidth=80, stretch=True)
        self.tree.column("time", width=140, minwidth=140, stretch=False, anchor="e")

        # 禁止拖动列分隔线
        self.tree.bind("<Button-1>", self._prevent_separator_resize, add="+")
        self.tree.bind("<B1-Motion>", self._prevent_separator_resize, add="+")

        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        for entry in self.history:
            src_t = self._preview(entry.get("source_text", ""))
            t = self._format_time(entry.get("time", ""))
            self.tree.insert("", "end", values=(src_t, t))

        self.tree.bind("<Double-Button-1>", self._on_select)
        self.tree.bind("<Return>", self._on_select)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._refresh_state()

    def _prevent_separator_resize(self, event):
        if self.tree.identify_region(event.x, event.y) == "separator":
            return "break"

    def _preview(self, text, limit=120):
        text = " ".join(str(text).split())
        if len(text) <= limit:
            return text
        return text[:limit - 3] + "..."

    def _format_time(self, value):
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
        except (TypeError, ValueError):
            return str(value)

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self.history):
            self.callback(self.history[idx])
            self.dialog.destroy()

    def _clear(self):
        if not self.history:
            return
        self.history_mgr.clear()
        self.history = []
        self.tree.delete(*self.tree.get_children())
        self._refresh_state()

    def _on_tree_select(self, event=None):
        self._refresh_state()

    def _refresh_state(self):
        has_history = bool(self.history)
        has_selection = bool(self.tree.selection())
        max_items = getattr(self.history_mgr, "max_items", DEFAULT_HISTORY_MAX_ITEMS)
        self.status_label.configure(text=f"共 {len(self.history)}/{max_items} 条", foreground="gray")
        self.clear_history_btn.configure(state=tk.NORMAL if has_history else tk.DISABLED)
        self.restore_btn.configure(state=tk.NORMAL if has_selection else tk.DISABLED)


# ============================================================
#  入口
# ============================================================
if __name__ == "__main__":
    app = TranslatorApp()
    app.run()
