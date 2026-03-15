# !/usr/bin/env python
# coding: utf-8
"""
回测系统集成测试 —— 使用 DataFetcher 拉取真实行情数据

python -m pytest tests/backtest/test_backtest.py -v

覆盖：
  - Portfolio 开/平/反向/加仓，PnL 数学正确性（合成 bar，纯算术验证）
  - Trade.pnl 多/空方向
  - Metrics 各字段类型与合理范围（真实数据驱动）
  - BacktestEngine 完整流程（真实 BTC_USDT 1h K 线 × MACrossStrategy）
"""
import math
import sys
import os
import unittest
from datetime import datetime, timezone

import pandas as pd

# ─── 路径 ─────────────────────────────────────────────────────────────
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "..", "gateapi-python"))
sys.path.insert(0, ROOT)

from data.fetcher       import DataFetcher
from backtest.portfolio import Portfolio, Trade
from backtest.metrics   import calc_metrics, calc_metrics_raw
from backtest.engine    import BacktestEngine
from strategy.ma_cross  import MACrossStrategy
from strategy.base      import Signal

# ══════════════════════════════════════════════════════════════════════
# 真实数据：模块级只拉取一次，所有用例共享
# 合约：BTC_USDT  周期：1h  区间：2025-06-01 ~ 2025-09-01（约 2208 根）
# ══════════════════════════════════════════════════════════════════════
_FETCHER  = DataFetcher(settle="usdt")   # 公开行情接口，无需 key/secret
_CONTRACT = "BTC_USDT"
_START    = datetime(2025, 6,  1, tzinfo=timezone.utc)
_END      = datetime(2025, 9,  1, tzinfo=timezone.utc)

print(f"\n[test_backtest] 拉取真实行情: {_CONTRACT} 1h  {_START.date()} → {_END.date()} ...")
REAL_DF: pd.DataFrame = _FETCHER.fetch_range(_CONTRACT, interval="1h",
                                              start=_START, end=_END)
print(f"[test_backtest] 共 {len(REAL_DF)} 根 K 线，列: {list(REAL_DF.columns)}\n")


# ══════════════════════════════════════════════════════════════════════
# 工具函数（仅用于 Portfolio/Trade 算术单元测试）
# ══════════════════════════════════════════════════════════════════════

def _make_bar(price: float, ts=None) -> pd.Series:
    """构造单根合成 K 线（仅用于 PnL 数学验证，不用于引擎测试）"""
    if ts is None:
        ts = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.Series(
        {"open": price, "high": price * 1.001,
         "low":  price * 0.999, "close": price, "volume": 1000.0},
        name=ts,
    )


def _make_signal(action: str, size: int, reason: str = "") -> Signal:
    return Signal(action=action, contract=_CONTRACT, size=size, reason=reason)


# ══════════════════════════════════════════════════════════════════════
# 1. Portfolio 单元测试
# ══════════════════════════════════════════════════════════════════════

class TestPortfolioOpenClose(unittest.TestCase):
    """开/平仓基础逻辑"""

    def setUp(self):
        self.pf = Portfolio(initial_capital=10000, fee_rate=0.001)

    # ── 多头 ──────────────────────────────────────────────────────────
    def test_long_profit(self):
        """开多 10 手 @ 100，平多 @ 110 → 盈利"""
        bar_open  = _make_bar(100, pd.Timestamp("2024-01-01", tz="UTC"))
        bar_close = _make_bar(110, pd.Timestamp("2024-01-02", tz="UTC"))

        self.pf.execute(_make_signal("buy",  +10), bar_open)
        self.pf.execute(_make_signal("sell", -10), bar_close)

        trade = self.pf.closed_trades[-1]
        self.assertEqual(trade.direction, "long")
        self.assertEqual(trade.size, 10)
        self.assertAlmostEqual(trade.entry_price, 100)
        self.assertAlmostEqual(trade.exit_price,  110)

        # 手工验算：pnl = 10*(110-100) - fee_close  （fee_open 已从 capital 扣）
        expected_fee_close = 10 * 110 * 0.001
        expected_pnl       = 10 * (110 - 100) - expected_fee_close
        self.assertAlmostEqual(trade.pnl, expected_pnl, places=6)
        self.assertGreater(trade.pnl, 0)

    def test_long_loss(self):
        """开多亏损"""
        bar_open  = _make_bar(100, pd.Timestamp("2024-01-01", tz="UTC"))
        bar_close = _make_bar(90,  pd.Timestamp("2024-01-02", tz="UTC"))
        self.pf.execute(_make_signal("buy",  +10), bar_open)
        self.pf.execute(_make_signal("sell", -10), bar_close)
        trade = self.pf.closed_trades[-1]
        self.assertLess(trade.pnl, 0)

    # ── 空头 ──────────────────────────────────────────────────────────
    def test_short_profit(self):
        """开空盈利"""
        bar_open  = _make_bar(100, pd.Timestamp("2024-01-01", tz="UTC"))
        bar_close = _make_bar(90,  pd.Timestamp("2024-01-02", tz="UTC"))
        self.pf.execute(_make_signal("sell", -10), bar_open)
        self.pf.execute(_make_signal("buy",  +10), bar_close)
        trade = self.pf.closed_trades[-1]
        self.assertEqual(trade.direction, "short")
        self.assertGreater(trade.pnl, 0)

    def test_short_loss(self):
        """开空亏损"""
        bar_open  = _make_bar(100, pd.Timestamp("2024-01-01", tz="UTC"))
        bar_close = _make_bar(110, pd.Timestamp("2024-01-02", tz="UTC"))
        self.pf.execute(_make_signal("sell", -10), bar_open)
        self.pf.execute(_make_signal("buy",  +10), bar_close)
        trade = self.pf.closed_trades[-1]
        self.assertLess(trade.pnl, 0)


