# 单测覆盖说明

## 运行方式

```bash
cd /home/dehuazhang12/codebase/quantTrading/money

# 全量
python -m pytest tests/ -v

# 仅回测模块
python -m pytest tests/backtest/test_backtest.py -v

# 仅数据模块
python -m pytest tests/data/test_fetcher.py -v

# 终端蜡烛图（需 -s 打印 stdout）
python -m pytest tests/data/test_fetcher.py::TestCandlestickChart -v -s
```

---

## 一、回测系统（tests/backtest/test_backtest.py）

**数据来源**：模块顶层拉取 Gate.io 真实行情一次（BTC_USDT 1h，2025-06-01 ~ 2025-09-01，约 2208 根），所有引擎/指标测试共享，避免重复网络请求。Portfolio/Trade 算术验证使用合成 bar（纯数字，无需网络）。

### 1.1 TestPortfolioOpenClose — 开/平仓基础逻辑

| 用例 | 测试场景 |
|------|----------|
| `test_long_profit` | 开多 10 手 @ 100，平多 @ 110 → 验证 `direction="long"`、`entry/exit_price`、`pnl` 数学精确值（手工验算）、`pnl > 0` |
| `test_long_loss` | 开多 @ 100，平多 @ 90 → `pnl < 0` |
| `test_short_profit` | 开空 @ 100，平空 @ 90 → `direction="short"`，`pnl > 0` |
| `test_short_loss` | 开空 @ 100，平空 @ 110 → `pnl < 0` |

### 1.2 TestPortfolioReversal — 反向开仓

| 用例 | 测试场景 |
|------|----------|
| `test_long_to_short` | 持多 10 手后发 `size=-20`：自动平多 10 手 + 开空 10 手；验证 `position=-10`、`closed_trades` 计数与方向；再平空后 `position=0` |
| `test_short_to_long` | 持空 10 手后发 `size=+20`：平空 + 开多，验证 `position=+10`、`closed_trades=1` |

### 1.3 TestPortfolioEquity — 净值曲线

| 用例 | 测试场景 |
|------|----------|
| `test_equity_series_length` | 连续 5 次 execute → `equity_series()` 长度恰好为 5，类型为 `pd.Series` |
| `test_initial_equity` | 空仓状态下净值快照 = 初始资金（12345 USDT） |
| `test_final_equity_after_close` | 平仓后无浮盈亏，`final_equity == portfolio.capital` |

### 1.4 TestMetrics — 绩效指标（真实数据驱动）

| 用例 | 测试场景 |
|------|----------|
| `test_metrics_keys` | `calc_metrics()` 返回字典包含全部 14 个预定义中文键 |
| `test_metrics_raw_types` | `calc_metrics_raw()` 所有值为 `int` 或 `float`，无 NaN |
| `test_total_return_direction` | `profit_factor` 无 inf（数值有界） |
| `test_metrics_win_rate_range` | `win_rate ∈ [0, 1]` |
| `test_metrics_max_drawdown_negative` | `max_drawdown ≤ 0`，无 NaN（杠杆合约净值可为负，不设下界） |
| `test_metrics_no_trades` | 零交易场景不崩溃，`n_trades=0`，`win_rate=0.0` |

### 1.5 TestBacktestEngine — 引擎端到端（真实 BTC_USDT 1h 行情）

`setUpClass` 跑一次完整回测，后续用例复用结果。

| 用例 | 测试场景 |
|------|----------|
| `test_real_data_not_empty` | 真实行情行数 > 500，含 open/high/low/close/volume 列 |
| `test_run_returns_two_values` | `engine.run()` 返回 `(metrics, portfolio)` 两元组，均非 None |
| `test_metrics_dict` | `metrics` 是字典且含 `"总收益率"` 键 |
| `test_equity_curve_not_empty` | `equity_series()` 长度在 `(0, len(REAL_DF)]` 范围内 |
| `test_equity_index_is_datetime` | 净值曲线 index 是 `pd.Timestamp`，最早时间 ≥ 真实数据最早时间 |
| `test_at_least_one_trade` | 2208 根 K 线至少产生 1 笔已平仓交易 |
| `test_closed_trade_prices_match_real_data` | 所有成交开/平仓价格落在真实 K 线 `[low.min(), high.max()]` 区间内 |
| `test_final_equity_is_finite` | `final_equity` 非 NaN、非 inf（不验证正负，取决于市场） |
| `test_no_open_position_at_end` | `on_stop()` 执行后不抛异常 |
| `test_time_range_filter` | 设置 `start="2025-07-15"` 后净值曲线长度 < 全量，且起始时间 ≥ 2025-07-15 |
| `test_only_long_mode` | `only_long=True` 时全部已平仓交易 `direction != "short"` |

