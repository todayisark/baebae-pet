# baebae Framework

一个轻量级桌面宠物框架。项目目标不是做复杂 AI 助手，而是提供一个低打扰、低占用、可扩展的桌面陪伴基础设施：窗口常驻、状态动画、输入感知、休息提醒和素材包导入。

当前版本主要面向 macOS 开发和验证。

## 功能

- 透明无边框桌面宠物窗口
- macOS 原生置顶处理，支持跨 Space 和全屏辅助窗口
- PNG 帧动画系统，每个状态一个目录
- 键盘输入感知：打字、专注打字、停止打字后回到 idle
- 鼠标交互：点击回应、拖拽移动、右键菜单
- 休息提醒气泡，支持确认后重置计时
- 素材包导入，框架和角色素材解耦
- 首次启动自动初始化用户配置和默认素材

## 状态

| 状态          | 说明                 |
| ------------- | -------------------- |
| `idle`        | 待机                 |
| `typing`      | 检测到键盘输入       |
| `typing_flow` | 连续输入达到专注阈值 |
| `sleep`       | 长时间无活动         |
| `jump`        | 启动动画             |
| `remind`      | 休息提醒             |
| `poke`        | 点击回应             |
| `drag`        | 拖拽中               |

鼠标和妙控板点击不会触发 `typing`。`typing` 只由键盘输入触发；键盘停止 10 秒后恢复 `idle`。

## 环境要求

- macOS
- Python 3.11+
- 辅助功能权限：用于 `pynput` 监听键盘和鼠标活动

安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果输入监听没有生效，请到：

```text
系统设置 -> 隐私与安全性 -> 辅助功能
```

把当前终端 App 或打包后的 baebae App 加进去，然后重新启动程序。

## 运行

```bash
. .venv/bin/activate
python main.py
```

启动后会显示默认宠物。右键宠物可以打开菜单，预览状态、切换大小、导入素材包或退出。

## 测试

```bash
.venv/bin/python -m unittest tests.test_activity_monitor tests.test_pet_controller
```

快速语法检查：

```bash
.venv/bin/python -m py_compile main.py engine/*.py ui/*.py config/*.py tests/*.py
```

## 素材包格式

素材包是一个包含 `manifest.json` 和状态目录的文件夹，也可以打成 `.zip` 后通过右键菜单导入。

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

帧文件按数字排序加载，建议使用透明背景 PNG。

## 项目结构

```text
baebae-framework/
├── main.py                    # 程序入口和状态协调
├── engine/
│   ├── activity_monitor.py    # 键盘/鼠标活动监听
│   ├── animator.py            # 素材加载和动画播放数据
│   ├── macos_window.py        # macOS 原生窗口置顶处理
│   ├── reminder.py            # 工作提醒气泡
│   ├── state_machine.py       # 宠物状态机
│   └── window.py              # 宠物窗口和交互菜单
├── config/
│   └── settings.py            # 用户配置和素材目录管理
├── ui/
│   └── onboarding.py          # 首次启动导入素材包界面
├── pets/
│   └── default_pet/           # 默认素材包
├── tests/                     # 行为测试
└── doc/
    └── 需求.md                # 设计文档
```

`bunny_core.py`、`mac_bunny.py` 和 `setup.py` 是早期 macOS demo，保留用于对照窗口和动画实现；当前框架入口是 `main.py`。

## 用户数据

运行时配置和导入的素材包会写入：

```text
~/Library/Application Support/baebae/
```

右键菜单中的“清除所有数据”会删除这个目录并退出程序。

## 打包状态

当前代码已经按 PyInstaller 方向组织依赖，但打包脚本还没有整理成正式发布流程。早期 `setup.py` 是 py2app demo 配置，不代表当前框架的最终打包方式。
