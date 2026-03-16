# !/usr/bin/env python
# coding: utf-8
"""
K 线聚合工具：从母级别(1m)聚合到更高周期
"""
import pandas as pd


_INTERVAL_TO_RULE = {
    "10s": "10S",
    "1m":  "1T",
    "5m":  "5T",
    "15m": "15T",
    "30m": "30T",
    "1h":  "1H",
    "2h":  "2H",
    "4h":  "4H",
    "8h":  "8H",
    "1d":  "1D",
    "7d":  "7D",
    "30d": "30D",
}


def resample_ohlcv(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    将 OHLCV 数据按 interval 聚合。

    规则：
      - open: 首根
      - high: 最大
      - low:  最小
      - close: 末根
      - volume/amount: 求和
    """
    if df is None or df.empty:
        return pd.DataFrame()

    rule = _INTERVAL_TO_RULE.get(interval)
    if rule is None:
        raise ValueError(f"unsupported interval '{interval}'")

    data = df.copy()
    if data.index.tzinfo is None:
        data.index = pd.to_datetime(data.index, utc=True)
    data = data.sort_index()
    data = data[~data.index.duplicated(keep="last")]

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
    }
    resampled = (data.resample(rule, label="right", closed="right")
                 .agg(agg)
                 .dropna(subset=["close"]))
    return resampled
