"""
    该脚本用于分析获取到的资金费率数据
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from datetime import datetime

matplotlib.use('TkAgg')

HL_COMMISSTION_FEE = 0.0002  # Hyperliquid平台手续费率, 0.01%
OKX_COMMISION_FEE = 0.0004  # OKX平台手续费率，0.02%
BN_COMMISION_FEE = 0.00036  # Binance平台手续费率，0.018%
BYBIT_COMMISION_FEE = 0.00036  # Bybit平台手续费率，0.018%


def max_analyze_funding_rate():
    """
    分析资金费率数据
    """
    file_path = './data/funding_data.csv'  # CSV 文件路径
    data = pd.read_csv(file_path)  # 读取数据

    # 处理空值，将NaN替换为0
    data['BinFR'] = data['BinFR'].fillna(0)
    data['OkxFR'] = data['OkxFR'].fillna(0)
    data['BybitFR'] = data['BybitFR'].fillna(0)
    data['HlFR'] = data['HlFR'].fillna(0)
    
    # 计算每四小时的资金套利费率（取绝对值）
    data['bin_Arb_FR'] = abs(data['BinFR'] - data['HlFR']) - HL_COMMISSTION_FEE - BN_COMMISION_FEE
    data['bybit_Arb_FR'] = abs(data['BybitFR'] - data['HlFR']) - HL_COMMISSTION_FEE - BYBIT_COMMISION_FEE
    data['okx_Arb_FR'] = abs(data['OkxFR'] - data['HlFR']) - HL_COMMISSTION_FEE - OKX_COMMISION_FEE
    
    # 计算三个套利费率中的最大值
    data['max_Arb_FR'] = data[['bin_Arb_FR', 'bybit_Arb_FR', 'okx_Arb_FR']].max(axis=1)
    
    # 找出具有最大套利差值的记录
    max_arb_record = data.loc[data['max_Arb_FR'].idxmax()]
    
    print("最大套利差值记录:")
    print(max_arb_record)
    print(f"最大套利差值: {max_arb_record['max_Arb_FR']}")
    
    # 确定最大套利差值来自哪个交易所对
    max_pair = ""
    if max_arb_record['max_Arb_FR'] == max_arb_record['bin_Arb_FR']:
        max_pair = "Binance-Hyperliquid"
    elif max_arb_record['max_Arb_FR'] == max_arb_record['bybit_Arb_FR']:
        max_pair = "Bybit-Hyperliquid"
    elif max_arb_record['max_Arb_FR'] == max_arb_record['okx_Arb_FR']:
        max_pair = "OKX-Hyperliquid"
    
    print(f"最大套利差值来自交易所对: {max_pair}")


def analyze_unmatched_timestamp():
    """
    该函数用于分析收集的历史数据集中在相同时间Segments下不匹配的时间戳
    """
    okx_file_path = './data/candles/okx_BTC_USDT_SWAP_1m.csv'  # OKX 资金费率数据文件路径
    bin_file_path = './data/candles/bin_BTCUSDT_1m.csv'  # Binance 资金费率数据文件路径
    hl_file_path = './data/candles/hl_BTC_1m.csv'  # Hyperliquid 资金费率数据文件路径

    # 读取三个CSV文件
    okx_data = pd.read_csv(okx_file_path)
    bin_data = pd.read_csv(bin_file_path)
    hl_data = pd.read_csv(hl_file_path)
    
    # 提取每个文件的时间戳列
    okx_timestamps = set(okx_data['timestamp'])
    bin_timestamps = set(bin_data['timestamp'])
    hl_timestamps = set(hl_data['timestamp'])

    print("okx 共有记录数：", len(okx_timestamps))
    print("bin 共有记录数：", len(bin_timestamps))
    print("hl 共有记录数：", len(hl_timestamps))
    
    # 找出每个交易所独有的时间戳
    okx_unique = hl_timestamps.union(okx_timestamps) - okx_timestamps
    bin_unique = bin_timestamps - (okx_timestamps.union(hl_timestamps))
    hl_unique = hl_timestamps.union(bin_timestamps) - bin_timestamps
    
    # 打印结果
    print(f"OKX独有的时间戳数量: {len(okx_unique)}")
    if len(okx_unique) > 0:
        print("OKX独有时间戳示例:")
        for ts in list(okx_unique):
            print(f"  - {datetime.fromtimestamp(ts / 1000.0)}")
    else:
        print("OKX没有独有的时间戳。")
    
    print(f"\nBinance独有的时间戳数量: {len(bin_unique)}")
    if len(bin_unique) > 0:
        print("Binance独有时间戳示例:")
        for ts in list(bin_unique):
            print(f"  - {datetime.fromtimestamp(ts / 1000.0)}")
    else:
        print("Binance没有独有的时间戳。")

    
    print(f"\nHyperliquid独有的时间戳数量: {len(hl_unique)}")
    if len(hl_unique) > 0:
        print("Hyperliquid独有时间戳示例(最多显示5个):")
        for ts in list(hl_unique):
            print(f"  - {datetime.fromtimestamp(ts / 1000.0)}")
    else:
        print("Hyperliquid没有独有的时间戳。")
    
    # 计算总体统计信息
    total_unique_timestamps = len(okx_timestamps.union(bin_timestamps).union(hl_timestamps))
    common_timestamps = len(okx_timestamps.intersection(bin_timestamps).intersection(hl_timestamps))
    
    print(f"\n总计唯一时间戳数量: {total_unique_timestamps}")
    print(f"三个交易所共有的时间戳数量: {common_timestamps}")
    print(f"不匹配的时间戳占比: {(total_unique_timestamps - common_timestamps) / total_unique_timestamps:.2%}")


if __name__ == '__main__':
    analyze_unmatched_timestamp()
