"""
interaction.py — 交互行为控制层

职责：管理所有"原始输入事件 → 状态机变更"之间的有状态逻辑。

包括：
  - 最低播放轮数强制（确保 MEAL / REMIND / IDLE_RANDOM 等状态播满指定秒数后才允许切走）
  - Poke 区域计算 + poke/up 二次跟随检测（一定时间窗口内再次点击上方触发 up_double）
  - 拖拽速度采样、fast/slow 切换、长时间拖拽计时器

不负责：
  - 渲染（window.py）
  - 由系统活动驱动的宏观状态决策（main.py / PetController）
  - 动画资源加载与缓存（animator.py）
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QTimer

from engine.state_machine import ONE_SHOT_STATES, State

if TYPE_CHECKING:
    from engine.animator import Animator
    from engine.state_machine import StateMachine


# ---------------------------------------------------------------------------
# 可调参数
# ---------------------------------------------------------------------------

# 拖拽速度阈值（像素/秒），超过此值切换到 fast drag 动画
DRAG_FAST_THRESHOLD_PX_S: float = 600.0

# 速度平均窗口（秒），用于平滑抖动
DRAG_VEL_WINDOW_S: float = 0.15

# poke/up 跟随窗口（毫秒）：第一次点 up 之后，此时间内再次点 up 触发 up_double
POKE_UP_FOLLOWUP_MS: float = 2000.0

# 持续拖拽多久（毫秒）后切换到长时间拖拽动画
LONG_DRAG_DELAY_MS: int = 5000

# 各状态的最低播放时长（秒）。
# 运行时根据帧数和 fps 换算成最少完播轮数，因此用户替换素材后自动适应。
MIN_PLAY_SECONDS: dict[State, float] = {
    State.MEAL: 10.0,
    State.REMIND: 10.0,
    State.IDLE_RANDOM: 5.0,
}


# ---------------------------------------------------------------------------
# InteractionHandler
# ---------------------------------------------------------------------------

class InteractionHandler:
    """
    交互状态控制器。每个 PetWindow 持有一个实例。

    PetWindow 把原始鼠标事件和帧循环事件转发过来，本类决定何时切换动画状态，
    并通过 *on_state_changed* 回调通知窗口刷新显示。
    """

    def __init__(
        self,
        animator: Animator,
        state_machine: StateMachine,
        on_state_changed: Callable[[], None],
    ) -> None:
        self._animator = animator
        self._sm = state_machine
        self._notify = on_state_changed  # 状态变更后通知窗口重绘

        # ── 最低播放计数 ──────────────────────────────────────────────────────
        # 每完播一轮减 1；归零后 one-shot 状态才允许 restore，
        # timed 状态（MEAL / REMIND）才允许 PetController 切走。
        self._min_loops_remaining: int = 0

        # ── Poke 跟随追踪 ──────────────────────────────────────────────────────
        self._last_click_time: float = 0.0        # 上次点击 up 区域的单调时间戳
        self._last_click_zone: str | None = None  # 上次点击的 zone 名

        # ── 拖拽状态 ──────────────────────────────────────────────────────────
        self._drag_is_long: bool = False   # 是否已进入长时间拖拽阶段
        self._drag_is_fast: bool = False   # 当前速度是否超过阈值
        # 速度采样环形缓冲，元素为 (monotonic_time, QPoint)
        self._drag_vel_samples: deque = deque()

        # 5 秒后触发长时间拖拽切换
        self._long_drag_timer = QTimer()
        self._long_drag_timer.setSingleShot(True)
        self._long_drag_timer.timeout.connect(self._on_long_drag_timer)

    # -------------------------------------------------------------------------
    # 外部接口：供 PetWindow 调用
    # -------------------------------------------------------------------------

    def set_animator(self, animator: Animator) -> None:
        """更换 Animator 引用（导入新素材包时调用）。"""
        self._animator = animator

    def recompute_min_loops(self) -> None:
        """
        状态切换后重新计算最低播放轮数。
        PetWindow.on_state_changed() 负责调用此方法。
        """
        min_s = MIN_PLAY_SECONDS.get(self._sm.state, 0.0)
        if min_s <= 0:
            self._min_loops_remaining = 0
            return
        anim = self._animator.get_animation(self._sm.state)
        cycle_s = anim.frame_count / anim.fps
        self._min_loops_remaining = math.ceil(min_s / cycle_s)

    def is_in_minimum_play_period(self) -> bool:
        """
        当前状态是否仍在最低播放期内。
        PetController._tick() 据此决定是否跳过宏观状态切换。
        """
        return self._min_loops_remaining > 0

    def on_loop_completed(self) -> bool:
        """
        每次动画帧索引归零（一轮播完）时由 PetWindow._tick() 调用。

        - 消耗一个最低播放计数
        - 若计数归零且当前为 one-shot 状态，执行 restore

        返回 True 表示状态已 restore，窗口需要将帧索引重置为 0。
        """
        # 消耗最低播放预算
        if self._min_loops_remaining > 0:
            self._min_loops_remaining -= 1

        # one-shot 状态在预算耗尽后 restore
        if self._sm.is_temporary and self._sm.state in ONE_SHOT_STATES:
            if self._min_loops_remaining == 0:
                self._sm.restore()
                return True  # 告知窗口重置帧索引

        return False

    # ── 点击 ──────────────────────────────────────────────────────────────────

    def on_click(self, local_y: int, window_height: int) -> None:
        """
        处理一次左键单击（已排除拖拽情况）。

        区域划分（从上到下）：
          up   0–44%   触发 poke/up（满足条件时触发 poke/up_double）
          mid  44–74%  触发 poke/mid
          down 74–100% 触发 poke/down

        up_double 触发条件：
          上次点击也在 up 区域 且 距今 < POKE_UP_FOLLOWUP_MS 且 up_double 素材存在。
          触发后重置追踪，避免三连击持续链接。

        up_double 可以打断当前正在播放的 poke（无需等动画结束）；
        普通单击不打断临时状态。
        """
        # 从睡眠中唤醒，不触发 poke
        if self._sm.state == State.SLEEP:
            self._sm.transition_to(State.IDLE)
            self._notify()
            return

        # 根据点击纵坐标确定区域
        if local_y < window_height * 44 // 100:
            zone = "up"
        elif local_y < window_height * 74 // 100:
            zone = "mid"
        else:
            zone = "down"

        # 判断是否满足 up_double 条件
        now = time.monotonic()
        is_followup = (
            zone == "up"
            and self._last_click_zone == "up"
            and (now - self._last_click_time) * 1000 < POKE_UP_FOLLOWUP_MS
            and self._animator.has_animation("poke/up_double")
        )

        # 更新追踪状态（followup 后清空，防止三连击再次触发）
        self._last_click_time = now
        self._last_click_zone = None if is_followup else zone

        # followup 可打断当前 poke；普通单击仅在非临时状态下触发
        if not is_followup and self._sm.is_temporary:
            return

        return_to = self._sm.return_state if self._sm.is_temporary else self._sm.state
        self._animator.set_poke_zone("up_double" if is_followup else zone)
        if self._animator.has_poke_animation():
            self._sm.transition_to(State.POKE, temporary=True, return_to=return_to)
        self._notify()

    # ── 拖拽 ──────────────────────────────────────────────────────────────────

    def on_drag_start(self) -> None:
        """
        鼠标移动超过死区（3px）时由 PetWindow 调用，标志着拖拽手势正式开始。
        切换到 DRAG 状态，重置所有拖拽追踪，启动长时间拖拽计时器。
        """
        # 当前已在临时状态（poke / jump 等），不触发拖拽
        if self._sm.is_temporary or not self._animator.has_animation(State.DRAG):
            return

        self._drag_is_long = False
        self._drag_is_fast = False
        self._drag_vel_samples.clear()

        self._sm.transition_to(State.DRAG, temporary=True, return_to=self._sm.state)
        self._notify()
        self._long_drag_timer.start(LONG_DRAG_DELAY_MS)

    def on_drag_velocity(self, global_pos: QPoint) -> None:
        """
        鼠标在拖拽中移动时持续调用，维护速度滑动窗口。
        当速度跨越阈值时在 fast/slow drag 动画之间切换。
        """
        now = time.monotonic()
        self._drag_vel_samples.append((now, global_pos))

        # 丢弃窗口外的旧样本
        cutoff = now - DRAG_VEL_WINDOW_S
        while self._drag_vel_samples and self._drag_vel_samples[0][0] < cutoff:
            self._drag_vel_samples.popleft()

        if len(self._drag_vel_samples) < 2:
            return

        t0, p0 = self._drag_vel_samples[0]
        t1, p1 = self._drag_vel_samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return

        dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
        speed = (dx * dx + dy * dy) ** 0.5 / dt

        new_fast = speed >= DRAG_FAST_THRESHOLD_PX_S
        if new_fast != self._drag_is_fast:
            self._drag_is_fast = new_fast
            self._apply_drag_state()

    def on_drag_end(self) -> None:
        """鼠标松开，结束拖拽，恢复拖拽前的状态。"""
        self._long_drag_timer.stop()
        self._drag_vel_samples.clear()
        if self._sm.state in (State.DRAG, State.DRAG_FAST, State.DRAG_LONG):
            self._sm.restore()
            self._notify()

    # -------------------------------------------------------------------------
    # 内部拖拽辅助
    # -------------------------------------------------------------------------

    def _on_long_drag_timer(self) -> None:
        """
        LONG_DRAG_DELAY_MS 后触发。若用户仍在拖拽，切换到长时间拖拽动画。
        （注意：此时可能是 DRAG 或 DRAG_FAST，都属于正常拖拽阶段。）
        """
        if self._sm.state not in (State.DRAG, State.DRAG_FAST):
            return  # 计时器触发前用户已经松手
        self._drag_is_long = True
        self._apply_drag_state()

    def _drag_target_state(self) -> State:
        """
        根据当前拖拽阶段（普通/长时）和速度（fast/slow）选出最合适的状态。

        降级规则：
          长时 fast  → DRAG_LONG → DRAG_FAST → DRAG
          长时 slow  → DRAG_LONG → DRAG
          普通 fast  → DRAG_FAST → DRAG
          普通 slow  → DRAG
        """
        if self._drag_is_long:
            candidates = (
                [State.DRAG_LONG, State.DRAG_FAST, State.DRAG]
                if self._drag_is_fast
                else [State.DRAG_LONG, State.DRAG]
            )
        else:
            candidates = (
                [State.DRAG_FAST, State.DRAG]
                if self._drag_is_fast
                else [State.DRAG]
            )
        for state in candidates:
            if self._animator.has_animation(state):
                return state
        return State.DRAG

    def _apply_drag_state(self) -> None:
        """切换到目标拖拽状态，保留拖拽开始前的 return_state 不变。"""
        target = self._drag_target_state()
        if self._sm.state == target:
            return
        return_to = self._sm.return_state
        self._sm.transition_to(target, temporary=True, return_to=return_to)
        self._notify()
