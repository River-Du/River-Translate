<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/Dependencies-zero-success" alt="Dependencies">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

<h1 align="center">River Translate</h1>

一个轻量、简约、免费的 Windows 纯文本翻译工具。仅依赖 Python 标准库，无需安装第三方包。适合日常查词、短句翻译、剪贴板翻译和多引擎对照。

## 界面

<p align="center">
  <img src="assets/images/homepage.png" alt="主界面" width="45%">
  &nbsp;&nbsp;
  <img src="assets/images/setting.png" alt="设置界面" width="45%">
</p>

## 功能

- 翻译引擎：谷歌、百度、DeepL、自定义AI
- 谷歌免费接口开箱即用
- 自动检测源语言
- 翻译历史记录保存

可配置功能：

- **自动翻译** — 输入停止约 1 秒后自动翻译
- **剪贴板翻译** — 复制文本后自动填入并翻译
- **自动复制** — 翻译完成后自动复制译文
- **窗口置顶** — 窗口保持在其他窗口上方

## 快速开始

需要 Python 3.8+。

```bash
# 方式一：双击运行
run.bat

# 方式二：命令行
python src/main.py
```

## 使用

配置翻译引擎和相关参数后，点击保存。
选择源语言、目标语言、翻译引擎，输入文本后按 `Enter` 或点击翻译按钮。

| 快捷键 | 功能 |
| --- | --- |
| `Enter` | 翻译 |
| `Ctrl + Enter` / `Shift + Enter` | 换行 |
| `Escape` | 清空输入和结果 |

支持语言：自动检测源语言，目标语言覆盖中文、英语、日语、韩语、法语、德语、俄语、西班牙语。

## 翻译引擎

| 引擎 | 接口类型 | 需要配置 |
| --- | --- | --- |
| 谷歌翻译 | 免费接口（默认）/ Cloud API | 免费接口不需要；Cloud 模式需要 API Key |
| 百度翻译 | 通用翻译 API | AppID + SecretKey |
| DeepL | Free API / Pro API | API Key |
| 自定义 AI 1 / 2 | OpenAI 兼容接口 | API Key、Base URL、模型名 |

> 谷歌免费接口为公共接口，开箱即用，但稳定性受网络环境和服务状态影响，国内网络下可能不可用。如需更高稳定性，建议配置 Google Cloud、DeepL、百度或自定义 AI 接口。

## 项目结构

```
River Translate/
├── src/
│   ├── main.py         # 主程序入口
│   ├── translator.py   # 翻译引擎实现
│   └── config.py       # 配置与历史记录管理
├── assets/
│   └── images/         # 截图等图片资源
├── user_data/          # 用户配置与历史文件
├── run.bat             # Windows 一键启动脚本
└── README.md
```

## 隐私

`user_data/` 目录存放本地配置和翻译历史，可能包含 API Key 和翻译文本，请勿分享该目录。

翻译时，输入文本会发送至所选翻译服务。请根据自身隐私需求选择合适的引擎。

## 常见问题

<details>
<summary>双击 run.bat 没反应</summary>

通常是 Python 未安装或未加入系统 PATH。在命令行运行 `python --version` 检查。如未显示版本号，请重新安装 Python 并勾选 "Add Python to PATH"。
</details>

<details>
<summary>谷歌免费翻译不可用或结果异常</summary>

谷歌免费接口不是正式付费 API，可能受网络环境和服务状态影响，在国内网络下可能无法访问。可稍后重试，或切换到其他已配置的引擎。
</details>

<details>
<summary>百度、DeepL、自定义 AI 为什么不能直接用</summary>

这些接口需要自行准备对应平台的 API Key 或账号信息，在设置中配置并保存后即可使用。
</details>

## 许可

[MIT](LICENSE)
