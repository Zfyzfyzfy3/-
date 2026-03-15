# !/usr/bin/env python
# coding: utf-8
"""
DataFetcher 集成测试（真实网络请求）
行情接口为公开接口，无需 API Key

运行方式：
    cd /home/dehuazhang12/codebase/quantTrading/money
    python -m pytest tests/data/test_fetcher.py -v
    python -m pytest tests/data/test_fetcher.py -v -k "Pagination"
    python -m pytest tests/data/test_fetcher.py::TestCandlestickChart -v -s # 会显示一个月的k线图
"""
import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

# ── 路径配置 ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../gateapi-python"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from data.fetcher import DataFetcher

CONTRACT = "BTC_USDT"
FETCHER  = DataFetcher(settle="usdt")   # 公开行情接口，不需要 key/secret

# 所有测试日期均在 2025-04 之后，确保在"近一年"窗口内
# 当前时间：2026-03-15，一年前截止：2025-03-15


# ─────────────────────────────────────────────────────────────────────
# 基础功能
# ─────────────────────────────────────────────────────────────────────
class TestFetchRangeBasic(unittest.TestCase):

    def test_columns_exist(self):
        """返回 DataFrame 包含必要列"""
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 6, 2, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertFalse(df.empty, "DataFrame 不应为空")
        for col in ("open", "high", "low", "close", "volume"):
            self.assertIn(col, df.columns, f"缺少列: {col}")

    def test_index_has_timezone(self):
        """index 应为 UTC 时区的 timestamp"""
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 6, 3, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertFalse(df.empty)
        self.assertIsNotNone(df.index.tzinfo, "index 应带时区信息")

    def test_data_within_requested_range(self):
        """所有 K 线时间戳应在 [start, end] 内"""
        start = datetime(2025, 7, 1,  tzinfo=timezone.utc)
        end   = datetime(2025, 7, 10, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="4h", start=start, end=end)
        self.assertFalse(df.empty)
        self.assertGreaterEqual(df.index.min(), start)
        self.assertLessEqual(df.index.max(), end)

    def test_no_duplicate_timestamps(self):
        """不应有重复时间戳"""
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 9, 1, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertFalse(df.empty)
        self.assertTrue(df.index.is_unique, "存在重复时间戳")

    def test_sorted_ascending(self):
        """数据应按时间升序排列"""
        start = datetime(2025, 8, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 8, 5, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertFalse(df.empty)
        self.assertTrue(df.index.is_monotonic_increasing, "数据未按时间升序")

    def test_price_sanity(self):
        """close > 0，high >= low，volume >= 0"""
        start = datetime(2025, 9, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 9, 2, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertFalse(df.empty)
        self.assertTrue((df["close"] > 0).all(),         "close 存在非正值")
        self.assertTrue((df["high"] >= df["low"]).all(),  "high < low 异常")
        self.assertTrue((df["volume"] >= 0).all(),        "volume 存在负值")


# ─────────────────────────────────────────────────────────────────────
# 不同 interval
# ─────────────────────────────────────────────────────────────────────
class TestFetchRangeIntervals(unittest.TestCase):

    def _check(self, interval, start, end, min_bars):
        df = FETCHER.fetch_range(CONTRACT, interval=interval, start=start, end=end)
        self.assertFalse(df.empty,          f"[{interval}] 返回空 DataFrame")
        self.assertTrue(df.index.is_unique, f"[{interval}] 存在重复时间戳")
        self.assertGreaterEqual(len(df), min_bars,
                                f"[{interval}] 返回 {len(df)} 根，少于预期 {min_bars}")
        return df

    def test_1m(self):
        """2小时 1m ≈ 120 根（1m 只允许近 ~6.9 天，使用近期日期）"""
        now   = datetime.now(timezone.utc)
        end   = now - timedelta(hours=2)
        start = end  - timedelta(hours=2)
        df = self._check("1m", start, end, min_bars=110)
        self.assertLessEqual(len(df), 125)

    def test_5m(self):
        """24小时 5m ≈ 288 根（5m 只允许近 ~34 天，使用近期日期）"""
        now   = datetime.now(timezone.utc)
        end   = now - timedelta(days=1)
        start = end  - timedelta(days=1)
        self._check("5m", start, end, min_bars=270)

    def test_1h(self):
        """7天 1h ≈ 168 根"""
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 6, 8, tzinfo=timezone.utc)
        self._check("1h", start, end, min_bars=160)

    def test_4h(self):
        """30天 4h ≈ 180 根"""
        start = datetime(2025, 7, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 8, 1, tzinfo=timezone.utc)
        self._check("4h", start, end, min_bars=170)

    def test_1d(self):
        """3个月 1d ≈ 90 根"""
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 9, 1, tzinfo=timezone.utc)
        self._check("1d", start, end, min_bars=85)

    def test_unsupported_interval_raises(self):
        """不支持的 interval 应抛出 ValueError"""
        with self.assertRaises(ValueError):
            FETCHER.fetch_range(CONTRACT, interval="3x")


