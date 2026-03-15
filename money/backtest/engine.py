# !/usr/bin/env python
# coding: utf-8
"""
回测引擎
基于历史K线逐根驱动策略，模拟撮合，记录交易历史

快速上手：
    # 1. 准备数据
    from data.fetcher import DataFetcher
    fetcher = DataFetcher(settle="usdt")
    df = fetcher.fetch_range("BTC_USDT", interval="1h",
                             start=datetime(2025,6,1,tzinfo=timezone.utc),
                             end=datetime(2025,9,1,tzinfo=timezone.utc))

    # 2. 选择策略
    from strategy.ma_cross import MACrossStrategy
    strategy = MACrossStrategy("BTC_USDT", fast=5, slow=20, order_size=1)

    # 3. 初始化引擎（可指定回测时间段）
    engine = BacktestEngine(
        strategy        = strategy,
        data            = df,
        start           = '2025-06-01',   # 可选，不填则使用全部数据
        end             = '2025-09-01',   # 可选
        initial_capital = 10000,
        fee_rate        = 0.001,
    )

    # 4a. 运行并获取结果
    metrics, portfolio = engine.run()
    print(metrics)                  # 胜率/盈亏比/回报率等
    positions = portfolio.positions_df()  # 全部历史仓位 DataFrame
    print(positions)

    # 4b. 打印完整报告（指标 + 净值图 + 仓位表）
    engine.report()
"""
import logging
from datetime import datetime
from typing import Optional, Union

import pandas as pd
from backtest.portfolio import Portfolio
from backtest.metrics import calc_metrics
from data.preprocessor import add_ma, add_ema, add_rsi, add_bollinger, add_macd

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        strategy,
        data: pd.DataFrame,
        start: Optional[Union[str, datetime]] = None,
        end:   Optional[Union[str, datetime]] = None,
        initial_capital: float = 10000,
        fee_rate: float = 0.0005,
        indicators: Optional[list] = None,
    ):
        """
        :param strategy:        策略实例（继承 BaseStrategy）
        :param data:            全量历史K线 DataFrame（建议传入比回测区间更早的数据，用于指标热身）
        :param start:           回测起始时间（字符串 'YYYY-MM-DD' 或 datetime，可选）
        :param end:             回测结束时间（可选）
        :param initial_capital: 初始资金（USDT）
        :param fee_rate:        每笔手续费率（如 0.0005 = 0.05%）
        :param indicators:      需预计算的指标列表，默认全量 ['ma','ema','rsi','boll','macd']
                                自定义示例：['ma', 'rsi'] 可加速预处理
        """
        self.strategy = strategy
        self.raw_data = data
        self.start = pd.Timestamp(start, tz="UTC") if start else None
        self.end   = pd.Timestamp(end,   tz="UTC") if end   else None
        self.portfolio = Portfolio(initial_capital, fee_rate)
        self.indicators = indicators or ['ma', 'ema', 'rsi', 'boll', 'macd']

    # ------------------------------------------------------------------
    # 指标预处理
    # ------------------------------------------------------------------
    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对全量数据预计算指标（保留热身窗口，避免开头 NaN 影响信号），
        再按 start/end 裁剪回测区间。
        """
        df = df.copy()
        if 'ma' in self.indicators:
            df = add_ma(df, [5, 10, 20, 60])
        if 'ema' in self.indicators:
            df = add_ema(df, [12, 26])
        if 'rsi' in self.indicators:
            df = add_rsi(df)
        if 'boll' in self.indicators:
            df = add_bollinger(df)
        if 'macd' in self.indicators:
            df = add_macd(df)

        # 策略可通过实现 on_prepare(df) 追加自定义指标列
        if hasattr(self.strategy, 'on_prepare'):
            df = self.strategy.on_prepare(df)

        # 裁剪到用户指定的区间
        if self.start:
            df = df[df.index >= self.start]
        if self.end:
            df = df[df.index <= self.end]

        if df.empty:
            logger.warning("no data in range [%s, %s]", self.start, self.end)
        else:
            logger.info("backtest range: %s → %s (%d bars)",
                        df.index[0], df.index[-1], len(df))
        return df

    # ------------------------------------------------------------------
    # 回测主流程
    # ------------------------------------------------------------------
    def run(self):
        df = self._prepare_data(self.raw_data)
        self.strategy.on_start()

        for i in range(len(df)):
            history = df.iloc[:i + 1]   # 含当前 bar 的全部历史
            bar     = df.iloc[i]
            signal  = self.strategy.on_bar(bar, history)
            if signal:
                self.portfolio.execute(signal, bar)

        self.strategy.on_stop()
        metrics = calc_metrics(self.portfolio)
        return metrics, self.portfolio

    # ------------------------------------------------------------------
    # 报告（含终端净值曲线图）
    # ------------------------------------------------------------------
    def report(self):
        metrics, portfolio = self.run()

        # ── 文字报告 ──────────────────────────────────────────────────
        print("\n" + "=" * 55)
        print(f"  回测报告  合约: {self.strategy.contract}")
        if self.start or self.end:
            print(f"  时间范围: {self.start or '最早'} → {self.end or '最新'}")
        print("=" * 55)
        for k, v in metrics.items():
            print(f"  {k:14s}: {v}")
        print("=" * 55)

        # ── 终端净值曲线图 ────────────────────────────────────────────
        equity = portfolio.equity_series()
        if len(equity) >= 2:
            try:
                import plotext as plt
                dates  = [str(ts.date()) if hasattr(ts, 'date') else str(ts)
                          for ts in equity.index]
                values = equity.tolist()

                plt.clf()
                plt.theme("dark")
                plt.plot_size(width=90, height=20)
                plt.date_form("Y-m-d")
                plt.plot(dates, values, color="cyan", label="净值")
                plt.hline(portfolio.initial_capital, color="white")
                plt.title(f"净值曲线  {dates[0]} → {dates[-1]}")
                plt.xlabel("日期")
                plt.ylabel("USDT")
                print()
                plt.show()
            except ImportError:
                pass  # plotext 未安装时跳过图表

        # ── 逐笔交易明细（全部）────────────────────────────────────
        positions = portfolio.positions_df()
        if not positions.empty:
            total = len(positions)
            print(f"\n  历史仓位记录（共 {total} 笔）:")
            # 调整显示列，宽度适应终端
            pd.set_option("display.max_rows", None)
            pd.set_option("display.float_format", "{:.4f}".format)
            pd.set_option("display.width", 130)
            display_cols = [
                "entry_time", "exit_time", "holding_h",
                "direction", "size",
                "entry_price", "exit_price",
                "pnl", "pnl_pct", "fee",
                "reason_open", "reason_close",
            ]
            print(positions[display_cols].to_string(index=True))
            pd.reset_option("display.max_rows")
            pd.reset_option("display.float_format")
            pd.reset_option("display.width")
            print()

        return metrics, portfolio
