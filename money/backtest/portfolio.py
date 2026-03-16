# !/usr/bin/env python
# coding: utf-8
"""
模拟持仓与资金管理（期货合约撮合）

盈亏模型（期货逐笔结算）：
  - 开仓：只扣手续费，不扣保证金（简化模型）
  - 平仓：结算 (exit_price - entry_price) * size，扣手续费
  - 支持加减仓（size 为增量）
  - equity = capital + 未平仓浮动盈亏
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    """余额不足，无法支付开仓手续费，回测终止"""


class Trade:
    """单笔已平仓交易记录"""
    def __init__(self, entry_time, exit_time, direction, size,
                 entry_price, exit_price, fee, reason_open, reason_close):
        self.entry_time   = entry_time
        self.exit_time    = exit_time
        self.direction    = direction       # 'long' | 'short'
        self.size         = size            # 合约数量（正整数）
        self.entry_price  = entry_price
        self.exit_price   = exit_price
        self.fee          = fee
        self.reason_open  = reason_open
        self.reason_close = reason_close

    @property
    def pnl(self):
        if self.direction == 'long':
            return self.size * (self.exit_price - self.entry_price) - self.fee
        else:
            return self.size * (self.entry_price - self.exit_price) - self.fee

    @property
    def pnl_pct(self):
        notional = self.size * self.entry_price
        return self.pnl / notional if notional > 0 else 0


class Portfolio:
    def __init__(self, initial_capital: float, fee_rate: float = 0.0005):
        self.initial_capital = initial_capital
        self.capital         = initial_capital   # 已实现资金（含历次结算盈亏）
        self.fee_rate        = fee_rate

        self.position        = 0      # 当前净持仓（正=多 负=空）
        self.entry_price     = 0.0    # 当前持仓均价
        self.entry_time      = None
        self.entry_reason    = ""

        self.closed_trades: list[Trade] = []   # 已平仓交易记录
        self.equity_curve:  list[dict]  = []   # 每根K线净值快照

    # ------------------------------------------------------------------
    # 核心：处理信号
    # ------------------------------------------------------------------
    def execute(self, signal, bar):
        """
        按信号执行开/平/反向操作，并记录本 bar 净值快照。
        :param signal: Signal 对象
        :param bar:    当前 K 线（pd.Series，index 为时间戳）
        """
        price  = float(bar["close"])
        size   = signal.size           # 增量：正数增多/减空，负数增空/减多
        ts     = bar.name

        if size == 0:
            self._snapshot(price, ts)
            return

        # ── 有反向平仓的情况 ──────────────────────────────────────────
        if self.position != 0 and self._is_reducing(size):
            close_size = min(abs(size), abs(self.position))
            self._close(close_size, price, ts, signal.reason)
            remaining = abs(size) - close_size
            if remaining > 0:
                # 反向开仓
                new_size = remaining * (1 if size > 0 else -1)
                self._open(new_size, price, ts, signal.reason)
        elif self.position == 0:
            self._open(size, price, ts, signal.reason)
        else:
            # 同向加仓：重新计算均价
            self._add(size, price)

        self._snapshot(price, ts)

    def _is_reducing(self, size: int) -> bool:
        """size 方向与持仓相反 = 减仓/平仓"""
        return (self.position > 0 and size < 0) or \
               (self.position < 0 and size > 0)

    def _open(self, size: int, price: float, ts, reason: str):
        """开仓"""
        fee = abs(size) * price * self.fee_rate
        if self.capital < fee:
            logger.warning(
                "[OPEN 失败] %s  余额不足: capital=%.4f < fee=%.4f  "
                "方向=%s size=%+d price=%.4f  回测终止",
                ts, self.capital, fee,
                'long' if size > 0 else 'short', size, price
            )
            raise InsufficientBalanceError(
                f"余额不足: capital={self.capital:.4f} < fee={fee:.4f}，"
                f"无法在 {ts} 开仓 {size} 手 @ {price:.4f}"
            )
        self.capital    -= fee
        self.position    = size
        self.entry_price = price
        self.entry_time  = ts
        self.entry_reason = reason
        logger.info("[OPEN ] %s  方向=%-5s  size=%+d  开仓价=%.4f  手续费=%.4f  原因=%s",
                    ts, 'long' if size > 0 else 'short', size, price, fee, reason)

    def _add(self, size: int, price: float):
        """加仓：更新均价"""
        fee = abs(size) * price * self.fee_rate
        self.capital -= fee
        total_size   = self.position + size
        new_avg = (self.entry_price * abs(self.position) +
                   price * abs(size)) / abs(total_size)
        logger.info("[ADD  ] 方向=%-5s  size=%+d  加仓价=%.4f  新均价=%.4f  总持仓=%d",
                    'long' if self.position > 0 else 'short',
                    size, price, new_avg, total_size)
        self.entry_price = new_avg
        self.position = total_size

    def _close(self, close_size: int, price: float, ts, reason: str):
        """平仓 close_size 手"""
        fee = close_size * price * self.fee_rate
        direction = 'long' if self.position > 0 else 'short'

        if direction == 'long':
            realized = close_size * (price - self.entry_price)
        else:
            realized = close_size * (self.entry_price - price)

        self.capital   += realized - fee
        self.position  -= close_size if direction == 'long' else -close_size

        trade = Trade(
            entry_time   = self.entry_time,
            exit_time    = ts,
            direction    = direction,
            size         = close_size,
            entry_price  = self.entry_price,
            exit_price   = price,
            fee          = fee,
            reason_open  = self.entry_reason,
            reason_close = reason,
        )
        self.closed_trades.append(trade)
        logger.info("[CLOSE] %s  方向=%-5s  size=%d  平仓价=%.4f  pnl=%+.4f  手续费=%.4f  原因=%s",
                    ts, direction, close_size, price, trade.pnl, fee, reason)

    def _snapshot(self, price: float, ts):
        """记录当前净值"""
        unrealized = 0.0
        if self.position != 0:
            if self.position > 0:
                unrealized = self.position * (price - self.entry_price)
            else:
                unrealized = abs(self.position) * (self.entry_price - price)
        equity = self.capital + unrealized
        self.equity_curve.append({"time": ts, "equity": equity})

    # ------------------------------------------------------------------
    # 统计属性
    # ------------------------------------------------------------------
    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1]["equity"] if self.equity_curve else self.capital

    @property
    def trades(self) -> list[Trade]:
        return self.closed_trades

    def equity_series(self) -> pd.Series:
        if not self.equity_curve:
            return pd.Series(dtype="float64", name="equity")
        df = pd.DataFrame(self.equity_curve)
        if "time" not in df.columns:
            return pd.Series(dtype="float64", name="equity")
        return df.set_index("time")["equity"]

    def positions_df(self) -> pd.DataFrame:
        """
        返回所有已平仓交易的结构化 DataFrame，方便分析历史仓位。

        列说明：
          entry_time   开仓时间
          exit_time    平仓时间
          holding_h    持仓时长（小时）
          direction    方向（long / short）
          size         合约手数
          entry_price  开仓均价
          exit_price   平仓价格
          pnl          盈亏（USDT，含手续费）
          pnl_pct      盈亏率（相对名义价值）
          fee          本笔手续费（USDT）
          reason_open  开仓原因
          reason_close 平仓原因
        """
        if not self.closed_trades:
            return pd.DataFrame(columns=[
                "entry_time", "exit_time", "holding_h", "direction",
                "size", "entry_price", "exit_price",
                "pnl", "pnl_pct", "fee", "reason_open", "reason_close",
            ])

        rows = []
        for t in self.closed_trades:
            try:
                holding_h = round(
                    (t.exit_time - t.entry_time).total_seconds() / 3600, 2
                )
            except Exception:
                holding_h = None
            rows.append({
                "entry_time":   t.entry_time,
                "exit_time":    t.exit_time,
                "holding_h":    holding_h,
                "direction":    t.direction,
                "size":         t.size,
                "entry_price":  round(t.entry_price, 4),
                "exit_price":   round(t.exit_price, 4),
                "pnl":          round(t.pnl, 4),
                "pnl_pct":      round(t.pnl_pct * 100, 4),  # 转为百分比数值
                "fee":          round(t.fee, 4),
                "reason_open":  t.reason_open,
                "reason_close": t.reason_close,
            })
        return pd.DataFrame(rows)
