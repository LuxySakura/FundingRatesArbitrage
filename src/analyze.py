"""
    该脚本用于分析获取到的资金费率数据
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.use('TkAgg')

HL_COMMISSTION_FEE = 0.0002  # Hyperliquid平台手续费率, 0.01%
OKX_COMMISION_FEE = 0.0004  # OKX平台手续费率，0.02%
BN_COMMISION_FEE = 0.00036  # Binance平台手续费率，0.018%
BYBIT_COMMISION_FEE = 0.00036  # Bybit平台手续费率，0.018%

if __name__ == '__main__':
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
