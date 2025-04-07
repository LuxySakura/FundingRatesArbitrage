"""
调用子模块采集历史数据并进行合并
"""
from okx_history_fetch import okx_fetch_history_mark_price_candles, okx_fetch_history_funding_rates
from bin_history_fetch import bin_fetch_history_mark_price_candles, bin_fetch_history_funding_rates
from hl_history_fetch import hl_fetch_history_mark_price_candles, hl_fetch_history_funding_rates
from bybit_history_fetch import bybit_fetch_history_mark_price_candles, bybit_fetch_history_funding_rates
from sys import path as sys_path
from os import path as os_path
# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logger import setup_logger
from src.utils import genearate_history_moments


if __name__ == '__main__':
    days = 1  # 要收集的天数
    ticker = 'BTC'
    okx_symbol = 'BTC-USDT-SWAP'  # 要采集的symbol
    bin_symbol = 'BTCUSDT'  # 要采集的symbol
    bybit_symbol = 'BTCUSDT'  # 要采集的symbol
    
    # 生成
    k_history_segments = genearate_history_moments(interval=1, batch=60, days=days)
    fr_segments = genearate_history_moments(interval=60, batch=24, days=days)

    print("<=== OKX History Candles ====>")
    okx_fetch_history_mark_price_candles(symbol=okx_symbol, segments=k_history_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== Hyper Liquid History Candles ====>")
    hl_fetch_history_mark_price_candles(symbol=ticker, segments=k_history_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== Binance History Candles ====>")
    bin_fetch_history_mark_price_candles(symbol=bin_symbol, segments=k_history_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== Bybit History Candles ====>")
    bybit_fetch_history_mark_price_candles(symbol=bybit_symbol, segments=k_history_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== Binance History FR ====>")
    bin_fetch_history_funding_rates(symbol=bin_symbol, segments=fr_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== OKX History FR ====>")
    okx_fetch_history_funding_rates(symbol=okx_symbol, segments=k_history_segments, ticker=ticker)
    print("#=========================#\n")

    print("<==== Bybit History FR ====>")
    bybit_fetch_history_funding_rates(symbol=bybit_symbol, segments=fr_segments)
    print("#=========================#\n")

    print("<==== Hyper Liquid History FR ====>")
    hl_fetch_history_funding_rates(symbol=ticker, segments=fr_segments, ticker=ticker)
    print("#=========================#\n")