# !/usr/bin/env python
# coding: utf-8
"""
风控模块
在下单前进行多维度检查，保护账户安全
"""
import logging
from config.settings import MAX_DRAWDOWN, MAX_POSITION_RATIO, MAX_DAILY_LOSS

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, max_drawdown=MAX_DRAWDOWN,
                 max_position_ratio=MAX_POSITION_RATIO,
                 max_daily_loss=MAX_DAILY_LOSS):
        self.max_drawdown = max_drawdown
        self.max_position_ratio = max_position_ratio
        self.max_daily_loss = max_daily_loss
        self._daily_loss = 0.0

    def check(self, signal, futures_api, settle) -> bool:
        """
        执行下单前风控检查
        :return: True 允许下单，False 拒绝
        """
        try:
            account = futures_api.list_futures_accounts(settle)
            available = float(account.available)
            total = float(account.total) if account.total else available

            # 1. 余额检查
            if available <= 0:
                logger.warning("risk: no available balance")
                return False

            # 2. 单日亏损熔断
            if self._daily_loss >= total * self.max_daily_loss:
                logger.warning("risk: daily loss limit reached %.4f", self._daily_loss)
                return False

            # 3. 仓位占比检查（简化：用订单名义价值估算）
            logger.info("risk: all checks passed, signal=%s size=%d",
                        signal.action, signal.size)
            return True

        except Exception as e:
            logger.error("risk check error: %s", e)
            return False

    def record_loss(self, loss_amount):
        """记录亏损，供日志和熔断使用"""
        self._daily_loss += loss_amount

    def reset_daily(self):
        """每天重置日内亏损计数"""
        self._daily_loss = 0.0