# ─────────────────────────────────────────────────────────────────────
# 分页（> 2000 根，触发多次 API 请求）
# ─────────────────────────────────────────────────────────────────────
class TestPagination(unittest.TestCase):

    def test_3months_1h_exceeds_2000(self):
        """
        3 个月 1h ≈ 2160 根，超过单次上限 2000，必须触发分页；
        验证分页后数据连续、无重复。
        """
        start = datetime(2025, 6, 1, tzinfo=timezone.utc)
        end   = datetime(2025, 9, 1, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)

        self.assertFalse(df.empty)
        self.assertGreater(len(df), 2000,  "3个月1h数据应超过2000根")
        self.assertTrue(df.index.is_unique,               "分页后存在重复时间戳")
        self.assertTrue(df.index.is_monotonic_increasing,  "分页后数据不连续")

    def test_7days_5m_near_2000_boundary(self):
        """
        7天 5m ≈ 2016 根，刚好跨分页边界；
        5m 只允许近 ~34 天，使用近期日期。
        验证边界处无遗漏、无重复。
        """
        now   = datetime.now(timezone.utc)
        end   = now - timedelta(days=1)
        start = end  - timedelta(days=7)
        df = FETCHER.fetch_range(CONTRACT, interval="5m", start=start, end=end)

        self.assertFalse(df.empty)
        self.assertGreater(len(df), 1900)
        self.assertTrue(df.index.is_unique, "5m分页后存在重复时间戳")


# ─────────────────────────────────────────────────────────────────────
# fetch_month 便捷方法
# ─────────────────────────────────────────────────────────────────────
class TestFetchMonth(unittest.TestCase):

    def test_august_2025_bar_count(self):
        """8月31天，1h K线应在 [730, 745] 范围内"""
        df = FETCHER.fetch_month(CONTRACT, year=2025, month=8, interval="1h")
        self.assertFalse(df.empty)
        self.assertGreater(len(df), 720)
        self.assertLess(len(df), 750)

    def test_august_2025_time_boundary(self):
        """返回数据应在 8 月内（含边界时间戳）"""
        df = FETCHER.fetch_month(CONTRACT, year=2025, month=8, interval="1h")
        self.assertGreaterEqual(df.index.min(), datetime(2025, 8, 1, tzinfo=timezone.utc))
        self.assertLessEqual   (df.index.max(), datetime(2025, 9, 1, tzinfo=timezone.utc))

    def test_december_2025_crosses_year(self):
        """12月跨年边界应正确处理（含边界时间戳）"""
        df = FETCHER.fetch_month(CONTRACT, year=2025, month=12, interval="1d")
        self.assertFalse(df.empty)
        self.assertGreaterEqual(df.index.min(), datetime(2025, 12, 1, tzinfo=timezone.utc))
        self.assertLessEqual   (df.index.max(), datetime(2026, 1,  1, tzinfo=timezone.utc))

    def test_june_shorter_bar_count_than_august(self):
        """6月30天 K线数应少于8月31天"""
        df_jun = FETCHER.fetch_month(CONTRACT, year=2025, month=6, interval="1h")
        df_aug = FETCHER.fetch_month(CONTRACT, year=2025, month=8, interval="1h")
        self.assertLess(len(df_jun), len(df_aug), "6月 K线数量应少于8月")


