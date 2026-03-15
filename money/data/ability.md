# DataFetcher 行情数据类功能说明

文件：`data/fetcher.py`

---

## 公开方法

### `fetch_range(contract, interval, start, end)` — 核心方法

按任意时间范围拉取历史K线，自动分页处理。

| 参数 | 类型 | 说明 |
|------|------|------|
| `contract` | str | 合约名称，如 `BTC_USDT` |
| `interval` | str | K线周期，见下方支持列表 |
| `start` | datetime \| None | 起始时间（naive 视为 UTC），默认一年前 |
| `end` | datetime \| None | 结束时间，默认当前时间 |

返回：`pd.DataFrame`，index 为 UTC timestamp，列为 `open / high / low / close / volume / amount`

**关键机制：**
- Gate.io API 单次最多返回 **2000** 根K线，超范围自动切分时间窗口循环请求
- `_from` / `to` 时间戳参数与 `limit` 不兼容，时间范围查询只传前两者
- 相邻分页之间有 0.3s 休眠，避免触发限速
- 去重处理：分页边界可能重叠，自动按 timestamp 去重

---

### `fetch_year(contract, interval)` — 便捷方法

拉取近一年全量数据，等价于 `fetch_range` 不传 `start/end`。

```python
df = fetcher.fetch_year('BTC_USDT', interval='1h')
# 返回约 8760 根K线（分 5 次请求自动完成）
```

---

### `fetch_month(contract, year, month, interval)` — 便捷方法

拉取指定年月的全部K线，适合回测指定时间段。

```python
df = fetcher.fetch_month('BTC_USDT', year=2024, month=3, interval='1h')
# 精确返回 2024-03-01 00:00 UTC ~ 2024-03-31 23:00 UTC 的数据
```

---

### `fetch_latest_bar(contract, interval)` — 实盘用

拉取最新一根**已完成**的K线（取倒数第二根，确保该周期已收盘）。

---

### `fetch_ticker(contract)` — 实时行情

返回指定合约的最新 Ticker 对象（含最新价、成交量等），无需鉴权。

---

## 支持的 K 线周期

| interval | 周期 | 单次最多时间跨度（2000根） |
|----------|------|--------------------------|
| `10s` | 10 秒 | ~5.5 小时 |
| `1m` | 1 分钟 | ~33 小时 |
| `5m` | 5 分钟 | ~7 天 |
| `15m` | 15 分钟 | ~20 天 |
| `30m` | 30 分钟 | ~41 天 |
| `1h` | 1 小时 | ~83 天 |
| `4h` | 4 小时 | ~333 天 |
| `1d` | 1 天 | ~5.5 年 |

---

## 约束与保护

- **最远只支持近一年数据**：`start` 超出一年前自动截断并输出 warning
- **不支持 `limit` 参数**：时间范围模式下统一用 `_from + to` 查询，避免 API 冲突
- 分页请求失败（返回空）时自动终止循环，不抛出异常
