# !/usr/bin/env python
# coding: utf-8
"""
均线交叉策略（示例）
快线上穿慢线做多，快线下穿慢线做空
"""
import logging
from strategy.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class MACrossStrategy(BaseStrategy):
    def __init__(self, contract, fast=5, slow=20, order_size=10):
        super().__init__(contract, {"fast": fast, "slow": slow})
        self.fast = fast
        self.slow = slow
        self.order_size = order_size
        self.position = 0  # 当前持仓方向：1多 -1空 0无

    def on_bar(self, bar, history):
        fast_col = f"ma{self.fast}"
        slow_col = f"ma{self.slow}"

        if fast_col not in history.columns or slow_col not in history.columns:
            return None
        if len(history) < self.slow + 1:
            return None

        prev = history.iloc[-2]
        curr = history.iloc[-1]

        # 金叉：快线上穿慢线 → 做多
        if prev[fast_col] <= prev[slow_col] and curr[fast_col] > curr[slow_col]:
            if self.position != 1:
                self.position = 1
                logger.info("golden cross → buy, price=%.2f", curr["close"])
                return Signal(action="buy", contract=self.contract,
                              size=self.order_size, reason="golden cross")

        # 死叉：快线下穿慢线 → 做空
        elif prev[fast_col] >= prev[slow_col] and curr[fast_col] < curr[slow_col]:
            if self.position != -1:
                self.position = -1
                logger.info("death cross → sell, price=%.2f", curr["close"])
                return Signal(action="sell", contract=self.contract,
                              size=-self.order_size, reason="death cross")

        return None
