# !/usr/bin/env python
# coding: utf-8
"""
主入口

用法:
  回测（默认全年）:          python main.py backtest
  回测（指定月份）:          python main.py backtest --start 2024-03-01 --end 2024-03-31
  实盘:                      python main.py live
"""
import logging
import sys
from argparse import ArgumentParser

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def run_backtest(start=None, end=None):
    from config.settings import (API_KEY, API_SECRET, API_HOST,
                                  CONTRACT, BACKTEST_INITIAL_CAPITAL, BACKTEST_FEE_RATE)
    from data.fetcher import DataFetcher
    from data.storage import DataStorage
    from strategy.ma_cross import MACrossStrategy
    from backtest.engine import BacktestEngine

    logger.info("=== 开始回测 (%s → %s) ===", start or "一年前", end or "现在")

    storage = DataStorage()
    df = storage.load(CONTRACT, "1h")

    if df is None:
        logger.info("本地无缓存，从 API 拉取近一年数据...")
        fetcher = DataFetcher(API_KEY, API_SECRET, API_HOST)
        df = fetcher.fetch_year(CONTRACT, interval="1h")
        storage.save(df, CONTRACT, "1h")
    else:
        logger.info("使用本地缓存数据（%d 根K线）", len(df))

    strategy = MACrossStrategy(CONTRACT, fast=5, slow=20, order_size=10)
    engine = BacktestEngine(
        strategy        = strategy,
        data            = df,
        start           = start,   # 如 '2024-03-01'，None 表示全量
        end             = end,     # 如 '2024-03-31'，None 表示全量
        initial_capital = BACKTEST_INITIAL_CAPITAL,
        fee_rate        = BACKTEST_FEE_RATE,
    )
    engine.report()


def run_live():
    from config.settings import API_KEY, API_SECRET, API_HOST, CONTRACT
    from strategy.ma_cross import MACrossStrategy
    from live.trader import LiveTrader

    logger.info("=== 启动实盘 ===")
    strategy = MACrossStrategy(CONTRACT, fast=5, slow=20, order_size=10)
    trader = LiveTrader(strategy, API_KEY, API_SECRET, API_HOST,
                        interval="1h", poll_seconds=60)
    trader.run()


if __name__ == "__main__":
    parser = ArgumentParser(description="量化交易系统")
    parser.add_argument("mode", choices=["backtest", "live"], help="运行模式")
    parser.add_argument("--start", default=None, help="回测开始日期，如 2024-03-01")
    parser.add_argument("--end",   default=None, help="回测结束日期，如 2024-03-31")
    options = parser.parse_args()

    if options.mode == "backtest":
        run_backtest(start=options.start, end=options.end)
    elif options.mode == "live":
        run_live()

