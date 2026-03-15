# !/usr/bin/env python
# coding: utf-8
"""
实盘交易引擎
定时拉取最新K线，驱动策略生成信号，经风控后下单执行
"""
import time
import logging
import pandas as pd
from gate_api import ApiClient, Configuration, FuturesApi, FuturesOrder
from gate_api.exceptions import GateApiException

from live.risk import RiskManager
from data.fetcher import DataFetcher
from data.preprocessor import add_ma, add_ema, add_rsi, add_bollinger

logger = logging.getLogger(__name__)


class LiveTrader:
    def __init__(self, strategy, api_key, api_secret, host,
                 settle="usdt", interval="1h", poll_seconds=60):
        self.strategy = strategy
        self.settle = settle
        self.interval = interval
        self.poll_seconds = poll_seconds

        config = Configuration(key=api_key, secret=api_secret, host=host)
        self.futures_api = FuturesApi(ApiClient(config))
        self.fetcher = DataFetcher(api_key, api_secret, host, settle)
        self.risk = RiskManager()
        self._history = None

    def _prepare(self, df):
        df = add_ma(df, [5, 10, 20, 60])
        df = add_ema(df, [12, 26])
        df = add_rsi(df)
        df = add_bollinger(df)
        return df

    def run(self):
        logger.info("live trader started, contract=%s interval=%s",
                    self.strategy.contract, self.interval)
        self.strategy.on_start()

        # 初始化历史数据
        self._history = self._prepare(
            self.fetcher.fetch_candlesticks(self.strategy.contract,
                                            self.interval, limit=200)
        )

        while True:
            try:
                bar = self.fetcher.fetch_latest_bar(
                    self.strategy.contract, self.interval)
                self._history = pd.concat(
                    [self._history, bar.to_frame().T]
                ).iloc[-500:]

                signal = self.strategy.on_bar(bar, self._history)
                if signal and self.risk.check(signal, self.futures_api, self.settle):
                    self._execute(signal)

            except GateApiException as e:
                logger.error("api error: label=%s msg=%s", e.label, e.message)
            except Exception as e:
                logger.exception("unexpected error: %s", e)

            time.sleep(self.poll_seconds)

    def _execute(self, signal):
        order = FuturesOrder(
            contract=signal.contract,
            size=signal.size,
            price="0",
            tif="ioc"
        )
        try:
            resp = self.futures_api.create_futures_order(self.settle, order)
            logger.info("order created: id=%s status=%s size=%d reason=%s",
                        resp.id, resp.status, signal.size, signal.reason)
        except GateApiException as e:
            logger.error("order failed: %s", e.message)