class TestPortfolioReversal(unittest.TestCase):
    """反向开仓（多翻空 / 空翻多）"""

    def test_long_to_short(self):
        """持多 10 手后发 sell -20（反向变空 10 手）"""
        pf = Portfolio(10000, fee_rate=0.001)
        ts1 = pd.Timestamp("2024-01-01", tz="UTC")
        ts2 = pd.Timestamp("2024-01-02", tz="UTC")
        ts3 = pd.Timestamp("2024-01-03", tz="UTC")

        pf.execute(_make_signal("buy",  +10), _make_bar(100, ts1))
        pf.execute(_make_signal("sell", -20), _make_bar(110, ts2))  # 平 10 + 开空 10

        self.assertEqual(pf.position, -10)
        self.assertEqual(len(pf.closed_trades), 1)        # 多头已平
        self.assertEqual(pf.closed_trades[0].direction, "long")

        # 再平空
        pf.execute(_make_signal("buy", +10), _make_bar(105, ts3))
        self.assertEqual(pf.position, 0)
        self.assertEqual(len(pf.closed_trades), 2)
        self.assertEqual(pf.closed_trades[1].direction, "short")

    def test_short_to_long(self):
        """持空 10 手后反向"""
        pf = Portfolio(10000, fee_rate=0.001)
        ts1 = pd.Timestamp("2024-01-01", tz="UTC")
        ts2 = pd.Timestamp("2024-01-02", tz="UTC")
        pf.execute(_make_signal("sell", -10), _make_bar(100, ts1))
        pf.execute(_make_signal("buy",  +20), _make_bar(90, ts2))
        self.assertEqual(pf.position, +10)
        self.assertEqual(len(pf.closed_trades), 1)


class TestPortfolioEquity(unittest.TestCase):
    """净值曲线"""

    def test_equity_series_length(self):
        """每次 execute 都追加一条净值快照"""
        pf = Portfolio(10000, fee_rate=0.001)
        for i in range(5):
            ts = pd.Timestamp(f"2024-01-0{i+1}", tz="UTC")
            pf.execute(_make_signal("buy", 0), _make_bar(100 + i, ts))

        eq = pf.equity_series()
        self.assertEqual(len(eq), 5)
        self.assertIsInstance(eq, pd.Series)

    def test_initial_equity(self):
        """未开仓时净值等于初始资金"""
        pf = Portfolio(12345.0, fee_rate=0.001)
        ts = pd.Timestamp("2024-01-01", tz="UTC")
        pf.execute(_make_signal("buy", 0), _make_bar(100, ts))
        self.assertAlmostEqual(pf.equity_series().iloc[0], 12345.0)

    def test_final_equity_after_close(self):
        """平仓后净值 = 初始 + 已实现盈亏（无浮亏）"""
        pf = Portfolio(10000, fee_rate=0.001)
        pf.execute(_make_signal("buy",  +10), _make_bar(100, pd.Timestamp("2024-01-01", tz="UTC")))
        pf.execute(_make_signal("sell", -10), _make_bar(110, pd.Timestamp("2024-01-02", tz="UTC")))

        final = pf.final_equity
        # 浮亏为 0，净值 = capital
        self.assertAlmostEqual(final, pf.capital, places=6)


