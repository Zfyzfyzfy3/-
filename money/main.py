# !/usr/bin/env python
# coding: utf-8
"""
主入口

用法:
  回测（默认全年，默认策略 ma_cross）:
    python main.py backtest

  回测（指定时间段）:
    python main.py backtest --start 2025-06-01 --end 2025-09-01

  回测（指定策略及参数）:
    python main.py backtest --strategy ma_cross --fast 10 --slow 30 --order-size 5
    python main.py backtest --strategy ma_cross --only-long

  强制重新拉取远端数据（忽略本地缓存）:
    python main.py backtest --no-cache

  实盘:
    python main.py live --strategy ma_cross

可选策略:
  ma_cross   均线交叉策略（金叉做多，死叉做空）
             参数: --fast INT  --slow INT  --order-size INT  --only-long
"""
import logging
import os
import sys

# gate_api 包位于 gateapi-python/ 目录下，加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateapi-python"))

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 策略注册表：name → (class, indicator_list)
# 新增策略时在此处注册
# ──────────────────────────────────────────────────────────────────────
def _build_strategy(name: str, contract: str, args) -> object:
    """根据策略名和命令行参数构造策略实例"""
    if name == "ma_cross":
        from strategy.ma_cross import MACrossStrategy
        return MACrossStrategy(
            contract,
            fast       = args.fast,
            slow       = args.slow,
            order_size = args.order_size,
            only_long  = args.only_long,
        )
    raise ValueError(f"未知策略: {name}。目前支持: ma_cross")


def _indicators_for(name: str) -> list:
    """返回策略所需的预计算指标列表"""
    if name == "ma_cross":
        return ["ma"]
    return ["ma", "ema", "rsi", "boll", "macd"]


# ──────────────────────────────────────────────────────────────────────
# 回测入口
# ──────────────────────────────────────────────────────────────────────
def run_backtest(args):
    from config.settings import (API_KEY, API_SECRET, API_HOST,
                                  CONTRACT, BACKTEST_INITIAL_CAPITAL, BACKTEST_FEE_RATE)
    from data.fetcher import DataFetcher
    from data.storage import DataStorage
    from backtest.engine import BacktestEngine

    start    = args.start
    end      = args.end
    no_cache = args.no_cache

    logger.info("=== 开始回测 策略=%s  时间段: %s → %s ===",
                args.strategy, start or "一年前", end or "现在")

    # ── 数据加载 ──────────────────────────────────────────────────────
    storage = DataStorage()
    df = None if no_cache else storage.load(CONTRACT, "1h")

    if df is None:
        reason = "强制刷新" if no_cache else "本地无缓存"
        logger.info("%s，从 API 拉取近一年数据...", reason)
        fetcher = DataFetcher(API_KEY, API_SECRET, API_HOST)
        df = fetcher.fetch_year(CONTRACT, interval="1h")
        storage.save(df, CONTRACT, "1h")
    else:
        logger.info("使用本地缓存数据（%d 根K线）", len(df))

    # ── 策略构造 ──────────────────────────────────────────────────────
    strategy = _build_strategy(args.strategy, CONTRACT, args)

    # ── 引擎运行并打印报告 ────────────────────────────────────────────
    engine = BacktestEngine(
        strategy        = strategy,
        data            = df,
        start           = start,
        end             = end,
        initial_capital = BACKTEST_INITIAL_CAPITAL,
        fee_rate        = BACKTEST_FEE_RATE,
        indicators      = _indicators_for(args.strategy),
    )
    engine.report()   # 自动打印：指标 + 净值曲线图 + 全部历史仓位


# ──────────────────────────────────────────────────────────────────────
# 实盘入口
# ──────────────────────────────────────────────────────────────────────
def run_live(args):
    from config.settings import API_KEY, API_SECRET, API_HOST, CONTRACT
    from live.trader import LiveTrader

    logger.info("=== 启动实盘 策略=%s ===", args.strategy)
    strategy = _build_strategy(args.strategy, CONTRACT, args)
    trader = LiveTrader(strategy, API_KEY, API_SECRET, API_HOST,
                        interval="1h", poll_seconds=60)
    trader.run()


# ──────────────────────────────────────────────────────────────────────
# CLI 参数定义
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = ArgumentParser(
        description="量化交易系统",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("mode", choices=["backtest", "live"], help="运行模式")

    # 时间范围（回测专用）
    parser.add_argument("--start",    default=None, metavar="YYYY-MM-DD",
                        help="回测开始日期")
    parser.add_argument("--end",      default=None, metavar="YYYY-MM-DD",
                        help="回测结束日期")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略本地缓存，强制重新拉取行情数据")

    # 策略选择
    parser.add_argument("--strategy", default="ma_cross",
                        choices=["ma_cross"],
                        help="使用的策略名称")

    # ma_cross 策略参数
    ma_group = parser.add_argument_group("ma_cross 策略参数")
    ma_group.add_argument("--fast",       type=int,  default=5,
                          help="快线均线周期")
    ma_group.add_argument("--slow",       type=int,  default=20,
                          help="慢线均线周期")
    ma_group.add_argument("--order-size", type=int,  default=10,
                          dest="order_size", help="每次开仓手数")
    ma_group.add_argument("--only-long",  action="store_true",
                          dest="only_long", help="只做多，不做空")

    args = parser.parse_args()

    # 参数校验
    if args.strategy == "ma_cross" and args.fast >= args.slow:
        parser.error(f"--fast ({args.fast}) 必须小于 --slow ({args.slow})")

    if args.mode == "backtest":
        run_backtest(args)
    elif args.mode == "live":
        run_live(args)

