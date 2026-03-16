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
import os
from datetime import datetime
from typing import Optional, Union

import pandas as pd
from backtest.portfolio import Portfolio, InsufficientBalanceError
from backtest.metrics import calc_metrics
from data.preprocessor import add_ma, add_ema, add_rsi, add_bollinger, add_macd

logger = logging.getLogger(__name__)

# 日志文件存放目录（相对 money/ 根目录）
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "Log", "backTest")


def _setup_file_logging(tag: str) -> logging.FileHandler:
    """
    在 Log/backTest/ 下创建带时间戳的日志文件，将 backtest 相关 logger
    的输出同时写入该文件，返回 handler（供后续 remove）。
    """
    os.makedirs(_LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(_LOG_DIR, f"backtest_{tag}_{ts}.log")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    # 挂载到 backtest / data / strategy 根 logger，确保捕获所有子模块日志
    for name in ("backtest", "data", "strategy", "__main__"):
        logging.getLogger(name).addHandler(fh)
        logging.getLogger(name).setLevel(logging.DEBUG)
    logger.info("日志文件: %s", log_path)
    return fh


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
        config_snapshot: Optional[dict] = None,
        multi_data: Optional[dict] = None,
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
        self.config_snapshot = config_snapshot or {}
        self.multi_data = multi_data or {}

        # 初始化文件日志
        contract = getattr(strategy, 'contract', 'UNKNOWN')
        self._log_handler = _setup_file_logging(contract)
        logger.info(
            "BacktestEngine 初始化: contract=%s strategy=%s start=%s end=%s "
            "initial_capital=%.2f fee_rate=%.4f indicators=%s",
            contract, type(strategy).__name__,
            self.start or '最早', self.end or '最新',
            initial_capital, fee_rate, self.indicators
        )

    def _report_config_items(self) -> list[tuple[str, object]]:
        """汇总本次回测配置，用于报告打印"""
        items = [
            ("mode", self.config_snapshot.get("mode", "backtest")),
            ("strategy", type(self.strategy).__name__),
            ("contract", getattr(self.strategy, "contract", "UNKNOWN")),
            ("interval", self.config_snapshot.get("interval", "N/A")),
            ("multi_intervals", self.config_snapshot.get("multi_intervals", [])),
            ("start", self.start or "最早"),
            ("end", self.end or "最新"),
            ("initial_capital", self.portfolio.initial_capital),
            ("fee_rate", self.portfolio.fee_rate),
            ("indicators", self.indicators),
            ("no_cache", self.config_snapshot.get("no_cache", "N/A")),
        ]
        for k, v in sorted(getattr(self.strategy, "params", {}).items()):
            items.append((f"param.{k}", v))
        return items

    def _equity_at_price(self, price: float) -> float:
        """按当前持仓和给定价格估算账户净值（含未实现盈亏）"""
        pos = self.portfolio.position
        if pos > 0:
            unrealized = pos * (price - self.portfolio.entry_price)
        elif pos < 0:
            unrealized = abs(pos) * (self.portfolio.entry_price - price)
        else:
            unrealized = 0.0
        return self.portfolio.capital + unrealized

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
        total_bars = len(df)
        logger.info("开始逐K线回测，共 %d 根K线", total_bars)
        self.strategy.on_start()

        day_index = df.index.normalize()
        unique_days = day_index.unique()
        total_days = len(unique_days)
        start_day = unique_days[0].date() if total_days > 0 else None
        day_no_map = {d.date(): i + 1 for i, d in enumerate(unique_days)}
        if start_day:
            logger.info("运行状态: 回测起始日=%s，总交易日=%d", start_day, total_days)

        signal_count = 0
        stopped_early = False
        for i in range(total_bars):
            history = df.iloc[:i + 1]   # 含当前 bar 的全部历史
            bar     = df.iloc[i]
            if self.multi_data:
                multi_history = {}
                for interval, df_tf in self.multi_data.items():
                    if df_tf is None or df_tf.empty:
                        multi_history[interval] = df_tf
                        continue
                    multi_history[interval] = df_tf[df_tf.index <= bar.name]
                signal = self.strategy.on_bar_multi(bar, history, multi_history)
            else:
                signal  = self.strategy.on_bar(bar, history)
            if signal:
                signal_count += 1
                logger.info(
                    "[bar %d/%d] %s 信号: size=%+d reason=%s price=%.4f",
                    i + 1, total_bars, bar.name,
                    signal.size, signal.reason, float(bar["close"])
                )
                try:
                    self.portfolio.execute(signal, bar)
                except InsufficientBalanceError as e:
                    price = float(bar["close"])
                    # 记录当根K线净值快照，避免净值曲线为空
                    self.portfolio._snapshot(price, bar.name)
                    equity = self._equity_at_price(price)
                    current_day = bar.name.date()
                    day_no = day_no_map.get(current_day, 0)
                    logger.warning("回测提前终止（第 %d/%d 根K线）: %s", i + 1, total_bars, e)
                    logger.info(
                        "运行状态: 起始日=%s 当前第%d/%d天 当前日=%s 当前时刻=%s "
                        "余额(含浮盈亏)=%.4f 可用资金=%.4f 持仓=%+d",
                        start_day, day_no, total_days, current_day, bar.name,
                        equity, self.portfolio.capital, self.portfolio.position
                    )
                    stopped_early = True
                    break
            else:
                # 无信号也要记录净值曲线（便于回撤/收益计算）
                self.portfolio._snapshot(float(bar["close"]), bar.name)

            # 每个交易日最后一根K线：打印当日运行状态与日终余额
            current_day = bar.name.date()
            is_last_bar_of_day = (i == total_bars - 1) or (df.index[i + 1].date() != current_day)
            if is_last_bar_of_day and start_day:
                day_no = day_no_map.get(current_day, 0)
                price = float(bar["close"])
                equity = self._equity_at_price(price)
                day_end_2359 = bar.name.normalize() + pd.Timedelta(hours=23, minutes=59)
                logger.info(
                    "运行状态: 起始日=%s 当前第%d/%d天 当前日=%s 日内最后K线=%s "
                    "日终时刻=%s 余额(含浮盈亏)=%.4f 可用资金=%.4f 持仓=%+d",
                    start_day, day_no, total_days, current_day, bar.name,
                    day_end_2359,
                    equity, self.portfolio.capital, self.portfolio.position
                )

        self.strategy.on_stop()
        if stopped_early:
            logger.info("回测因余额不足提前结束，已完成 %d/%d 根K线，触发信号 %d 次，成交 %d 笔",
                        i + 1, total_bars, signal_count, len(self.portfolio.closed_trades))
        else:
            logger.info("回测完成，共 %d 根K线，触发信号 %d 次，成交 %d 笔",
                        total_bars, signal_count, len(self.portfolio.closed_trades))
        metrics = calc_metrics(self.portfolio)
        return metrics, self.portfolio

    # ------------------------------------------------------------------
    # 报告（含终端净值曲线图）
    # ------------------------------------------------------------------
    def report(self):
        logger.info("========== 回测报告开始 ==========")
        metrics, portfolio = self.run()

        # ── 文字报告 ──────────────────────────────────────────────────
        print("\n" + "=" * 55)
        print(f"  回测报告  合约: {self.strategy.contract}")
        print("  本次配置:")
        for k, v in self._report_config_items():
            print(f"  {k:14s}: {v}")
            logger.info("  [config] %-14s: %s", k, v)
        print("=" * 55)
        for k, v in metrics.items():
            print(f"  {k:14s}: {v}")
            logger.info("  %-14s: %s", k, v)
        print("=" * 55)
        logger.info("========== 回测报告结束 ==========")

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
