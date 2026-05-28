# Baebae Pet

[中文](#中文) | [English](#english)

## 中文

Baebae Pet 是一个轻量级跨平台桌面宠物框架，支持 macOS 和 Windows。它专注于低打扰陪伴、状态动画、键盘活动感知、休息提醒和可替换素材包，而不是复杂 AI 助手或高性能 3D 系统。

当前项目仍处于 beta / testing 阶段。

**最新版本：v0.3.0-beta** · [下载](https://github.com/todayisark/baebae-pet/releases/latest)

### 功能

- 透明、无边框、可拖拽的桌面宠物窗口
- macOS 原生置顶处理，支持跨 Space 和全屏辅助窗口；Windows 同样支持置顶
- PNG 帧动画系统，每个状态一个目录
- 键盘输入感知：打字、专注打字、停止打字后恢复 idle
- 鼠标和妙控板点击不会触发 typing
- 点击回应、拖拽状态、右键菜单
- 休息提醒气泡，确认后重置计时
- 吃饭提醒：可指定三个本地时间，到点切换吃饭动画并弹出提醒
- 自动更新检测：启动时检查新版本，有更新时显示提醒气泡
- 导入 `.zip` 素材包
- 打开当前宠物的本地素材目录，方便直接查看或替换图片
- 导出模板素材包到 `~/Downloads/pet_template.zip`，方便基于示例图制作自己的宠物
- Dock 图标自动从当前宠物的 `idle/0.png` 读取
- 右键菜单支持中文 / English 切换
- 首次启动引导界面，支持导入素材包、直接使用模板或导出模板后自定义

### 状态

| 状态          | 说明                 |
| ------------- | -------------------- |
| `idle`        | 待机                 |
| `typing`      | 检测到键盘输入       |
| `typing_flow` | 连续输入达到专注阈值 |
| `sleep`       | 长时间无活动         |
| `meal`        | 吃饭提醒             |
| `jump`        | 启动动画             |
| `remind`      | 休息提醒             |
| `poke`        | 点击回应             |
| `drag`        | 拖拽中               |

所有状态根据素材是否存在自动启用或禁用——只要对应文件夹存在且有 PNG 帧，该状态就会生效，无需手动配置。

#### idle 子动作

在 `idle/` 目录下创建子文件夹可以添加随机待机动作，程序每隔 3 分钟随机播放一个（播完后自动回到默认待机）。`idle/` 根目录的帧始终作为默认待机循环。

推荐命名：使用描述动作的英文小写词，例如：

```text
idle/
├── 0.png         ← 默认待机帧（循环播放）
├── 1.png
├── ...
├── stretch/      ← 伸懒腰
├── yawn/         ← 打哈欠
├── look_around/  ← 四处张望
├── sneeze/       ← 打喷嚏
└── wave/         ← 挥手
```

子文件夹的 FPS 可以在 `manifest.json` 中单独指定，键名为 `"idle/stretch"`（以此类推）；若未指定则默认 10 FPS。

#### poke 分区

点击宠物时，程序会根据点击位置将画面分为上中下三段，分别在 `poke/up/`、`poke/mid/`、`poke/down/` 中查找对应动画。若某个区域没有素材，则回退到 `poke/` 根目录的默认 poke 动画。三个子文件夹都是可选的，可以只提供其中几个。

### 安装和运行

#### 直接下载（推荐）

前往 [Releases](https://github.com/todayisark/baebae-pet/releases/latest) 下载最新版本：

- **macOS (Apple Silicon)**：下载 `baebae-pet-vX.X.X-beta-macos-arm64.zip`，解压后将 `Baebae Pet Beta.app` 拖入「应用程序」文件夹；首次打开需在「**系统设置 → 隐私与安全性**」中点击「仍要打开」，并在「辅助功能」中允许该 App
- **Windows**：下载 `snappy-pet-vX.X.X-beta-windows-x64.zip`，解压后直接运行 `Snappy Pet Beta.exe`；若弹出 SmartScreen 提示，点击「更多信息 → 仍要运行」

#### 从源码运行

要求：

- macOS 或 Windows
- Python 3.11+
- 辅助功能权限（macOS）或后台输入监听权限（Windows），用于监听键盘和鼠标活动

从源码运行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

如果输入监听没有生效：

- **macOS**：前往「系统设置 → 隐私与安全性 → 辅助功能」，将终端 App 或打包后的 App 加进去，然后重新启动程序
- **Windows**：以普通用户身份运行通常即可；如仍无法监听输入，尝试以管理员身份运行

### 使用

**首次启动**时会显示引导窗口，可以：

- 导出模板到 `~/Downloads/pet_template.zip`，解压后替换图片再导入
- 打开模板所在目录
- 直接使用内置模板启动（无需导入）
- 导入已有的 `.zip` 素材包
- 切换界面语言（中文 / English）

启动后宠物出现在桌面上。**右键宠物**可以打开菜单：

- 预览不同状态动画
- 导入素材包
- 打开当前宠物的素材目录
- 导出模板素材包
- 打开使用手册
- 打开设置窗口，调整语言、大小、透明度、休息提醒和吃饭提醒
- 清除所有数据
- 退出程序

### 素材包

素材包是一个包含 `manifest.json` 和状态目录的文件夹，可以压缩成 `.zip` 后通过右键菜单导入。

如果想基于示例素材制作自己的宠物，可以在引导界面或右键菜单选择”导出模板”。程序会把模板导出到 `~/Downloads/pet_template.zip`。先解压这个 zip，替换各状态目录中的 PNG，修改 `manifest.json` 里的 `name`、`author` 和 `version`，再把素材包文件夹重新压缩为 zip 后导入。

示例结构：

```text
my_pet/
├── manifest.json
├── idle/
│   ├── 0.png         ← 默认待机帧
│   ├── 1.png
│   ├── ...
│   ├── stretch/      ← 随机子动作（可选）
│   │   ├── 0.png
│   │   └── ...
│   └── yawn/         ← 随机子动作（可选）
│       ├── 0.png
│       └── ...
├── typing/
│   ├── 0.png
│   └── ...
├── typing_flow/
├── sleep/
├── meal/
├── jump/
├── remind/
├── poke/
│   ├── 0.png         ← 默认 poke（点击任意位置回退用）
│   ├── ...
│   ├── up/           ← 点击上段触发（可选）
│   │   └── 0.png
│   ├── mid/          ← 点击中段触发（可选）
│   │   └── 0.png
│   └── down/         ← 点击下段触发（可选）
│       └── 0.png
└── drag/
```

**所有状态文件夹均为可选**。程序会自动检测哪些文件夹存在且有 PNG 帧，不存在则跳过该状态，无需修改 `manifest.json`。

`manifest.json` 示例：

```json
{
  "name": "my_pet",
  "author": "your_name",
  "version": "0.1",
  "frameSize": [200, 200],
  "animations": {
    "idle": { "fps": 8 },
    "idle/stretch": { "fps": 10 },
    "idle/yawn": { "fps": 6 },
    "typing": { "fps": 8 },
    "typing_flow": { "fps": 8 },
    "sleep": { "fps": 8 },
    "meal": { "fps": 8 },
    "jump": { "fps": 8 },
    "remind": { "fps": 8 },
    "poke": { "fps": 8 },
    "poke/up": { "fps": 8 },
    "poke/mid": { "fps": 8 },
    "poke/down": { "fps": 8 },
    "drag": { "fps": 8 }
  }
}
```

子动作和 poke 分区的 FPS 可以在 `manifest.json` 中单独指定，未指定则默认 10 FPS。帧文件按数字顺序加载，建议使用透明背景 PNG。

### 开发

运行测试：

```bash
.venv/bin/python -m unittest discover -s tests
```

快速语法检查：

```bash
.venv/bin/python -m py_compile main.py engine/*.py ui/*.py config/*.py tests/*.py
```

### 项目结构

```text
baebae-pet/
├── main.py                    # 程序入口和状态协调
├── engine/
│   ├── activity_monitor.py    # 键盘/鼠标活动监听
│   ├── animator.py            # 素材加载和动画播放数据
│   ├── i18n.py                # 中英文文本
│   ├── macos_window.py        # macOS 原生窗口置顶处理
│   ├── pet_template.py        # 模板素材包导出
│   ├── reminder.py            # 休息提醒气泡
│   ├── state_machine.py       # 宠物状态机
│   ├── update_checker.py      # 自动更新检测
│   └── window.py              # 宠物窗口和交互菜单
├── config/
│   └── settings.py            # 用户配置和素材目录管理
├── ui/
│   └── onboarding.py          # 首次启动引导界面
├── pets/
│   └── default_pet/           # 内置模板素材包
└── tests/                     # 行为测试
```

### 用户数据

当前 beta 版本的运行时配置和导入的素材包会写入 legacy 目录：

```text
~/Library/Application Support/baebae/
```

右键菜单中的“清除所有数据”会删除这个目录并退出程序。

### 打包状态

当前代码可以用 PyInstaller 分别生成 macOS 和 Windows beta 包：

| 平台 | 包名 | 压缩后大小 |
| ---- | ---- | ---------- |
| macOS (Apple Silicon) | `Baebae Pet Beta.app` | ~32 MB |
| Windows (x64) | `Snappy Pet Beta.exe` | — |

macOS beta 包为 ad-hoc 签名，首次运行或更新后可能需要重新添加辅助功能权限。正式分发前还需要 Developer ID 签名和 notarization 流程。

### License

Apache License 2.0. See [LICENSE](LICENSE).

---

## English

Baebae Pet is a lightweight cross-platform desktop pet framework for macOS and Windows. It focuses on quiet companionship, state-based animation, keyboard activity detection, break reminders, and replaceable pet asset packs instead of complex AI assistant behavior or heavy 3D rendering.

The project is currently in beta / testing.

**Latest release: v0.3.0-beta** · [Download](https://github.com/todayisark/baebae-pet/releases/latest)

### Features

- Transparent, frameless, draggable desktop pet window
- Native macOS always-on-top handling with Spaces and fullscreen support; always-on-top also supported on Windows
- PNG frame animation system, one folder per state
- Keyboard-aware states: typing, typing flow, and idle after typing stops
- Mouse and trackpad clicks do not trigger typing
- Click reaction, drag state, and context menu
- Break reminder bubble with dismiss/reset behavior
- Meal reminders: configure three local wall-clock times for meal animation and a reminder bubble
- Auto update checker: detects new releases on startup and shows an update bubble
- Import `.zip` pet packs
- Open the current pet's local asset folder for quick inspection or image replacement
- Export template pack to `~/Downloads/pet_template.zip` for customization
- Dock icon automatically set from the active pet's `idle/0.png`
- Context menu language switch between Chinese and English
- First-run onboarding with options to import a pack, use the bundled template directly, or export the template for customization

### States

| State         | Meaning                                       |
| ------------- | --------------------------------------------- |
| `idle`        | Idle                                          |
| `typing`      | Keyboard input detected                       |
| `typing_flow` | Continuous typing reached the focus threshold |
| `sleep`       | Long inactivity                               |
| `meal`        | Meal reminder                                 |
| `jump`        | Startup animation                             |
| `remind`      | Break reminder                                |
| `poke`        | Click reaction                                |
| `drag`        | Dragging                                      |

All states are auto-enabled or disabled based on whether the asset folder exists and contains PNG frames — no manual configuration required.

#### Idle sub-actions

Create sub-folders inside `idle/` to add random idle animations. The app picks one randomly every 3 minutes, plays it once, then returns to the default idle loop. Frames in the `idle/` root are always used as the default idle loop.

Suggested naming — use short, lowercase English action words:

```text
idle/
├── 0.png         ← default idle frames (looping)
├── 1.png
├── ...
├── stretch/      ← stretch
├── yawn/         ← yawn
├── look_around/  ← look around
├── sneeze/       ← sneeze
└── wave/         ← wave
```

Sub-folder FPS can be set in `manifest.json` using the key `"idle/stretch"` (and so on); defaults to 10 FPS if omitted.

#### Poke zones

When the pet is clicked, the app divides the window into three vertical zones and looks for animations in `poke/up/`, `poke/mid/`, and `poke/down/`. If a zone has no assets, it falls back to the default `poke/` animation. All three sub-folders are optional.

### Install And Run

#### Download (recommended)

Go to [Releases](https://github.com/todayisark/baebae-pet/releases/latest) and download the latest build:

- **macOS (Apple Silicon)**: download `baebae-pet-vX.X.X-beta-macos-arm64.zip`, unzip it, and drag `Baebae Pet Beta.app` to your Applications folder; on first launch go to **System Settings → Privacy & Security** to allow the app and enable it under **Accessibility**
- **Windows**: download `snappy-pet-vX.X.X-beta-windows-x64.zip`, unzip it, and run `Snappy Pet Beta.exe`; if Windows SmartScreen appears, click **More info → Run anyway**

#### Run from source

Requirements:

- macOS or Windows
- Python 3.11+
- Accessibility permission (macOS) or background input monitoring (Windows) for keyboard and mouse activity

Run from source:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

If input monitoring does not work:

- **macOS**: go to **System Settings → Privacy & Security → Accessibility**, add your terminal app or the packaged app, then restart Baebae Pet
- **Windows**: running as a normal user usually works; if input is still not detected, try running as Administrator

### Usage

**On first launch**, an onboarding window appears with options to:

- Export the template to `~/Downloads/pet_template.zip`, customize it, then import
- Open the template folder directly
- Use the bundled template as-is (no import needed)
- Import an existing `.zip` pet pack
- Toggle the interface language (Chinese / English)

After launch, the pet appears on the desktop. **Right-click the pet** to open the menu:

- Preview animation states
- Import a pet pack
- Open the current pet folder
- Export a template pet pack
- Open the manual
- Open settings to adjust language, size, opacity, break reminders, and meal reminders
- Clear all data
- Quit

### Pet Packs

A pet pack is a folder containing `manifest.json` and one folder per animation state. It can be zipped and imported from the context menu.

To create your own pet from the sample frames, choose "Export Template" from the onboarding window or the context menu. Baebae Pet exports the template to `~/Downloads/pet_template.zip`. Unzip it, replace the PNG frames, edit `name`, `author`, and `version` in `manifest.json`, then zip the pet folder again and import it.

Example structure:

```text
my_pet/
├── manifest.json
├── idle/
│   ├── 0.png         ← default idle frames
│   ├── 1.png
│   ├── ...
│   ├── stretch/      ← random sub-action (optional)
│   │   ├── 0.png
│   │   └── ...
│   └── yawn/         ← random sub-action (optional)
│       ├── 0.png
│       └── ...
├── typing/
│   ├── 0.png
│   └── ...
├── typing_flow/
├── sleep/
├── meal/
├── jump/
├── remind/
├── poke/
│   ├── 0.png         ← default poke fallback
│   ├── ...
│   ├── up/           ← top-zone click (optional)
│   │   └── 0.png
│   ├── mid/          ← mid-zone click (optional)
│   │   └── 0.png
│   └── down/         ← bottom-zone click (optional)
│       └── 0.png
└── drag/
```

**All state folders are optional.** The app automatically detects which folders exist and contain PNG frames; missing folders are silently skipped without any `manifest.json` changes required.

Example `manifest.json`:

```json
{
  "name": "my_pet",
  "author": "your_name",
  "version": "0.1",
  "frameSize": [200, 200],
  "animations": {
    "idle": { "fps": 8 },
    "idle/stretch": { "fps": 10 },
    "idle/yawn": { "fps": 6 },
    "typing": { "fps": 8 },
    "typing_flow": { "fps": 8 },
    "sleep": { "fps": 8 },
    "meal": { "fps": 8 },
    "jump": { "fps": 8 },
    "remind": { "fps": 8 },
    "poke": { "fps": 8 },
    "poke/up": { "fps": 8 },
    "poke/mid": { "fps": 8 },
    "poke/down": { "fps": 8 },
    "drag": { "fps": 8 }
  }
}
```

FPS for sub-actions and poke zones can be set individually in `manifest.json`; defaults to 10 FPS if omitted. Frames are loaded in numeric order. Transparent PNG files are recommended.

### Development

Run tests:

```bash
.venv/bin/python -m unittest discover -s tests
```

Quick syntax check:

```bash
.venv/bin/python -m py_compile main.py engine/*.py ui/*.py config/*.py tests/*.py
```

### Project Structure

```text
baebae-pet/
├── main.py                    # App entry point and state coordinator
├── engine/
│   ├── activity_monitor.py    # Keyboard and mouse activity monitor
│   ├── animator.py            # Asset loading and animation data
│   ├── i18n.py                # Chinese and English UI text
│   ├── macos_window.py        # Native macOS window level handling
│   ├── pet_template.py        # Template pet pack export
│   ├── reminder.py            # Break reminder bubble
│   ├── state_machine.py       # Pet state machine
│   ├── update_checker.py      # Auto update checker
│   └── window.py              # Pet window and context menu
├── config/
│   └── settings.py            # User settings and pet directory management
├── ui/
│   └── onboarding.py          # First-run onboarding UI
├── pets/
│   └── default_pet/           # Bundled template pet pack
└── tests/                     # Behavior tests
```

### User Data

The current beta stores runtime settings and imported pet packs in the legacy directory:

```text
~/Library/Application Support/baebae/
```

"Clear All Data" in the context menu deletes this directory and quits the app.

### Packaging Status

The code can be packaged with PyInstaller for both macOS and Windows:

| Platform | Bundle | Compressed size |
| -------- | ------ | --------------- |
| macOS (Apple Silicon) | `Baebae Pet Beta.app` | ~32 MB |
| Windows (x64) | `Snappy Pet Beta.exe` | — |

macOS beta builds are ad-hoc signed, so macOS may require Accessibility permission again after first launch or updates. A stable release flow still needs Developer ID signing and notarization.

### License

Apache License 2.0. See [LICENSE](LICENSE).
