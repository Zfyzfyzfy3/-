# !/usr/bin/env python
# coding: utf-8
"""
补齐 1h 历史数据到最新（建议每日或每周执行）

用法：
  python money/tools/refresh_1h_cache.py
  python money/tools/refresh_1h_cache.py --config money/config/strategy_config.yaml
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import yaml

# gate_api 包位于 gateapi-python/ 目录下，加入模块搜索路径
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "..", "gateapi-python"))

from data.fetcher import DataFetcher  # noqa: E402
from data.storage import DataStorage  # noqa: E402


def _load_config(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description="Refresh 1h cache to latest")
    parser.add_argument("--config", default=os.path.join(ROOT, "config", "strategy_config.yaml"))
    parser.add_argument("--contract", default=None)
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    cfg = _load_config(args.config)
    api = cfg.get("api", {})
    market = cfg.get("market", {})

    contract = args.contract or market.get("contract", "BTC_USDT")
    api_key = api.get("key", "")
    api_secret = api.get("secret", "")
    api_host = api.get("host", "https://api.gateio.ws/api/v4")

    if not api_key or not api_secret:
        raise ValueError("缺少 API 凭证: 请在配置文件中填写 api.key 和 api.secret")

    storage = DataStorage()
    fetcher = DataFetcher(api_key, api_secret, api_host)

    df = storage.load(contract, "1h")
    now = datetime.now(timezone.utc)

    if df is None or df.empty:
        start = now - timedelta(days=365)
        logger.info("本地无 1h 缓存，从近一年开始拉取")
    else:
        last_ts = df.index.max()
        start = last_ts + timedelta(hours=1)
        logger.info("本地最后一根 1h: %s", last_ts)

    end = now
    if start >= end:
        logger.info("1h 数据已是最新，无需补齐")
        return

    logger.info("补齐区间: %s → %s", start, end)
    patch = fetcher.fetch_range(contract, interval="1h", start=start, end=end)
    if patch.empty:
        logger.warning("未拉到新数据")
        return

    if df is None or df.empty:
        df = patch
    else:
        df = pd.concat([df.sort_index(), patch.sort_index()]).sort_index()
        df = df[~df.index.duplicated(keep="last")]

    storage.save(df, contract, "1h")
    logger.info("补齐完成，当前 1h 总条数: %d", len(df))


if __name__ == "__main__":
    main()