# ─────────────────────────────────────────────────────────────────────
# 边界与保护机制
# ─────────────────────────────────────────────────────────────────────
class TestBoundaryProtection(unittest.TestCase):

    def test_start_too_early_clamped(self):
        """start 早于一年前应自动截断，不报错，仍有数据"""
        very_early = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime.now(timezone.utc) - timedelta(days=10)   # 10天前（肯定有数据）
        df = FETCHER.fetch_range(CONTRACT, interval="1d",
                                 start=very_early, end=end)
        self.assertFalse(df.empty, "截断后应仍有数据返回")

    def test_naive_datetime_treated_as_utc(self):
        """naive datetime 视为 UTC，不应报错"""
        df = FETCHER.fetch_range(CONTRACT, interval="1h",
                                 start=datetime(2025, 6, 1),   # no tzinfo
                                 end=datetime(2025, 6, 3))
        self.assertFalse(df.empty)

    def test_empty_result_when_start_after_end(self):
        """start > end 应返回空 DataFrame"""
        start = datetime(2025, 9, 10, tzinfo=timezone.utc)
        end   = datetime(2025, 9,  1, tzinfo=timezone.utc)
        df = FETCHER.fetch_range(CONTRACT, interval="1h", start=start, end=end)
        self.assertTrue(df.empty, "start > end 应返回空 DataFrame")


# ─────────────────────────────────────────────────────────────────────
# fetch_ticker 实时行情
# ─────────────────────────────────────────────────────────────────────
class TestFetchTicker(unittest.TestCase):

    def test_ticker_not_none(self):
        ticker = FETCHER.fetch_ticker(CONTRACT)
        self.assertIsNotNone(ticker, "Ticker 不应为 None")

    def test_ticker_last_price_positive(self):
        ticker = FETCHER.fetch_ticker(CONTRACT)
        self.assertIsNotNone(ticker)
        self.assertGreater(float(ticker.last), 0, "最新价应大于 0")
        print(f"\n  [BTC_USDT 最新价] {ticker.last}")

    def test_ticker_invalid_contract_returns_none(self):
        """无效合约 fetch_ticker 应返回 None，不抛出异常"""
        ticker = FETCHER.fetch_ticker("INVALID_XYZ_999")
        self.assertIsNone(ticker, "无效合约应返回 None")


# ─────────────────────────────────────────────────────────────────────
# 终端 K 线图可视化（月K图）
# ─────────────────────────────────────────────────────────────────────
class TestCandlestickChart(unittest.TestCase):

    def test_print_monthly_candlestick_chart(self):
        """
        拉取近一个月 1d K 线，用 plotext 在终端画出蜡烛图。
        此测试始终 pass，图表打印到 stdout。
        """
        import plotext as plt

        now   = datetime.now(timezone.utc)
        end   = now
        start = now - timedelta(days=30)
        df = FETCHER.fetch_range(CONTRACT, interval="1d", start=start, end=end)
        self.assertFalse(df.empty, "无法获取K线数据")

        dates  = [str(ts.date()) for ts in df.index]
        opens  = df["open"].tolist()
        highs  = df["high"].tolist()
        lows   = df["low"].tolist()
        closes = df["close"].tolist()

        plt.clf()
        plt.theme("dark")
        plt.plot_size(width=100, height=30)
        plt.date_form("Y-m-d")             # plotext 格式：不加 %，内部自动转换
        data = {
            "Open":  opens,
            "High":  highs,
            "Low":   lows,
            "Close": closes,
        }
        plt.candlestick(dates, data)
        plt.title(f"BTC_USDT 近30天日K线  ({dates[0]} → {dates[-1]})")
        plt.xlabel("日期")
        plt.ylabel("价格 (USDT)")
        print()   # 换行让图表与 pytest 输出分开
        plt.show()

        # 基本数据完整性校验
        self.assertEqual(len(opens), len(closes))
        self.assertTrue(all(h >= l for h, l in zip(highs, lows)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
