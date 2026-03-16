# !/usr/bin/env python
# coding: utf-8
"""
主入口

用法:
  通过配置文件运行:
    python main.py

可选策略:
  ma_cross   均线交叉策略（金叉做多，死叉做空）
             参数: fast / slow / order_size / only_long
"""
import logging
import os
import sys
from types import SimpleNamespace

import yaml

# gate_api 包位于 gateapi-python/ 目录下，加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateapi-python"))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "strategy_config.yaml")


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


def _load_config(path: str = CONFIG_PATH) -> SimpleNamespace:
    """读取 YAML 配置并转换为运行参数对象"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    runtime = cfg.get("runtime", {})
    api = cfg.get("api", {})
    market = cfg.get("market", {})
    backtest = cfg.get("backtest", {})
    strategy_name = runtime.get("strategy", "ma_cross")
    strategy_cfg = cfg.get(strategy_name, {})

    args = SimpleNamespace(
        mode=runtime.get("mode", "backtest"),
        start=runtime.get("start"),
        end=runtime.get("end"),
        no_cache=bool(runtime.get("no_cache", False)),
        strategy=strategy_name,
        fast=int(strategy_cfg.get("fast", 5)),
        slow=int(strategy_cfg.get("slow", 20)),
        order_size=float(strategy_cfg.get("order_size", 0.001)),
        only_long=bool(strategy_cfg.get("only_long", False)),
        interval=strategy_cfg.get("interval", "1h"),
        contract=market.get("contract", "BTC_USDT"),
        settle=market.get("settle", "usdt"),
        initial_capital=float(backtest.get("initial_capital", 10000)),
        fee_rate=float(backtest.get("fee_rate", 0.0005)),
        poll_seconds=int(runtime.get("poll_seconds", 60)),
        api_key=api.get("key", ""),
        api_secret=api.get("secret", ""),
        api_host=api.get("host", "https://api.gateio.ws/api/v4"),
    )

    if args.strategy != "ma_cross":
        raise ValueError(f"未知策略: {args.strategy}。目前支持: ma_cross")
    if args.mode not in {"backtest", "live"}:
        raise ValueError(f"未知模式: {args.mode}。可选: backtest, live")
    if args.fast >= args.slow:
        raise ValueError(f"fast ({args.fast}) 必须小于 slow ({args.slow})")
    supported_intervals = {
        "10s", "1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d", "7d", "30d"
    }
    if args.interval not in supported_intervals:
        raise ValueError(
            f"不支持的 interval: {args.interval}，可选: {sorted(supported_intervals)}"
        )
    if not args.api_key or not args.api_secret:
        raise ValueError("缺少 API 凭证: 请在配置文件中填写 api.key 和 api.secret")
    return args


# ──────────────────────────────────────────────────────────────────────
# 回测入口
# ──────────────────────────────────────────────────────────────────────
def run_backtest(args):
    from data.fetcher import DataFetcher
    from data.storage import DataStorage
    from backtest.engine import BacktestEngine

    start    = args.start
    end      = args.end
    no_cache = args.no_cache
    contract = args.contract

    logger.info("=== 开始回测 策略=%s  时间段: %s → %s ===",
                args.strategy, start or "一年前", end or "现在")

    # ── 数据加载 ──────────────────────────────────────────────────────
    storage = DataStorage()
    df = None if no_cache else storage.load(contract, args.interval)

    if df is None:
        reason = "强制刷新" if no_cache else "本地无缓存"
        logger.info("%s，从 API 拉取近一年数据...", reason)
        fetcher = DataFetcher(args.api_key, args.api_secret, args.api_host)
        df = fetcher.fetch_year(contract, interval=args.interval)
        storage.save(df, contract, args.interval)
    else:
        logger.info("使用本地缓存数据（%d 根K线）", len(df))

    # ── 策略构造 ──────────────────────────────────────────────────────
    strategy = _build_strategy(args.strategy, contract, args)

    # ── 引擎运行并打印报告 ────────────────────────────────────────────
    engine = BacktestEngine(
        strategy        = strategy,
        data            = df,
        start           = start,
        end             = end,
        initial_capital = args.initial_capital,
        fee_rate        = args.fee_rate,
        indicators      = _indicators_for(args.strategy),
        config_snapshot = {
            "mode": args.mode,
            "strategy": args.strategy,
            "contract": args.contract,
            "interval": args.interval,
            "start": args.start,
            "end": args.end,
            "no_cache": args.no_cache,
        },
    )
    engine.report()   # 自动打印：指标 + 净值曲线图 + 全部历史仓位


# ──────────────────────────────────────────────────────────────────────
# 实盘入口
# ──────────────────────────────────────────────────────────────────────
def run_live(args):
    from live.trader import LiveTrader

    logger.info("=== 启动实盘 策略=%s ===", args.strategy)
    strategy = _build_strategy(args.strategy, args.contract, args)
    trader = LiveTrader(strategy, args.api_key, args.api_secret, args.api_host,
                        interval=args.interval, poll_seconds=args.poll_seconds)
    trader.run()


if __name__ == "__main__":
    args = _load_config()
    logger.info(
        "配置加载完成: mode=%s strategy=%s contract=%s interval=%s",
        args.mode, args.strategy, args.contract, args.interval
    )

    if args.mode == "backtest":
        run_backtest(args)
    elif args.mode == "live":
        run_live(args)
