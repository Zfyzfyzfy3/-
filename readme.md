# 全年回测
python main.py backtest

# 默认全年回测（MA5/20），结束自动打印报告
python main.py backtest

# 指定时间段
python main.py backtest --start 2025-06-01 --end 2025-09-01

# 指定策略参数
python main.py backtest --strategy ma_cross --fast 10 --slow 30 --order-size 5

# 只做多 + 自定义时间段
python main.py backtest --start 2025-06-01 --end 2025-09-01 --only-long

# 强制重拉数据
python main.py backtest --no-cache

# 实盘（同样支持策略参数）
python main.py live --strategy ma_cross --fast 5 --slow 20

# 实盘
python main.py live

# 开发流程
cd gateapi-python 然后 pip install --user gate-api
然后在money目录下开发，docs下放的是一些文档

# 测试
python -m pytest tests/data/test_fetcher.py -v
python -m pytest tests/data/test_fetcher.py -v -k "Pagination"
python -m pytest tests/data/test_fetcher.py::TestCandlestickChart -v -s # 会显示一个月的k线图