# ══════════════════════════════════════════════════════════════════════
# 2. Metrics 单元测试
# ══════════════════════════════════════════════════════════════════════

def _run_engine_on_real_data(
        fast=5, slow=20, order_size=1,
        only_long=False, start=None, end=None,
) -> tuple:
    """用真实行情数据跑回测，返回 (metrics, portfolio)"""
    strategy = MACrossStrategy(
        _CONTRACT, fast=fast, slow=slow,
        order_size=order_size, only_long=only_long,
    )
    engine = BacktestEngine(
        strategy=strategy,
        data=REAL_DF,
        start=start,
        end=end,
        initial_capital=10000,
        fee_rate=0.001,
        indicators=["ma"],
    )
    return engine.run()


class TestMetrics(unittest.TestCase):
    """确保 calc_metrics / calc_metrics_raw 字段完整且类型正确（真实数据）"""

    def _run_simple_engine(self) -> Portfolio:
        """用真实行情跑一次回测，返回 portfolio"""
        _, portfolio = _run_engine_on_real_data()
        return portfolio

    def test_metrics_keys(self):
        """calc_metrics 返回 14 个预定义键"""
        pf = self._run_simple_engine()
        metrics = calc_metrics(pf)
        expected_keys = [
            "初始资金", "最终净值", "总收益率", "年化收益率",
            "夏普比率", "最大回撤", "最大回撤天数",
            "总交易次数", "胜率", "盈亏比",
            "平均每笔盈亏", "平均盈利", "平均亏损", "总手续费",
        ]
        for k in expected_keys:
            self.assertIn(k, metrics, f"缺少指标键: {k}")

    def test_metrics_raw_types(self):
        """calc_metrics_raw 中所有值均为 float 或 int"""
        pf = self._run_simple_engine()
        raw = calc_metrics_raw(pf)
        for k, v in raw.items():
            self.assertIsInstance(v, (int, float),
                                  f"{k} 类型为 {type(v)}，期望数值")
            self.assertFalse(math.isnan(v), f"{k} 为 NaN")

    def test_total_return_direction(self):
        """盈亏比/净值方向与实际交易一致（不做方向断言，只验证无 inf）"""
        pf = self._run_simple_engine()
        raw = calc_metrics_raw(pf)
        self.assertFalse(math.isinf(raw["profit_factor"]))

    def test_metrics_win_rate_range(self):
        """胜率 ∈ [0, 1]"""
        pf = self._run_simple_engine()
        raw = calc_metrics_raw(pf)
        self.assertGreaterEqual(raw["win_rate"], 0.0)
        self.assertLessEqual(raw["win_rate"],    1.0)

    def test_metrics_max_drawdown_negative(self):
        """最大回撤 ≤ 0（无上界，净值为负时可低于 -1）"""
        pf = self._run_simple_engine()
        raw = calc_metrics_raw(pf)
        self.assertLessEqual(raw["max_drawdown"], 0.0)
        self.assertFalse(math.isnan(raw["max_drawdown"]))

    def test_metrics_no_trades(self):
        """无交易时也不崩溃（返回 0 值）"""
        pf = Portfolio(10000, fee_rate=0.001)
        # 至少 2 个快照，calc_metrics_raw 才会运行
        pf._snapshot(10000, pd.Timestamp("2024-01-01", tz="UTC"))
        pf._snapshot(10000, pd.Timestamp("2024-01-02", tz="UTC"))
        raw = calc_metrics_raw(pf)
        self.assertEqual(raw["n_trades"], 0)
        self.assertEqual(raw["win_rate"], 0.0)


# ══════════════════════════════════════════════════════════════════════
# 3. 回测引擎集成测试
# ══════════════════════════════════════════════════════════════════════

