# !/usr/bin/env python
# coding: utf-8
"""
回测引擎
基于历史K线逐根驱动策略，模拟撮合，记录交易历史

用法：
    engine = BacktestEngine(
        strategy        = MyStrategy('BTC_USDT'),
        data            = df,              # 全量历史数据
        start           = '2024-03-01',    # 指定回测开始日期（可选）
        end             = '2024-03-31',    # 指定回测结束日期（可选）
        initial_capital = 10000,
        fee_rate        = 0.0005,
    )
    metrics, portfolio = engine.run()
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
    # 报告
    # ------------------------------------------------------------------
    def report(self):
        metrics, portfolio = self.run()
        print("\n" + "=" * 50)
        print(f" 回测报告  合约: {self.strategy.contract}")
        if self.start or self.end:
            print(f" 时间范围: {self.start or '最早'} → {self.end or '最新'}")
        print("=" * 50)
        for k, v in metrics.items():
            print(f"  {k:12s}: {v}")
        print("=" * 50 + "\n")
        return metrics, portfolio
