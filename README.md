# Snappy Pet

[中文](#中文) | [English](#english)

## 中文

Snappy Pet 是一个轻量级 macOS 桌面宠物框架。它专注于低打扰陪伴、状态动画、键盘活动感知、休息提醒和可替换素材包，而不是复杂 AI 助手或高性能 3D 系统。

当前项目仍处于 beta / testing 阶段，主要用于 macOS 本地验证。

### 功能

- 透明、无边框、可拖拽的桌面宠物窗口
- macOS 原生置顶处理，支持跨 Space 和全屏辅助窗口
- PNG 帧动画系统，每个状态一个目录
- 键盘输入感知：打字、专注打字、停止打字后恢复 idle
- 鼠标和妙控板点击不会触发 typing
- 点击回应、拖拽状态、右键菜单
- 休息提醒气泡，确认后重置计时
- 导入 `.zip` 素材包
- 打开当前宠物的本地素材目录，方便直接查看或替换图片
- 导出 `pet-template.zip` 模板素材包，方便基于示例图制作自己的宠物
- 右键菜单支持中文 / English 切换
- 首次启动自动初始化用户配置和默认素材

### 状态

| 状态 | 说明 |
| --- | --- |
| `idle` | 待机 |
| `typing` | 检测到键盘输入 |
| `typing_flow` | 连续输入达到专注阈值 |
| `sleep` | 长时间无活动 |
| `jump` | 启动动画 |
| `remind` | 休息提醒 |
| `poke` | 点击回应 |
| `drag` | 拖拽中 |

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

把当前终端 App 或打包后的 Snappy Pet App 加进去，然后重新启动程序。

### 使用

启动后会显示默认宠物。右键宠物可以打开菜单：

- 预览不同状态动画
- 切换大小
- 导入素材包
- 打开当前宠物的素材目录
- 导出模板素材包
- 打开使用手册
- 切换中文 / English
- 清除所有数据
- 退出程序

### 素材包

素材包是一个包含 `manifest.json` 和状态目录的文件夹，可以压缩成 `.zip` 后通过右键菜单导入。

如果想基于示例素材制作自己的宠物，可以在右键菜单选择“导出模板素材包”。程序会生成 `pet-template.zip`。先解压这个 zip，替换各状态目录中的 PNG，修改 `manifest.json` 里的 `name`、`author` 和 `version`，再把素材包文件夹重新压缩为 zip 后导入。

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
    "typing": { "fps": 12 },
    "typing_flow": { "fps": 16 },
    "sleep": { "fps": 4 },
    "jump": { "fps": 10 },
    "remind": { "fps": 8 },
    "poke": { "fps": 10 },
    "drag": { "fps": 10 }
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
snappy-pet/
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
│   └── onboarding.py          # 首次启动导入素材包界面
├── pets/
│   └── default_pet/           # 默认素材包
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

Snappy Pet is a lightweight desktop pet framework for macOS. It focuses on quiet companionship, state-based animation, keyboard activity detection, break reminders, and replaceable pet asset packs instead of complex AI assistant behavior or heavy 3D rendering.

The project is currently in beta / testing and is mainly validated on macOS.

### Features

- Transparent, frameless, draggable desktop pet window
- Native macOS always-on-top handling with Spaces and fullscreen support
- PNG frame animation system, one folder per state
- Keyboard-aware states: typing, typing flow, and idle after typing stops
- Mouse and trackpad clicks do not trigger typing
- Click reaction, drag state, and context menu
- Break reminder bubble with dismiss/reset behavior
- Import `.zip` pet packs
- Open the current pet's local asset folder for quick inspection or image replacement
- Export `pet-template.zip` so users can customize a pet from the example frames
- Context menu language switch between Chinese and English
- First-run initialization for settings and the default pet pack

### States

| State | Meaning |
| --- | --- |
| `idle` | Idle |
| `typing` | Keyboard input detected |
| `typing_flow` | Continuous typing reached the focus threshold |
| `sleep` | Long inactivity |
| `jump` | Startup animation |
| `remind` | Break reminder |
| `poke` | Click reaction |
| `drag` | Dragging |

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

Add your terminal app or the packaged Snappy Pet app, then restart Snappy Pet.

### Usage

After launch, the default pet appears on the desktop. Right-click the pet to open the menu:

- Preview animation states
- Change size
- Import a pet pack
- Open the current pet folder
- Export a template pet pack
- Open the manual
- Switch between Chinese and English
- Clear all data
- Quit

### Pet Packs

A pet pack is a folder containing `manifest.json` and one folder per animation state. It can be zipped and imported from the context menu.

To create your own pet from the sample frames, choose "Export Template Pack" from the context menu. Snappy Pet creates `pet-template.zip`. Unzip it, replace the PNG frames, edit `name`, `author`, and `version` in `manifest.json`, then zip the pet folder again and import it.

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
    "typing": { "fps": 12 },
    "typing_flow": { "fps": 16 },
    "sleep": { "fps": 4 },
    "jump": { "fps": 10 },
    "remind": { "fps": 8 },
    "poke": { "fps": 10 },
    "drag": { "fps": 10 }
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
snappy-pet/
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
│   └── onboarding.py          # First-run pet pack import UI
├── pets/
│   └── default_pet/           # Default pet pack
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
