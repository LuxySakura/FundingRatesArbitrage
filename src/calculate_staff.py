import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from datetime import datetime, timedelta
from enum import Enum

matplotlib.use('TkAgg')

U_FUND = 5000  # 初始USDT资金量
# HL_COMMISSTION_FEE = 0.01  # Hyperliquid平台手续费率, 0.01%
# OKX_COMMISION_FEE = 0.02  # OKX平台手续费率，0.02%
# BN_COMMISION_FEE = 0.018  # Binance平台手续费率，0.018%
# BYBIT_COMMISION_FEE = 0.018  # Bybit平台手续费率，0.018%

class Platform(Enum):
    """
    交易平台枚举类型，包含平台名称和对应的手续费率
    """
    HYPERLIQUID = ("Hl", 0.0002)  # Hyperliquid平台手续费率, 0.01%
    OKX = ("Okx", 0.0004)  # OKX平台手续费率，0.02%
    BINANCE = ("Bin", 0.00036)  # Binance平台手续费率，0.018%
    BYBIT = ("Bybit", 0.00036)  # Bybit平台手续费率，0.018%
    UNKNOWN = ("", 0.0)
    
    def __init__(self, code, fee):
        self.code = code
        self.fee = fee
    
    @classmethod
    def from_string(cls, platform_str):
        """
        从字符串获取平台枚举值
        """
        for platform in cls:
            if platform.code == platform_str:
                return platform
        return cls.UNKNOWN
    
    @classmethod
    def get_lowest_fee_platform_with_valid_fr(cls, row_data, exclude_hl=True):
        """
        获取手续费最低且资金费率不为None的平台
        
        参数:
            row_data: DataFrame的一行数据
            exclude_hl: 是否排除Hyperliquid平台
        返回:
            Platform: 符合条件的平台枚举值
        """
        # 按手续费率排序所有平台（除UNKNOWN外和可选的Hl）
        sorted_platforms = sorted(
            [p for p in cls if p != cls.UNKNOWN and (not exclude_hl or p != cls.HYPERLIQUID)],
            key=lambda p: p.fee
        )
        
        # 遍历排序后的平台，找到第一个FR不为None的平台
        for platform in sorted_platforms:
            fr_column = f"{platform.code}FR"  # 构造FR列名
            if fr_column in row_data.index and pd.notna(row_data[fr_column]):
                return platform
        
        return cls.UNKNOWN


class TradingStrategy:
    """
    交易策略类：表示具体交易策略的相关信息
    属性：
        name: 
    """
    def __init__(self, platform=Platform.UNKNOWN, side=True, role=None):
        """
        初始化交易策略对象
        """
        self.platform = platform if isinstance(platform, Platform) else Platform.from_string(platform)
        self.side = side  # 开仓方向
        self.role = role  # 角色：套利方(arb)/对冲方(hedge)

    def strategyState(self):
        print("Platform:", self.platform.code, "===>")
        if self.role == True:
            if self.side:
                print("\tPosition Side: 做多(Long)\n\tRole: 套利方")
            else:
                print("\tPosition Side: 做空(Short)\n\tRole: 套利方")    
        else:
            if self.side:
                print("\tPosition Side: 做多(Long)\n\tRole: 对冲方")
            else:
                print("\tPosition Side: 做空(Short)\n\tRole: 对冲方") 


def create_trading_pair(platform1, platform2, fr1, fr2):
    """
    创建交易对，根据资金费率确定套利方和对冲方
    返回: (套利方TradingStrategy, 对冲方TradingStrategy)
    """
    # 将平台字符串转换为Platform枚举
    p1 = Platform.from_string(platform1)
    p2 = Platform.from_string(platform2)
    
    # 确定套利方向
    if fr1 * fr2 > 0:  # 资金费率同号
        # 选择绝对值大的作为套利方
        if abs(fr1) > abs(fr2):
            return TradingStrategy(p1, fr1 < 0, True), TradingStrategy(p2, not (fr1 < 0), False)
        else:
            return TradingStrategy(p2, fr2 < 0, False), TradingStrategy(p1, not (fr2 < 0), True)
    else:  # 资金费率异号
        # 负费率方做多，正费率方做空
        return (TradingStrategy(p1, True, True), TradingStrategy(p2, False, False)) if fr1 < 0 else (TradingStrategy(p2, True, True), TradingStrategy(p1, False, False))