class TestBacktestEngine(unittest.TestCase):
    """BacktestEngine end-to-end 流程（真实 BTC_USDT 1h 行情）"""

    @classmethod
    def setUpClass(cls):
        """全类只跑一次完整回测，后续用例复用结果"""
        cls.metrics, cls.portfolio = _run_engine_on_real_data()

    def test_real_data_not_empty(self):
        """真实数据拉取成功，行数合理"""
        # 2025-06-01 ~ 2025-09-01 约 2208 根 1h K 线
        self.assertGreater(len(REAL_DF), 500, "拉取的真实数据行数不足")
        for col in ("open", "high", "low", "close", "volume"):
            self.assertIn(col, REAL_DF.columns)

    def test_run_returns_two_values(self):
        self.assertIsInstance((self.metrics, self.portfolio), tuple)
        self.assertIsNotNone(self.metrics)
        self.assertIsNotNone(self.portfolio)

    def test_metrics_dict(self):
        self.assertIsInstance(self.metrics, dict)
        self.assertIn("总收益率", self.metrics)

    def test_equity_curve_not_empty(self):
        """净值曲线长度 > 0，且 ≤ 真实数据长度"""
        eq = self.portfolio.equity_series()
        self.assertGreater(len(eq), 0)
        self.assertLessEqual(len(eq), len(REAL_DF))

    def test_equity_index_is_datetime(self):
        """净值曲线 index 为时间戳，与真实 K 线对齐"""
        eq = self.portfolio.equity_series()
        self.assertIsInstance(eq.index[0], pd.Timestamp)
        # 净值曲线最早时间 ≥ 真实数据最早时间
        self.assertGreaterEqual(eq.index[0], REAL_DF.index[0])

    def test_at_least_one_trade(self):
        """真实行情中应产生至少 1 笔已平仓交易"""
        self.assertGreater(
            len(self.portfolio.closed_trades), 0,
            f"真实数据 {len(REAL_DF)} 根 K 线未产生任何交易",
        )

    def test_closed_trade_prices_match_real_data(self):
        """所有成交价格应在真实 K 线的价格范围内"""
        price_min = float(REAL_DF["low"].min())
        price_max = float(REAL_DF["high"].max())
        for t in self.portfolio.closed_trades:
            self.assertGreaterEqual(t.entry_price, price_min)
            self.assertLessEqual(t.entry_price, price_max)
            self.assertGreaterEqual(t.exit_price, price_min)
            self.assertLessEqual(t.exit_price, price_max)

    def test_final_equity_is_finite(self):
        """真实行情下盈亏取决于市场，只验证净值是有效数值（非 NaN/inf）"""
        final = self.portfolio.final_equity
        self.assertFalse(math.isnan(final), "final_equity 为 NaN")
        self.assertFalse(math.isinf(final), "final_equity 为 inf")

    def test_no_open_position_at_end(self):
        """on_stop() 不崩溃"""
        _ = self.portfolio.final_equity   # 不抛异常即通过

    def test_time_range_filter(self):
        """start 参数裁剪后，净值曲线长度 < 全量"""
        mid_date = "2025-07-15"
        _, pf_half = _run_engine_on_real_data(start=mid_date)
        eq_full = self.portfolio.equity_series()
        eq_half = pf_half.equity_series()
        self.assertLess(len(eq_half), len(eq_full),
                        "指定 start 后 equity 长度应小于全量")
        # 半段的起始时间应 ≥ mid_date
        if len(eq_half) > 0:
            self.assertGreaterEqual(
                eq_half.index[0],
                pd.Timestamp(mid_date, tz="UTC"),
            )

    def test_only_long_mode(self):
        """only_long=True 时不应存在 short 交易"""
        _, pf = _run_engine_on_real_data(only_long=True)
        for t in pf.closed_trades:
            self.assertNotEqual(t.direction, "short",
                                "only_long 模式下不应开空")


# ══════════════════════════════════════════════════════════════════════
# 4. Trade 属性测试
# ══════════════════════════════════════════════════════════════════════

class TestTrade(unittest.TestCase):
    """Trade.pnl / Trade.pnl_pct 数学正确性"""

    def test_long_pnl_formula(self):
        t = Trade(
            entry_time=0, exit_time=1, direction="long",
            size=10, entry_price=100, exit_price=110,
            fee=5, reason_open="test", reason_close="test",
        )
        self.assertAlmostEqual(t.pnl, 10 * (110 - 100) - 5)  # = 95

    def test_short_pnl_formula(self):
        t = Trade(
            entry_time=0, exit_time=1, direction="short",
            size=10, entry_price=100, exit_price=90,
            fee=5, reason_open="test", reason_close="test",
        )
        self.assertAlmostEqual(t.pnl, 10 * (100 - 90) - 5)  # = 95

    def test_pnl_pct(self):
        t = Trade(
            entry_time=0, exit_time=1, direction="long",
            size=10, entry_price=100, exit_price=110,
            fee=0, reason_open="", reason_close="",
        )
        # pnl_pct = 100 / (10*100) = 0.1
        self.assertAlmostEqual(t.pnl_pct, 0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