### 1.6 TestTrade — Trade 属性数学验证

| 用例 | 测试场景 |
|------|----------|
| `test_long_pnl_formula` | 多头 `pnl = size*(exit-entry) - fee` 精确匹配 |
| `test_short_pnl_formula` | 空头 `pnl = size*(entry-exit) - fee` 精确匹配 |
| `test_pnl_pct` | `pnl_pct = pnl / (size * entry_price)`，价格涨 10% → `pnl_pct = 0.1` |

---

## 二、数据模块（tests/data/test_fetcher.py）

所有测试均为真实网络请求（Gate.io 公开行情接口，无需 API Key）。

### 2.1 TestFetchRangeBasic — 基础功能

| 用例 | 测试场景 |
|------|----------|
| `test_columns_exist` | 返回 DataFrame 含 open/high/low/close/volume 列 |
| `test_index_has_timezone` | index 带 UTC 时区信息 |
| `test_data_within_requested_range` | 所有时间戳在 `[start, end]` 内 |
| `test_no_duplicate_timestamps` | 3个月数据无重复时间戳 |
| `test_sorted_ascending` | 数据按时间升序排列 |
| `test_price_sanity` | `close > 0`，`high >= low`，`volume >= 0` |

### 2.2 TestFetchRangeIntervals — 各周期覆盖

| 用例 | 周期 | 测试场景 |
|------|------|----------|
| `test_1m` | 1m | 2小时 ≈ 120 根，1m 只允许近 ~6.9 天使用近期日期 |
| `test_5m` | 5m | 24小时 ≈ 288 根，5m 只允许近 ~34 天使用近期日期 |
| `test_1h` | 1h | 7天 ≈ 168 根 |
| `test_4h` | 4h | 30天 ≈ 180 根 |
| `test_1d` | 1d | 3个月 ≈ 90 根 |
| `test_unsupported_interval_raises` | — | 非法 interval 抛 `ValueError` |

### 2.3 TestPagination — 自动分页（> 2000 根）

| 用例 | 测试场景 |
|------|----------|
| `test_3months_1h_exceeds_2000` | 3个月 1h ≈ 2160 根，超过单次上限，验证分页后无重复、单调递增 |
| `test_7days_5m_near_2000_boundary` | 7天 5m ≈ 2016 根，跨分页边界，验证边界无遗漏 |

### 2.4 TestFetchMonth — 按月拉取

| 用例 | 测试场景 |
|------|----------|
| `test_august_2025_bar_count` | 8月31天，1h K线根数在 `[730, 745]` |
| `test_august_2025_time_boundary` | 返回数据时间戳在 8月完整范围内 |
| `test_december_2025_crosses_year` | 12月跨年边界正确处理 |
| `test_june_shorter_bar_count_than_august` | 30天 vs 31天，K线数量关系正确 |

### 2.5 TestBoundaryProtection — 边界与保护

| 用例 | 测试场景 |
|------|----------|
| `test_start_too_early_clamped` | `start=2020-01-01`（超出一年窗口）自动截断，不报错仍有数据 |
| `test_naive_datetime_treated_as_utc` | 无时区 `datetime` 视为 UTC，不抛异常 |
| `test_empty_result_when_start_after_end` | `start > end` 返回空 DataFrame |

### 2.6 TestFetchTicker — 实时行情

| 用例 | 测试场景 |
|------|----------|
| `test_ticker_not_none` | `fetch_ticker(BTC_USDT)` 返回非 None |
| `test_ticker_last_price_positive` | 最新价 > 0，打印实时价格 |
| `test_ticker_invalid_contract_returns_none` | 无效合约返回 `None`，不抛异常 |

### 2.7 TestCandlestickChart — 终端蜡烛图

| 用例 | 测试场景 |
|------|----------|
| `test_print_monthly_candlestick_chart` | 拉取近30天 1d K线，用 plotext 在终端绘制蜡烛图；验证 `len(opens)==len(closes)`，`high >= low` |

---

## 三、覆盖统计

| 模块 | 测试文件 | 用例数 |
|------|----------|--------|
| `backtest/portfolio.py` | test_backtest.py | 10 |
| `backtest/metrics.py` | test_backtest.py | 6 |
| `backtest/engine.py` | test_backtest.py | 11 |
| `strategy/ma_cross.py` | test_backtest.py（间接）| — |
| `data/fetcher.py` | test_fetcher.py | 25 |
| **合计** | | **52** |
