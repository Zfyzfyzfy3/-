# Gate.io 合约（Futures）API 文档

基于 `gate_api/api/futures_api.py`，共 64 个公开 API，按功能分类如下。

---

## 一、行情 / 市场数据

| 方法 | 说明 |
|------|------|
| `list_futures_contracts(settle)` | 获取所有合约列表 |
| `get_futures_contract(settle, contract)` | 获取单个合约详情 |
| `list_futures_order_book(settle, contract)` | 获取合约深度（Order Book） |
| `list_futures_trades(settle, contract)` | 获取合约成交记录 |
| `list_futures_candlesticks(settle, contract)` | 获取合约 K 线数据 |
| `list_futures_premium_index(settle, contract)` | 获取溢价指数 K 线 |
| `list_futures_tickers(settle)` | 获取合约行情（Ticker） |
| `list_futures_funding_rate_history(settle, contract)` | 获取资金费率历史 |
| `list_batch_futures_funding_rates(settle, batch_funding_rates_request)` | 批量获取资金费率 |
| `list_futures_insurance_ledger(settle)` | 获取保险基金记录 |
| `list_contract_stats(settle, contract)` | 获取合约统计数据 |
| `get_index_constituents(settle, index)` | 获取指数成分 |
| `list_liquidated_orders(settle)` | 获取强平挂单（公开） |
| `list_futures_risk_limit_tiers(settle)` | 获取风险限额梯度列表 |
| `get_futures_risk_limit_table(settle, table_id)` | 获取指定风险限额表 |

---

## 二、账户与资产

| 方法 | 说明 |
|------|------|
| `list_futures_accounts(settle)` | 查询期货账户余额 |
| `list_futures_account_book(settle)` | 查询账户资金流水 |
| `get_futures_fee(settle)` | 查询合约手续费率 |

---

## 三、仓位管理

| 方法 | 说明 |
|------|------|
| `list_positions(settle)` | 查询所有持仓 |
| `list_positions_timerange(settle, contract)` | 按时间范围查询持仓历史 |
| `get_position(settle, contract)` | 查询单个合约持仓 |
| `get_leverage(settle, contract)` | 查询当前杠杆 |
| `update_position_margin(settle, contract, change)` | 调整逐仓保证金 |
| `update_position_leverage(settle, contract, leverage)` | 设置杠杆倍数 |
| `update_contract_position_leverage(settle, contract, leverage, margin_mode)` | 设置合约杠杆 + 保证金模式 |
| `update_position_cross_mode(settle, futures_position_cross_mode)` | 切换全仓 / 逐仓模式 |
| `update_dual_comp_position_cross_mode(settle, inline_object)` | 双向持仓下切换保证金模式 |
| `update_position_risk_limit(settle, contract, risk_limit)` | 更新风险限额 |

---

## 四、持仓模式（单向 / 双向）

| 方法 | 说明 |
|------|------|
| `set_dual_mode(settle, dual_mode)` | 开启 / 关闭双向持仓 |
| `set_position_mode(settle, position_mode)` | 设置持仓模式 |
| `get_dual_mode_position(settle, contract)` | 查询双向持仓 |
| `update_dual_mode_position_margin(settle, contract, change, dual_side)` | 调整双向持仓保证金 |
| `update_dual_mode_position_leverage(settle, contract, leverage)` | 调整双向持仓杠杆 |
| `update_dual_mode_position_risk_limit(settle, contract, risk_limit)` | 调整双向持仓风险限额 |

---

## 五、普通订单

| 方法 | 说明 |
|------|------|
| `list_futures_orders(settle, status)` | 查询订单列表 |
| `create_futures_order(settle, futures_order)` | 下单 |
| `cancel_futures_orders(settle)` | 批量撤销挂单 |
| `get_orders_with_time_range(settle)` | 按时间范围查询订单 |
| `create_batch_futures_order(settle, futures_order)` | 批量下单 |
| `get_futures_order(settle, order_id)` | 查询单个订单 |
| `amend_futures_order(settle, order_id, futures_order_amendment)` | 修改订单 |
| `cancel_futures_order(settle, order_id)` | 撤销单个订单 |
| `cancel_batch_future_orders(settle, request_body)` | 批量撤单（按 ID 列表） |
| `amend_batch_future_orders(settle, batch_amend_order_req)` | 批量修改订单 |
| `create_futures_bbo_order(settle, futures_bbo_order)` | 下 BBO（最优价）订单 |
| `countdown_cancel_all_futures(settle, countdown_cancel_all_futures_task)` | 倒计时全撤单（心跳保护） |

---

## 六、成交记录

| 方法 | 说明 |
|------|------|
| `get_my_trades(settle)` | 查询个人成交记录 |
| `get_my_trades_with_time_range(settle)` | 按时间范围查询成交记录 |

---

## 七、清算 / 强平 / 自动减仓

| 方法 | 说明 |
|------|------|
| `list_position_close(settle)` | 查询平仓记录 |
| `list_liquidates(settle)` | 查询个人强平记录 |
| `list_auto_deleverages(settle)` | 查询自动减仓（ADL）记录 |

---

## 八、追踪委托（Trail Order）

| 方法 | 说明 |
|------|------|
| `create_trail_order(settle, create_trail_order)` | 创建追踪委托 |
| `stop_trail_order(settle, stop_trail_order)` | 停止追踪委托 |
| `stop_all_trail_orders(settle, stop_all_trail_orders)` | 停止所有追踪委托 |
| `get_trail_orders(settle)` | 查询追踪委托列表 |
| `get_trail_order_detail(settle, id)` | 查询追踪委托详情 |
| `update_trail_order(settle, update_trail_order)` | 修改追踪委托 |
| `get_trail_order_change_log(settle, id)` | 查询追踪委托变更日志 |

---

## 九、价格触发委托（止盈止损条件单）

| 方法 | 说明 |
|------|------|
| `list_price_triggered_orders(settle, status)` | 查询条件单列表 |
| `create_price_triggered_order(settle, futures_price_triggered_order)` | 创建条件单 |
| `cancel_price_triggered_order_list(settle)` | 批量取消条件单 |
| `get_price_triggered_order(settle, order_id)` | 查询单个条件单 |
| `cancel_price_triggered_order(settle, order_id)` | 取消单个条件单 |
| `update_price_triggered_order(settle, order_id, futures_update_price_triggered_order)` | 修改条件单 |

---

## 参数说明

| 参数 | 说明 |
|------|------|
| `settle` | 结算货币，通常为 `"usdt"` 或 `"btc"` |
| `contract` | 合约名称，如 `"BTC_USDT"` |
| `status` | 订单状态，`"open"` / `"finished"` |
| `leverage` | 杠杆倍数，字符串类型，如 `"3"` |
| `dual_side` | 双向持仓方向，`"long"` / `"short"` |
