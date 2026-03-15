# !/usr/bin/env python
# coding: utf-8
"""
绩效指标计算
"""
import numpy as np
import pandas as pd


def calc_metrics(portfolio):
    equity = pd.DataFrame(portfolio.equity_curve).set_index("time")["equity"]
    initial = portfolio.initial_capital
    final = portfolio.final_equity
    days = max((equity.index[-1] - equity.index[0]).days, 1)

    # 年化收益率
    annual_return = (final / initial) ** (365 / days) - 1

    # 每日收益率
    daily_returns = equity.pct_change().dropna()

    # 夏普比率（假设无风险利率 3%）
    risk_free = 0.03 / 365
    excess = daily_returns - risk_free
    sharpe = (excess.mean() / excess.std() * np.sqrt(365)) if excess.std() > 0 else 0

    # 最大回撤
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    max_drawdown = drawdown.min()

    # 胜率
    trades = portfolio.trades
    if trades:
        profits = []
        for i in range(1, len(trades)):
            p = trades[i]["price"] - trades[i - 1]["price"]
            if trades[i - 1]["action"] == "sell":
                p = -p
            profits.append(p)
        win_rate = sum(1 for p in profits if p > 0) / len(profits) if profits else 0
    else:
        win_rate = 0

    return {
        "初始资金":      f"{initial:.2f} USDT",
        "最终净值":      f"{final:.2f} USDT",
        "总收益率":      f"{(final/initial - 1)*100:.2f}%",
        "年化收益率":    f"{annual_return*100:.2f}%",
        "夏普比率":      f"{sharpe:.2f}",
        "最大回撤":      f"{max_drawdown*100:.2f}%",
        "总交易次数":    len(trades),
        "胜率":          f"{win_rate*100:.2f}%",
    }