def next_ft_filter(_row):
    """
    计算最优资金费率套利策略
    返回: 包含最大资金费率差、套利方和对冲方的Series对象
    """
    # 创建结果Series的辅助函数
    def make_result(max_fr=0.0, arb_obj=None, hedge_obj=None):
        return pd.Series({
            'maxFR': max_fr,
            'arb_obj': getattr(arb_obj, 'code', arb_obj),
            'hedge_obj': getattr(hedge_obj, 'code', hedge_obj)
        })
    
    # 检查必要数据
    if 'nextFT' not in _row or pd.isna(_row['nextFT']):
        return make_result()
    
    # 获取目标时间点
    target_ft = _row['nextFT']
    
    # 高效筛选有效平台
    valid_platforms = {}  # 使用字典存储平台及其资金费率
    
    # 一次遍历收集所有有效平台及其资金费率
    for col in _row.index:
        if col == 'nextFT' or _row[col] != target_ft:
            continue
            
        if col.endswith('FT'):
            platform = col[:-2]
            fr_col = f"{platform}FR"
            
            if fr_col in _row.index and pd.notna(_row[fr_col]):
                valid_platforms[platform] = _row[fr_col]
    
    # 处理无有效平台的情况
    if not valid_platforms:
        return make_result()
    
    # 单平台情况处理
    if len(valid_platforms) == 1:
        platform, fr_value = next(iter(valid_platforms.items()))
        # print("Hl FR:", fr_value)
        lowest_fee_platform = Platform.get_lowest_fee_platform_with_valid_fr(_row)
        
        if lowest_fee_platform == Platform.UNKNOWN:
            return make_result()
        
        # 创建交易策略
        arb_platform = Platform.from_string(platform)
        side = fr_value < 0
        arb_obj = TradingStrategy(arb_platform, side)
        hedge_obj = TradingStrategy(lowest_fee_platform, not side)
        
        # 计算净收益
        max_fr = 3*abs(fr_value) - arb_platform.fee - lowest_fee_platform.fee
        
        return make_result(max_fr, arb_platform, lowest_fee_platform)
    
    # 多平台情况处理 - 直接计算最优组合
    best_combo = None
    max_profit = 0
    
    # 使用列表推导式预先获取平台对象和费率，避免重复计算
    platform_data = [(p, fr, Platform.from_string(p).fee) for p, fr in valid_platforms.items()]
    
    # 计算所有可能的组合
    for i, (p1, fr1, fee1) in enumerate(platform_data):
        for p2, fr2, fee2 in platform_data[i+1:]:
            # 计算净收益
            fr_diff = 3*abs(fr1 - fr2)
            net_profit = fr_diff - fee1 - fee2
            
            if net_profit > max_profit:
                max_profit = net_profit
                best_combo = (p1, p2, fr1, fr2)
    
    # 无有效组合或收益为负
    if not best_combo or max_profit <= 0:
        return make_result()
    
    # 创建最优交易对
    p1, p2, fr1, fr2 = best_combo
    arb_obj, hedge_obj = create_trading_pair(p1, p2, fr1, fr2)
    
    return make_result(max_profit, arb_obj.platform, hedge_obj.platform)


def max_funding_rate(data):
    """
    输入：资金费率数据.csv
    输出：最优资金套利费率，套利方(Obj), 对冲方(Obj)
    计算资金费率的最大差值, 并输出对应的资金费套利策略
    """
    max_funding_rate = 0
    max_funding_rate_index = 0

    # 第一原则，筛选出当前时间最近的资金费率
    # 找出距离当前时间最近的时刻
    current_dt = datetime.now()
    next_hour = current_dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_hour_ms = int(next_hour.timestamp() * 1000)  # 下一整点时刻
    
    # Input: current ticker Record
    # Output: maxFR, maxFT
    # 将apply的结果直接添加到原DataFrame中
    result_df = data.apply(next_ft_filter, axis=1)
    
    # 方法2：或者直接将结果列添加到原始DataFrame
    data['maxFR'] = result_df['maxFR']
    data['arb_obj'] = result_df['arb_obj']
    data['hedge_obj'] = result_df['hedge_obj']
    
    # 找出最大资金费率的记录
    max_fr_idx = data['maxFR'].idxmax()
    print(data['maxFR'].describe())
    max_record = data.loc[max_fr_idx]
    print("Best Funding Rate Arbitrage:\n", max_record)
    _arb_platform = max_record['arb_obj']
    _hedge_platform = max_record['hedge_obj']
    _ticker = max_record['ticker']

    _arb_obj, _hedge_obj = create_trading_pair(_arb_platform, _hedge_platform, max_record[f'{_arb_platform}FR'], max_record[f'{_hedge_platform}FR'])
    
    # Print Arbitrage Strategy
    _arb_obj.strategyState()
    _hedge_obj.strategyState()
    return max_record['maxFR'], _arb_obj, _hedge_obj, _ticker


if __name__ == '__main__':
    file_path = './data/funding_data.csv'  # CSV 文件路径
    data = pd.read_csv(file_path)  # 读取数据

    # 计算最大资金费率以及具体套利策略
    max_fr, arb, hedge, ticker = max_funding_rate(data)
    max_fr = float(max_fr) * 100
    # 估算日利润率: max_fr * 日执行次数 * 资金杠杆
    estimate_day_rate = max_fr * 12 * 5

    print("Max Funding Rate:", max_fr, "From:", ticker)
    print("Estimated Max Funding Rate(Per Day):", estimate_day_rate, "%")
    print("Estimated Max Funding Rate(Per Year):", pow(1.033, 365), "%")
    print("Profit Per Day:", 7.3 * max_fr * U_FUND/100 * 30, "￥")

    # TODO: 计算时间，并执行交易
