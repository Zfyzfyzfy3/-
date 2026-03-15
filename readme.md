# 全年回测
python main.py backtest

# 指定月份回测
python main.py backtest --start 2024-03-01 --end 2024-03-31

# 实盘
python main.py live

# 开发流程
cd gateapi-python 然后 pip install --user gate-api
然后在money目录下开发，docs下放的是一些文档

# 测试
python -m pytest tests/data/test_fetcher.py -v
python -m pytest tests/data/test_fetcher.py -v -k "Pagination"
python -m pytest tests/data/test_fetcher.py::TestCandlestickChart -v -s # 会显示一个月的k线图