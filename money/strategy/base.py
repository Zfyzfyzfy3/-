# !/usr/bin/env python
# coding: utf-8
"""
策略抽象基类
回测引擎和实盘引擎都通过此接口调用策略。

用户自定义策略只需继承 BaseStrategy，并实现：
  - on_bar(bar, history) → Signal | None   【必须实现】
  - on_bar_multi(bar, history, multi_history) → Signal | None
        （可选，多周期策略使用）
  - on_prepare(df)       → DataFrame        【可选：追加自定义指标列】
  - on_start()                               【可选：初始化状态】
  - on_stop()                                【可选：清仓/保存状态】

示例：
    class MyStrategy(BaseStrategy):
        def on_prepare(self, df):
            # 追加自定义指标
            df['my_signal'] = df['close'].diff()
            return df

        def on_bar(self, bar, history):
            if bar['my_signal'] > 0 and self.position == 0:
                self.position = 1
                return Signal(action='buy', contract=self.contract, size=10)
            return None
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    action:   str    # 'buy' | 'sell' | 'close_long' | 'close_short'
    contract: str    # 合约名称，如 BTC_USDT
    size:     int    # 下单量（正数做多，负数做空，0 = 平仓）
    price:    float = 0.0    # 0 表示市价
    reason:   str   = ""     # 信号原因（用于日志和统计）
    extra:    dict  = field(default_factory=dict)  # 自定义扩展字段


class BaseStrategy(ABC):
    def __init__(self, contract: str, params: Optional[dict] = None):
        """
        :param contract: 合约名称，如 'BTC_USDT'
        :param params:   策略参数字典，子类可通过 self.params['xxx'] 访问
        """
        self.contract = contract
        self.params   = params or {}
        self.position = 0   # 当前持仓方向：1=多仓 -1=空仓 0=无仓

    # ------------------------------------------------------------------
    # 【必须实现】核心信号逻辑
    # ------------------------------------------------------------------
    @abstractmethod
    def on_bar(self, bar: pd.Series, history: pd.DataFrame) -> Optional[Signal]:
        """
        每根K线到来时调用。
        :param bar:     当前K线（含 open/high/low/close/volume 及所有预计算指标列）
        :param history: 含当前 bar 在内的全部历史 DataFrame（按时间升序）
        :return:        Signal（交易信号）或 None（不操作）
        """
        pass

    # ------------------------------------------------------------------
    # 【可选】多周期信号逻辑
    # ------------------------------------------------------------------
    def on_bar_multi(
        self,
        bar: pd.Series,
        history: pd.DataFrame,
        multi_history: dict[str, pd.DataFrame],
    ) -> Optional[Signal]:
        """
        多周期回测时调用。
        :param bar: 当前K线（主周期）
        :param history: 主周期历史（含当前 bar）
        :param multi_history: 其他周期历史数据字典，例如 {"4h": df, "5m": df}
        """
        return self.on_bar(bar, history)

    # ------------------------------------------------------------------
    # 【可选钩子】自定义指标
    # ------------------------------------------------------------------
    def on_prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        回测引擎在预计算完内置指标后调用此方法，
        用于追加策略专属指标列到 DataFrame。
        默认不做任何处理，子类按需覆盖。

        :param df: 已含 ma/ema/rsi/boll/macd 等内置指标的 DataFrame
        :return:   追加了自定义列的 DataFrame
        """
        return df

    # ------------------------------------------------------------------
    # 【可选钩子】生命周期
    # ------------------------------------------------------------------
    def on_start(self):
        """引擎启动时调用，可用于初始化状态、加载模型等"""
        pass

    def on_stop(self):
        """引擎停止时调用，可用于清仓、保存状态等"""
        pass
