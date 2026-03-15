# !/usr/bin/env python
# coding: utf-8
"""
模拟持仓与资金管理
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Portfolio:
    def __init__(self, initial_capital, fee_rate=0.0005):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.fee_rate = fee_rate
        self.position = 0       # 当前持仓量（正多负空）
        self.avg_price = 0.0    # 持仓均价
        self.trades = []        # 成交记录
        self.equity_curve = []  # 净值曲线

    def execute(self, signal, bar):
        price = bar["close"]
        size = signal.size
        fee = abs(size) * price * self.fee_rate

        if signal.action in ("buy", "sell"):
            cost = size * price + fee
            self.capital -= cost
            self.position += size
            self.avg_price = price
            self.trades.append({
                "time": bar.name,
                "action": signal.action,
                "size": size,
                "price": price,
                "fee": fee,
                "reason": signal.reason,
            })
            logger.debug("%s %s size=%d price=%.2f fee=%.4f",
                         bar.name, signal.action, size, price, fee)

        equity = self.capital + self.position * price
        self.equity_curve.append({"time": bar.name, "equity": equity})

    @property
    def final_equity(self):
        if self.equity_curve:
            return self.equity_curve[-1]["equity"]
        return self.capital
