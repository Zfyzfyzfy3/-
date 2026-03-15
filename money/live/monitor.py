# !/usr/bin/env python
# coding: utf-8
"""
状态监控模块
定期打印账户状态、持仓、当日盈亏等信息
"""
import logging

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, futures_api, settle="usdt"):
        self.futures_api = futures_api
        self.settle = settle

    def print_account(self):
        try:
            acc = self.futures_api.list_futures_accounts(self.settle)
            logger.info("账户余额: available=%.4f total=%.4f unrealised_pnl=%.4f",
                        float(acc.available or 0),
                        float(acc.total or 0),
                        float(acc.unrealised_pnl or 0))
        except Exception as e:
            logger.error("monitor error: %s", e)

    def print_positions(self, contract=None):
        try:
            if contract:
                pos = self.futures_api.get_position(self.settle, contract)
                logger.info("持仓 %s: size=%s entry=%.4f unrealised=%.4f",
                            contract, pos.size,
                            float(pos.entry_price or 0),
                            float(pos.unrealised_pnl or 0))
            else:
                positions = self.futures_api.list_positions(self.settle)
                for pos in positions:
                    if pos.size != 0:
                        logger.info("持仓 %s: size=%s unrealised=%.4f",
                                    pos.contract, pos.size,
                                    float(pos.unrealised_pnl or 0))
        except Exception as e:
            logger.error("position monitor error: %s", e)
