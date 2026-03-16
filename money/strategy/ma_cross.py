# !/usr/bin/env python
# coding: utf-8
"""
均线交叉策略（示例）

逻辑：
  - 快线上穿慢线（金叉）→ 平空 + 开多
  - 快线下穿慢线（死叉）→ 平多 + 开空
  - 可通过 params 禁止做空（only_long=True）
"""
import logging
from strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class MACrossStrategy(BaseStrategy):
    def __init__(self, contract: str, fast: int = 5, slow: int = 20,
                 order_size: int = 1, only_long: bool = False):
        """
        :param contract:   合约名称
        :param fast:       快线周期
        :param slow:       慢线周期
        :param order_size: 每次开仓手数
        :param only_long:  True = 只做多，不做空
        """
        super().__init__(contract, {
            "fast": fast, "slow": slow,
            "order_size": order_size, "only_long": only_long,
        })
        self.fast       = fast
        self.slow       = slow
        self.order_size = order_size
        self.only_long  = only_long

    def on_bar(self, bar, history) -> Signal | None:
        fast_col = f"ma{self.fast}"
        slow_col = f"ma{self.slow}"

        # 指标列不存在（数据太少）
        if fast_col not in history.columns or slow_col not in history.columns:
            return None
        if len(history) < self.slow + 2:
            return None

        prev = history.iloc[-2]
        curr = history.iloc[-1]

        prev_fast, prev_slow = prev[fast_col], prev[slow_col]
        curr_fast, curr_slow = curr[fast_col], curr[slow_col]

        # 任一指标为 NaN 则跳过
        import math
        if any(math.isnan(v) for v in [prev_fast, prev_slow, curr_fast, curr_slow]):
            return None

        # self.position: 0=空仓 1=持多 -1=持空
        # 发出的 size = 目标净仓 - 当前净仓（增量）
        #   从空到多: delta = +order_size - (-order_size) = +2*order_size（平空+开多）
        #   从无到多: delta = +order_size - 0 = +order_size（直接开多）
        #   从多到空: delta = -order_size - (+order_size) = -2*order_size（平多+开空）
        #   从无到空: delta = -order_size - 0 = -order_size（直接开空）
        #   从多到平: delta = 0 - order_size = -order_size（平多）

        # ── 金叉：fast 上穿 slow → 目标持多 ──────────────────────────
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            if self.position != 1:
                logger.info("金叉 @ %.2f  fast=%.2f slow=%.2f",
                            curr["close"], curr_fast, curr_slow)
                # 当前净仓（按 order_size 计）
                current_net = self.position * self.order_size  # 0 or -order_size
                target_net  = self.order_size
                delta = target_net - current_net
                self.position = 1
                return Signal(
                    action="buy", contract=self.contract,
                    size=delta, reason="golden_cross",
                )

        # ── 死叉：fast 下穿 slow ──────────────────────────────────────
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            if self.only_long:
                # 只做多：死叉时平多变空仓（目标 = 0）
                if self.position == 1:
                    logger.info("死叉(只多) @ %.2f  fast=%.2f slow=%.2f",
                                curr["close"], curr_fast, curr_slow)
                    delta = -self.order_size   # 0 - order_size
                    self.position = 0
                    return Signal(
                        action="sell", contract=self.contract,
                        size=delta, reason="death_cross_close",
                    )
            else:
                # 双向：死叉时目标持空
                if self.position != -1:
                    logger.info("死叉 @ %.2f  fast=%.2f slow=%.2f",
                                curr["close"], curr_fast, curr_slow)
                    current_net = self.position * self.order_size  # 0 or +order_size
                    target_net  = -self.order_size
                    delta = target_net - current_net
                    self.position = -1
                    return Signal(
                        action="sell", contract=self.contract,
                        size=delta, reason="death_cross",
                    )

        return None

    def on_stop(self):
        """回测结束：重置持仓状态"""
        self.position = 0

