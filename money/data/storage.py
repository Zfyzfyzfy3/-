# !/usr/bin/env python
# coding: utf-8
"""
本地数据缓存模块
使用 CSV 缓存历史K线，避免重复请求API
"""
import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "../../cache")


class DataStorage:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, contract, interval):
        return os.path.join(self.cache_dir, f"{contract}_{interval}.csv")

    def save(self, df, contract, interval):
        path = self._path(contract, interval)
        df.to_csv(path)
        logger.info("saved %d bars to %s", len(df), path)

    def load(self, contract, interval):
        path = self._path(contract, interval)
        if not os.path.exists(path):
            return None
        df = pd.read_csv(path, index_col="timestamp", parse_dates=True)
        logger.info("loaded %d bars from %s", len(df), path)
        return df
