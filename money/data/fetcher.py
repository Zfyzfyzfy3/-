# !/usr/bin/env python
# coding: utf-8
"""
数据拉取模块
负责从 Gate.io 获取历史K线、实时行情等数据

关键约束（来自 API 文档）：
  - 每次最多返回 2000 根 K 线
  - _from / to 与 limit 不能同时传，使用时间范围时只用 _from + to
  - 超过 2000 根需要自动分页
"""
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from gate_api import ApiClient, Configuration, FuturesApi
from gate_api.exceptions import GateApiException

logger = logging.getLogger(__name__)

# 各 interval 对应的秒数，用于计算分页步长
INTERVAL_SECONDS = {
    "10s": 10,
    "1m":  60,
    "5m":  300,
    "15m": 900,
    "30m": 1800,
    "1h":  3600,
    "2h":  7200,
    "4h":  14400,
    "8h":  28800,
    "1d":  86400,
    "7d":  604800,
    "30d": 2592000,
}

MAX_POINTS_PER_REQUEST = 2000   # API 单次上限
RATE_LIMIT_SLEEP = 0.3          # 分页请求间隔（秒），避免触发限速


class DataFetcher:
    def __init__(self, api_key="", api_secret="", host="https://api.gateio.ws/api/v4",
                 settle="usdt"):
        config = Configuration(key=api_key, secret=api_secret, host=host)
        self.futures_api = FuturesApi(ApiClient(config))
        self.settle = settle

    # ------------------------------------------------------------------
    # 内部：单次请求（from → to，不超过 2000 根）
    # ------------------------------------------------------------------
    def _fetch_chunk(self, contract, interval, from_ts, to_ts):
        candles = self.futures_api.list_futures_candlesticks(
            self.settle, contract,
            interval=interval,
            _from=int(from_ts),
            to=int(to_ts),
        )
        rows = []
        for c in candles:
            rows.append({
                "timestamp": pd.to_datetime(int(c.t), unit="s", utc=True),
                "open":   float(c.o),
                "high":   float(c.h),
                "low":    float(c.l),
                "close":  float(c.c),
                "volume": float(c.v) if c.v else 0.0,
                "amount": float(c.sum) if c.sum else 0.0,
            })
        return rows

    # ------------------------------------------------------------------
    # 核心：按时间范围拉取，自动分页，最远支持近一年
    # ------------------------------------------------------------------
    def fetch_range(
        self,
        contract: str,
        interval: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        拉取指定时间范围内的历史K线，自动分页。

        :param contract: 合约名称，如 BTC_USDT
        :param interval: K线周期，如 1m/5m/15m/1h/4h/8h/1d
        :param start:    起始时间（datetime，timezone-aware 或 naive 均可）
                         默认：一年前
        :param end:      结束时间（datetime）默认：当前时间
        :return: DataFrame，index=timestamp(UTC)，列=open/high/low/close/volume/amount
        """
        now = datetime.now(timezone.utc)

        if end is None:
            end = now
        if start is None:
            start = now - timedelta(days=365)

        # 确保 timezone-aware（naive 视为 UTC）
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        # 不允许超过一年
        max_start = now - timedelta(days=365)
        if start < max_start:
            logger.warning("start time is earlier than 1 year ago, clamped to %s", max_start)
            start = max_start

        step_seconds = INTERVAL_SECONDS.get(interval)
        if step_seconds is None:
            raise ValueError(f"unsupported interval '{interval}', "
                             f"supported: {list(INTERVAL_SECONDS.keys())}")

        # 每次请求的时间窗口大小
        chunk_seconds = step_seconds * MAX_POINTS_PER_REQUEST

        from_ts = start.timestamp()
        to_ts   = end.timestamp()

        all_rows = []
        cursor = from_ts
        total_requests = 0

        logger.info("fetching %s %s from %s to %s",
                    contract, interval,
                    start.strftime("%Y-%m-%d %H:%M"),
                    end.strftime("%Y-%m-%d %H:%M"))

        while cursor < to_ts:
            chunk_end = min(cursor + chunk_seconds, to_ts)
            rows = self._fetch_chunk(contract, interval, cursor, chunk_end)
            all_rows.extend(rows)
            total_requests += 1
            logger.debug("  page %d: from=%s got %d bars",
                         total_requests,
                         datetime.fromtimestamp(cursor, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                         len(rows))
            if not rows:
                break
            # 下一页从最后一根K线的下一个周期开始
            cursor = chunk_end + step_seconds
            if cursor < to_ts:
                time.sleep(RATE_LIMIT_SLEEP)

        if not all_rows:
            logger.warning("no data fetched for %s %s", contract, interval)
            return pd.DataFrame()

        df = (pd.DataFrame(all_rows)
                .set_index("timestamp")
                .sort_index()
                # 去重（相邻分页可能有重叠）
                [~pd.DataFrame(all_rows).set_index("timestamp").sort_index().index.duplicated()])
        logger.info("total fetched: %d bars (%d requests)", len(df), total_requests)
        return df

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------
    def fetch_year(self, contract: str, interval: str = "1m") -> pd.DataFrame:
        """拉取近一年全量数据"""
        return self.fetch_range(contract, interval)

    def fetch_month(
        self,
        contract: str,
        year: int,
        month: int,
        interval: str = "1h",
    ) -> pd.DataFrame:
        """
        拉取指定年月的数据，例如 fetch_month('BTC_USDT', 2024, 3)
        """
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        # 下个月第一天
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        return self.fetch_range(contract, interval, start=start, end=end)

    def fetch_latest_bar(self, contract: str, interval: str = "1m") -> pd.Series:
        """拉取最新一根已完成的K线（实盘用）"""
        now = datetime.now(timezone.utc)
        start = now - timedelta(seconds=INTERVAL_SECONDS.get(interval, 60) * 3)
        df = self.fetch_range(contract, interval, start=start, end=now)
        if len(df) < 1:
            raise RuntimeError(f"no latest bar fetched for {contract} {interval}")
        return df.iloc[-2] if len(df) >= 2 else df.iloc[-1]

    def fetch_ticker(self, contract: str):
        """获取最新行情 Ticker，合约不存在时返回 None"""
        try:
            tickers = self.futures_api.list_futures_tickers(self.settle, contract=contract)
            return tickers[0] if tickers else None
        except GateApiException as e:
            if e.label in ("CONTRACT_NOT_FOUND", "INVALID_PARAM"):
                logger.warning("fetch_ticker: contract %s not found", contract)
                return None
            raise
