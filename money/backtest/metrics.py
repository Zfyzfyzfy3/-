# !/usr/bin/env python
# coding: utf-8
"""
绩效指标计算
基于 Portfolio.equity_series() 和 Portfolio.closed_trades 计算：
  年化收益率、夏普比率、最大回撤、胜率、盈亏比、交易次数等
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calc_metrics(portfolio) -> dict:
    equity  = portfolio.equity_series()
    initial = portfolio.initial_capital
    final   = portfolio.final_equity
    trades  = portfolio.closed_trades

    if equity.empty or len(equity) < 2:
        return {"错误": "数据不足，无法计算指标"}

    # ── 收益率 ────────────────────────────────────────────────────────
    days = max((equity.index[-1] - equity.index[0]).total_seconds() / 86400, 1)
    total_return  = (final / initial) - 1
    ratio = final / initial
    # 若净值 ≤ 0（超额亏损），年化收益率直接定为 -100%，避免复数结果
    annual_return = ratio ** (365 / days) - 1 if ratio > 0 else -1.0

    # ── 每日收益率（用于夏普/波动率）──────────────────────────────────
    daily = equity.resample("1D").last().ffill()
    daily_ret = daily.pct_change().dropna()
    rf = 0.03 / 365   # 无风险利率（日）
    excess = daily_ret - rf
    sharpe = float(excess.mean() / excess.std() * np.sqrt(365)) \
             if excess.std() > 0 else 0.0

    # ── 最大回撤 ──────────────────────────────────────────────────────
    roll_max   = equity.cummax()
    drawdown   = (equity - roll_max) / roll_max
    max_dd     = float(drawdown.min())

    # ── 回撤持续天数（按自然日）───────────────────────────────────────
    # 注意：必须用日线净值序列统计；若用 equity 样本点计数会把“点数”误当“天数”。
    daily_roll_max = daily.cummax()
    daily_drawdown = (daily - daily_roll_max) / daily_roll_max
    in_dd_daily = daily_drawdown < 0
    dd_day_groups = (in_dd_daily != in_dd_daily.shift()).cumsum()
    dd_day_lengths = in_dd_daily[in_dd_daily].groupby(dd_day_groups[in_dd_daily]).count()
    max_dd_days = int(dd_day_lengths.max()) if not dd_day_lengths.empty else 0

    # ── 交易统计 ──────────────────────────────────────────────────────
    n_trades  = len(trades)
    if n_trades > 0:
        pnls     = [t.pnl for t in trades]
        wins     = [p for p in pnls if p > 0]
        losses   = [p for p in pnls if p <= 0]
        win_rate = len(wins) / n_trades

        avg_win  = float(np.mean(wins))   if wins   else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        profit_factor = abs(sum(wins) / sum(losses)) \
                        if sum(losses) != 0 else float("inf")
        avg_pnl      = float(np.mean(pnls))
        total_fee    = sum(t.fee for t in trades)
    else:
        win_rate = win_rate  = avg_win = avg_loss = profit_factor = avg_pnl = total_fee = 0.0

    result = {
        "初始资金":      f"{initial:,.2f} USDT",
        "最终净值":      f"{final:,.2f} USDT",
        "总收益率":      f"{total_return*100:.2f}%",
        "年化收益率":    f"{annual_return*100:.2f}%",
        "夏普比率":      f"{sharpe:.3f}",
        "最大回撤":      f"{max_dd*100:.2f}%",
        "最大回撤天数":  f"{max_dd_days} 天",
        "总交易次数":    n_trades,
        "胜率":          f"{win_rate*100:.1f}%",
        "盈亏比":        f"{profit_factor:.2f}",
        "平均每笔盈亏":  f"{avg_pnl:.4f} USDT",
        "平均盈利":      f"{avg_win:.4f} USDT",
        "平均亏损":      f"{avg_loss:.4f} USDT",
        "总手续费":      f"{total_fee:.4f} USDT",
    }
    _log_metrics(result)
    return result


def _log_metrics(metrics: dict) -> None:
    logger.info("----- 回测指标 -----")
    for k, v in metrics.items():
        logger.info("  %-14s: %s", k, v)
    logger.info("-" * 30)

def calc_metrics_raw(portfolio) -> dict:
    """返回原始数值（不格式化），方便程序化使用"""
    equity  = portfolio.equity_series()
    initial = portfolio.initial_capital
    final   = portfolio.final_equity
    trades  = portfolio.closed_trades

    if equity.empty or len(equity) < 2:
        return {}

    days = max((equity.index[-1] - equity.index[0]).total_seconds() / 86400, 1)
    total_return  = (final / initial) - 1
    ratio = final / initial
    annual_return = ratio ** (365 / days) - 1 if ratio > 0 else -1.0

    daily = equity.resample("1D").last().ffill()
    daily_ret = daily.pct_change().dropna()
    rf = 0.03 / 365
    excess = daily_ret - rf
    sharpe = float(excess.mean() / excess.std() * np.sqrt(365)) \
             if excess.std() > 0 else 0.0

    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    max_dd   = float(drawdown.min())

    daily_roll_max = daily.cummax()
    daily_drawdown = (daily - daily_roll_max) / daily_roll_max
    in_dd_daily = daily_drawdown < 0
    dd_day_groups = (in_dd_daily != in_dd_daily.shift()).cumsum()
    dd_day_lengths = in_dd_daily[in_dd_daily].groupby(dd_day_groups[in_dd_daily]).count()
    max_dd_days = int(dd_day_lengths.max()) if not dd_day_lengths.empty else 0

    pnls     = [t.pnl for t in trades]
    wins     = [p for p in pnls if p > 0]
    losses   = [p for p in pnls if p <= 0]

    return {
        "total_return":   total_return,
        "annual_return":  annual_return,
        "sharpe":         sharpe,
        "max_drawdown":   max_dd,
        "max_drawdown_days": max_dd_days,
        "n_trades":       len(trades),
        "win_rate":       len(wins) / len(trades) if trades else 0.0,
        "profit_factor":  abs(sum(wins) / sum(losses)) if losses else float("inf"),
        "final_equity":   final,
    }
