# Pop Translate

[English](./README_EN.md) | **中文**

一款专为 Linux 设计的轻量、美观的 AI 划词翻译与解释工具（原生支持 GTK4，完美兼容 Wayland 与 X11）。

选中任意文本，按下全局快捷键，即可在 macOS 风格的硬件加速窗口中，瞬间获得 AI 翻译、概念解析或进行多轮交互式对话。

![screenshot](screenshot_v2.png)

## ✨ 特性

- **🚀 图形化初次配置** — 告别繁琐的命令行！首次运行时若未配置 API Key，将自动弹出精致的配置向导，指引您填写 API 密钥、API 地址以及模型名称。
- **🎨 极简 macOS 视觉美学** — 升级至现代黑白灰极简白色主题，配备精致的胶囊药丸式标签页、卡片阴影、钢灰色左边框、重绘下拉框以及专门优化的系统字体栈（`Inter`, `Cantarell`, `Roboto`, `思源黑体`）。
- **🗂️ 三合一多功能工作流**：
  - **翻译 (Translate)** — 智能中英文双向自动检测与互译。支持在窗口内直接编辑原文并重新翻译。
  - **解释 (Explain)** — 在优雅的卡片布局中，对生词、学术术语或复杂概念提供详尽的 AI 深度解析。
  - **对话 (Chat)** — 线程安全的交互式聊天气泡界面。针对选中的文本进行语法剖析、用法追问等深度交流。
- **🧠 完美支持思考模式** — 支持一键切换/快捷键开启深度思考（如 DeepSeek R1 思考模型或推理模型），支持动态展示思考过程。
- **⚡ 全键盘友好导航** — 专为效率极客打造，完全免鼠标操作。通过易记的快捷键进行切页、复制、重新生成与设置开关。
- **📭 动态高度自适应** — 聊天输入框采用 TextView 多行文本设计，输入时视窗随行数增加平滑长高，发送或清空后即时缩回紧凑尺寸。
- **🔒 敏感凭证防泄漏** — 内置 API 报错拦截与脱敏机制，自动通过正则红线过滤并隐藏报错日志中可能出现的 API Key、Bearer Token 等凭证，保障开源安全。
- **💾 SQLite 本地智能缓存** — 相同文本的二次划词直接命中本地 SQLite 缓存，避免重复请求 API 产生资费；缓存记录超过 24 小时自动清理，保持轻量。
- **🛸 极致轻量，零后台常驻** — 纯粹的弹窗工具设计，窗口关闭后所有子线程及应用进程立即安全退出，不占用任何后台系统内存。

---

## ⌨️ 键盘快捷键导航

为了极致的划词效率，Pop Translate 支持全键盘操作。

### 本地窗口快捷键（窗口激活时有效）：
- `S` — 切换至 **翻译** 标签页
- `W` — 切换至 **解释** 标签页
- `C` — 切换至 **对话** 标签页
- `E` — **编辑** 原文
- `R` — **重新生成** 当前内容（重译/重解释/重新发送对话）
- `Y` — **复制** 译文（仅在翻译页有效）
- `F` — **网络搜索** 选中文本（若选中的是 URL 则直接在默认浏览器中打开，否则使用 Bing 搜索）
- `T` — **开启/关闭 思考模式**（Thinking Mode）
- `X` — **开启/关闭 包含上下文**（仅在对话页有效）
- `Esc` — **关闭** 翻译视窗

---

## 📦 依赖要求

| 依赖项 | 用途 |
|-----------|---------|
| `python3` | 运行环境 |
| `python-gobject` | GTK4 Python 绑定库 |
| `gtk4` | GUI 工具包 |
| `wl-clipboard` | Wayland 划词剪贴板获取 |
| `xclip` (可选) | X11 桌面环境兼容获取 |
| `ydotool` (可选) | Wayland 下模拟按键复制选中内容 |
| `xdotool` (可选) | X11 下模拟按键复制选中内容 |

---

## 🚀 快速开始

### 1. 安装系统依赖

**Arch Linux:**
```bash
sudo pacman -S python python-gobject gtk4 wl-clipboard xclip ydotool
```

**Debian/Ubuntu:**
```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 wl-clipboard xclip ydotool
```

**Fedora:**
```bash
sudo dnf install python3 python3-gobject gtk4 wl-clipboard xclip ydotool
```

### 2. 安装 Pop Translate

克隆本仓库到本地，并运行安装脚本：
```bash
./install.sh
```

### 3. 启用 ydotool 守护进程（Wayland 推荐）

为了在按快捷键时自动复制选中内容，需要启用 ydotool 守护进程：

```bash
systemctl --user enable --now ydotool
```

> **注：** 未启用 ydotool 时，Pop Translate 仍可正常工作，但会读取剪贴板中已有的内容，而非当前选中的文字。X11 用户使用 xdotool，无需额外配置。

### 4. 初始化配置

在终端直接输入并运行 `pop-translate`，或初次通过全局快捷键唤醒。

由于是首次启动，程序将为您呈现配置向导：
1. 输入您的 **API Key**（支持任何兼容 OpenAI 格式的厂商，如 DeepSeek、OpenAI、月之暗面等）。
2. 输入您的 **API 地址**（默认为 DeepSeek: `https://api.deepseek.com/chat/completions`）。
3. 输入您的 **模型名称**（例如 `deepseek-chat` 或 `deepseek-reasoner`）。
4. 点击 **保存**。

您的配置将安全地保存在本地 `~/.config/pop-translate/config.json` 中。

*(当然，您也依然可以使用传统的环境变量方式，在 `.bashrc` 或 `.zshrc` 中导出 `POP_TRANSLATE_API_KEY`、`POP_TRANSLATE_API_URL` 和 `POP_TRANSLATE_MODEL`)*

### 5. 设置全局快捷键

**KDE Plasma:**
1. 打开 **系统设置** → **快捷键** → **自定义快捷键**。
2. 点击 **编辑** → **新建** → **全局快捷键** → **命令/URL**。
3. 命名为 `Pop Translate`。
4. 触发器：设置您习惯的全局热键（如 `Ctrl+Alt+T`）。
5. 动作：输入命令 `pop-translate`。
6. 点击 **应用**。

**其他桌面环境 (GNOME, i3, Sway, Hyprland, etc.):**
在您的桌面环境或窗口管理器设置中，将可执行命令 `pop-translate` 绑定到您指定的全局快捷键即可。

---

## 🛠️ 配置环境变量选项

如果您希望通过环境变量覆盖默认参数：

| 变量名 | 默认值 | 描述 |
|----------|---------|-------------|
| `POP_TRANSLATE_API_KEY` | *(必填)* | OpenAI 兼容的 API 密钥 |
| `POP_TRANSLATE_API_URL` | `https://api.deepseek.com/chat/completions` | API 终结点地址 |
| `POP_TRANSLATE_MODEL` | `deepseek-chat` | 调用的模型名称 |

---

## 🎨 主题样式自定义

界面样式完全基于 GTK4 CSS 硬件加速节点实现，核心样式位于 `pop_translate/css.py` 中。您可以自由修改该文件中的背景色、卡片阴影、圆角曲率或字体栈，以完美融入您 Linux 的桌面美化（Rice）风格。

---

## 📄 开源许可

本项目基于 **MIT License** 许可协议开源。详情请参阅 `LICENSE` 文件。
