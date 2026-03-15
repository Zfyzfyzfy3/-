# !/usr/bin/env python
# coding: utf-8

# Gate.io API 配置
API_KEY = ""
API_SECRET = ""
API_HOST = "https://api.gateio.ws/api/v4"

# 合约配置
SETTLE = "usdt"
CONTRACT = "BTC_USDT"

# 回测配置
BACKTEST_INITIAL_CAPITAL = 10000  # 初始资金（USDT）
BACKTEST_FEE_RATE = 0.0005        # 手续费率（0.05%）

# 实盘风控配置
MAX_DRAWDOWN = 0.10       # 最大回撤限制 10%
MAX_POSITION_RATIO = 0.5  # 单仓最大仓位占比 50%
MAX_DAILY_LOSS = 0.05     # 单日最大亏损 5%
