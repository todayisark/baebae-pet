# Baebae Pet

[中文](#中文) | [English](#english)

## 中文

Baebae Pet 是一个轻量级 macOS 桌面宠物框架。它专注于低打扰陪伴、状态动画、键盘活动感知、休息提醒和可替换素材包，而不是复杂 AI 助手或高性能 3D 系统。

当前项目仍处于 beta / testing 阶段，主要用于 macOS 本地验证。

### 功能

- 透明、无边框、可拖拽的桌面宠物窗口
- macOS 原生置顶处理，支持跨 Space 和全屏辅助窗口
- PNG 帧动画系统，每个状态一个目录
- 键盘输入感知：打字、专注打字、停止打字后恢复 idle
- 鼠标和妙控板点击不会触发 typing
- 点击回应、拖拽状态、右键菜单
- 休息提醒气泡，确认后重置计时
- 吃饭提醒：可指定三个本地时间，到点切换吃饭动画并弹出提醒
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

### 安装和运行

要求：

- macOS
- Python 3.11+
- 辅助功能权限，用于监听键盘和鼠标活动

从源码运行：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

如果输入监听没有生效，请到：

```text
系统设置 -> 隐私与安全性 -> 辅助功能
```

把当前终端 App 或打包后的 Baebae Pet App 加进去，然后重新启动程序。

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
│   ├── 0.png
│   ├── 1.png
│   └── ...
├── typing/
│   ├── 0.png
│   └── ...
├── typing_flow/
├── sleep/
├── meal/
├── jump/
├── remind/
├── poke/
└── drag/
```

`manifest.json` 示例：

```json
{
  "name": "my_pet",
  "author": "your_name",
  "version": "0.1",
  "frameSize": [200, 200],
  "animations": {
    "idle": { "fps": 8 },
    "typing": { "fps": 8 },
    "typing_flow": { "fps": 8 },
    "sleep": { "fps": 8 },
    "meal": { "fps": 8 },
    "jump": { "fps": 8 },
    "remind": { "fps": 8 },
    "poke": { "fps": 8 },
    "drag": { "fps": 8 }
  }
}
```

帧文件按数字顺序加载，建议使用透明背景 PNG。

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

当前代码可以用 PyInstaller 生成 macOS beta 包。beta 包仍是 ad-hoc 签名，首次运行或更新后可能需要重新添加辅助功能权限。正式分发前需要整理稳定的打包脚本、Developer ID 签名和 notarization 流程。

### License

Apache License 2.0. See [LICENSE](LICENSE).

---

## English

Baebae Pet is a lightweight desktop pet framework for macOS. It focuses on quiet companionship, state-based animation, keyboard activity detection, break reminders, and replaceable pet asset packs instead of complex AI assistant behavior or heavy 3D rendering.

The project is currently in beta / testing and is mainly validated on macOS.

### Features

- Transparent, frameless, draggable desktop pet window
- Native macOS always-on-top handling with Spaces and fullscreen support
- PNG frame animation system, one folder per state
- Keyboard-aware states: typing, typing flow, and idle after typing stops
- Mouse and trackpad clicks do not trigger typing
- Click reaction, drag state, and context menu
- Break reminder bubble with dismiss/reset behavior
- Meal reminders: configure three local wall-clock times for meal animation and a reminder bubble
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

### Install And Run

Requirements:

- macOS
- Python 3.11+
- Accessibility permission for keyboard and mouse activity monitoring

Run from source:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

If input monitoring does not work, open:

```text
System Settings -> Privacy & Security -> Accessibility
```

Add your terminal app or the packaged Baebae Pet app, then restart Baebae Pet.

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
│   ├── 0.png
│   ├── 1.png
│   └── ...
├── typing/
│   ├── 0.png
│   └── ...
├── typing_flow/
├── sleep/
├── meal/
├── jump/
├── remind/
├── poke/
└── drag/
```

Example `manifest.json`:

```json
{
  "name": "my_pet",
  "author": "your_name",
  "version": "0.1",
  "frameSize": [200, 200],
  "animations": {
    "idle": { "fps": 8 },
    "typing": { "fps": 8 },
    "typing_flow": { "fps": 8 },
    "sleep": { "fps": 8 },
    "meal": { "fps": 8 },
    "jump": { "fps": 8 },
    "remind": { "fps": 8 },
    "poke": { "fps": 8 },
    "drag": { "fps": 8 }
  }
}
```

Frames are loaded in numeric order. Transparent PNG files are recommended.

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

The code can currently be packaged into a macOS beta build with PyInstaller. Beta builds are still ad-hoc signed, so macOS may require Accessibility permission again after first launch or updates. A stable release flow still needs a dedicated build script, Developer ID signing, and notarization.

### License

Apache License 2.0. See [LICENSE](LICENSE).
