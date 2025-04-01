"""
OKX 历史数据获取脚本
"""
import requests
import json
import pandas as pd
import os
import time
from datetime import datetime
from collections import deque
from sys import path as sys_path
from os import path as os_path

# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logger import setup_logger
from src.utils import genearate_history_moments

# 获取logger实例
logger = setup_logger('HistoryDataFetching')

BASE_URL = "https://www.okx.com"

# 流动性数据
# - timestamp
# - side (bid & ask)
# - price 
# - volume

# 资金费率数据
# - timestamp
# - funding_rate
def fetch_histroy_funding_rates(symbol, save_to_csv=True, csv_dir=None):
    """
    获取历史资金费率数据并与K线数据合并
    
    参数:
        symbol: 交易对，如'BTC-USDT-SWAP'
        save_to_csv: 是否保存到CSV文件
        csv_dir: CSV文件保存目录，默认为项目根目录下的data/candles目录
    
    返回:
        合并了资金费率的K线数据
    """
    segments = genearate_history_moments(interval=60, batch=24, days=7)

    # 设置CSV文件保存路径
    if csv_dir is None:
        # 默认保存到项目根目录下的data/candles目录
        csv_dir = os.path.join(os_path.dirname(os_path.dirname(os_path.dirname(__file__))), 'data', 'candles')
    
    # 确保目录存在
    os.makedirs(csv_dir, exist_ok=True)
    
    # CSV文件名：symbol_1m.csv
    csv_filename = f"{symbol.replace('-', '_')}_1m.csv"
    csv_path = os.path.join(csv_dir, csv_filename)
    
    # 读取现有K线CSV文件(如果存在)
    candle_data = None
    if os.path.exists(csv_path):
        try:
            candle_data = pd.read_csv(csv_path)
            logger.info(f"读取现有K线CSV文件: {csv_path}, 包含 {len(candle_data)} 条记录")
            # 确保datetime列存在
            if 'datetime' not in candle_data.columns:
                candle_data['datetime'] = pd.to_datetime(candle_data['timestamp'], unit='ms')
        except Exception as e:
            logger.error(f"读取CSV文件失败: {str(e)}")
            return None
    else:
        logger.error(f"K线数据文件不存在: {csv_path}，请先运行fetch_history_mark_price_candles获取K线数据")
        return None

    # GET /api/v5/public/funding-rate-history
    method = 'GET'
    request_path = '/api/v5/public/funding-rate-history'
    url = BASE_URL + request_path
    
    funding_rates_data = []  # 存储所有资金费率数据
    
    # 实现限速控制 - 使用滑动窗口跟踪最近的请求时间
    request_times = deque(maxlen=20)  # 最多保存20个请求时间
    
    for i in range(len(segments) - 1):
        start = segments[i][0]
        end = segments[i][1]
        body = {
            'instId': symbol,
            'after': end,
            'before': start,
            'limit': '24',
        }
        logger.info(f"获取时间段数据: start={datetime.fromtimestamp(start / 1000.0)}, end={datetime.fromtimestamp(end / 1000.0)}")
        
        # 限速控制 - 如果已经有20个请求在最近2秒内发出，则等待
        current_time = time.time()
        if len(request_times) == 20:
            oldest_request_time = request_times[0]
            time_diff = current_time - oldest_request_time
            if time_diff < 2.0:
                # 需要等待的时间
                wait_time = 2.0 - time_diff + 0.05  # 额外增加50ms的缓冲
                logger.info(f"达到限速阈值，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                current_time = time.time()  # 更新当前时间
        
        # 记录本次请求时间
        request_times.append(current_time)
        
        # 发送请求
        try:
            res = requests.get(
                url,
                params=body,
                timeout=10  # 设置超时时间
            )
            
            if res.status_code == 200:
                msg = res.json()
                data = msg['data']
                # realizedRate 实际资金费率
                # method: current_period/next_period(当期收/跨期收)
               
                if data and len(data) > 0:
                    # 将数据添加到列表中
                    for item in data:
                        funding_rates_data.append({
                            'timestamp': int(item['fundingTime']),
                            'funding_rate': float(item['realizedRate'])
                        })
                        logger.info(f"资金费时间: {datetime.fromtimestamp(int(item['fundingTime']) / 1000.0)}")
                    logger.info(f"获取到 {len(data)} 条资金费率数据")
                else:
                    logger.warning(f"该时间段未获取到数据")
            else:
                # 如果是429错误(Too Many Requests)，增加等待时间
                if res.status_code == 429:
                    logger.warning("收到限速响应，等待5秒后继续")
                    time.sleep(5)
                    i -= 1  # 重试当前请求
                    continue
                logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        except Exception as e:
            logger.error(f"请求异常: {str(e)}")
            # 出现异常时等待一段时间后重试
            time.sleep(2)
            i -= 1  # 重试当前请求
            continue
    
    # 如果获取到了资金费率数据
    if funding_rates_data:
        # 将资金费率数据转换为DataFrame
        funding_df = pd.DataFrame(funding_rates_data)
        
        # 将timestamp转换为datetime格式，方便排序和查看
        funding_df['datetime'] = pd.to_datetime(funding_df['timestamp'], unit='ms')
        
        logger.info(f"共获取到 {len(funding_df)} 条资金费率记录")
        
        # 合并资金费率数据到K线数据
        # 1. 如果K线数据中已有funding_rate列，先删除
        if 'okxFR' in candle_data.columns:
            candle_data = candle_data.drop('okxFR', axis=1)
        
        # 2. 创建一个新的DataFrame，用于存储合并后的数据
        merged_df = candle_data.copy()
        
        # 3. 初始化funding_rate列为NaN
        merged_df['okxFR'] = float('nan')
        
        # 4. 对于每个资金费率记录，找到对应时间戳的K线数据并更新
        for _, row in funding_df.iterrows():
            # 精确匹配时间戳
            matching_indices = merged_df[merged_df['timestamp'] == row['timestamp']].index
            
            if len(matching_indices) > 0:
                # 更新对应K线的资金费率
                merged_df.loc[matching_indices, 'okxFR'] = row['funding_rate']
                logger.info(f"精确匹配时间戳 {row['datetime']} 的资金费率: {row['funding_rate']}")
            else:
                logger.warning(f"未找到精确匹配的时间戳 {row['datetime']} 对应的K线数据")
        
        # 5. 不再进行前向填充，因为需要精确匹配时间戳
        # 删除所有funding_rate为NaN的行（可选，根据需求决定）
        # merged_df = merged_df.dropna(subset=['funding_rate'])
        
        logger.info(f"合并后共有 {len(merged_df)} 条记录，其中 {merged_df['funding_rate'].notna().sum()} 条有精确匹配的资金费率数据")
        
        # 保存到CSV
        if save_to_csv:
            merged_df.to_csv(csv_path, index=False)
            logger.info(f"合并后的数据已保存到: {csv_path}")
        
        return merged_df
    else:
        logger.warning("未获取到任何资金费率数据")
        return candle_data


def fetch_history_mark_price_candles(symbol, save_to_csv=True, csv_dir=None):
    """
    获取历史mark price数据并保存到CSV文件
    
    参数:
        symbol: 交易对，如'BTC-USDT-SWAP'
        save_to_csv: 是否保存到CSV文件
        csv_dir: CSV文件保存目录，默认为项目根目录下的data/candles目录
    
    返回:
        最新获取的K线数据
    """
    
    # 首先获取要进行获取的时间戳集合
    segments = genearate_history_moments(interval=1, batch=60, days=1)
    
    # 设置CSV文件保存路径
    if csv_dir is None:
        # 默认保存到项目根目录下的data/candles目录
        csv_dir = os.path.join(os_path.dirname(os_path.dirname(os_path.dirname(__file__))), 'data', 'candles')
    
    # 确保目录存在
    os.makedirs(csv_dir, exist_ok=True)
    
    # CSV文件名：symbol_1m.csv
    csv_filename = f"{symbol.replace('-', '_')}_1m.csv"
    csv_path = os.path.join(csv_dir, csv_filename)
    
    # 定义列名
    columns = ['timestamp', 'okxOpen', 'okxHigh', 'okxLow', 'okxClose', 'okxVolume', 'okxVolCcy', 'okxVolCcyQuote', 'confirm']
    
    # 读取现有CSV文件(如果存在)
    existing_data = None
    if os.path.exists(csv_path):
        try:
            existing_data = pd.read_csv(csv_path)
            logger.info(f"读取现有CSV文件: {csv_path}, 包含 {len(existing_data)} 条记录")
        except Exception as e:
            logger.error(f"读取CSV文件失败: {str(e)}")
    
    # GET /api/v5/market/history-mark-price-candles
    method = 'GET'
    request_path = '/api/v5/market/history-candles'
    url = BASE_URL + request_path
    
    all_new_data = []  # 存储所有新获取的数据
    
    # 实现限速控制 - 使用滑动窗口跟踪最近的请求时间
    request_times = deque(maxlen=20)  # 最多保存20个请求时间
    
    for i in range(len(segments) - 1):
        start = segments[i][0]
        end = segments[i][1]
        body = {
            'instId': symbol,
            'after': end,
            'before': start,
            'bar': '1m',
            'limit': '60',
        }
        logger.info(f"获取时间段数据: start={datetime.fromtimestamp(start / 1000.0)}, end={datetime.fromtimestamp(end / 1000.0)}")
        
        # 限速控制 - 如果已经有20个请求在最近2秒内发出，则等待
        current_time = time.time()
        if len(request_times) == 20:
            oldest_request_time = request_times[0]
            time_diff = current_time - oldest_request_time
            if time_diff < 2.0:
                # 需要等待的时间
                wait_time = 2.0 - time_diff + 0.05  # 额外增加50ms的缓冲
                logger.info(f"达到限速阈值，等待 {wait_time:.2f} 秒")
                time.sleep(wait_time)
                current_time = time.time()  # 更新当前时间
        
        # 记录本次请求时间
        request_times.append(current_time)
        
        # 发送请求
        try:
            res = requests.get(
                url,
                params=body,
                timeout=10  # 设置超时时间
            )
            
            if res.status_code == 200:
                msg = res.json()
                data = msg['data']
                # 返回数组顺序：[ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm]
                
                if data and len(data) > 0:
                    # 将数据添加到列表中，同时转换timestamp为int类型
                    for item in data:
                        item[0] = int(item[0])  # 转换timestamp列为int
                    all_new_data.extend(data)
                    logger.info(f"获取到 {len(data)} 条K线数据")
                else:
                    logger.warning(f"该时间段未获取到数据: start={start}, end={end}")
            else:
                # 如果是429错误(Too Many Requests)，增加等待时间
                if res.status_code == 429:
                    logger.warning("收到限速响应，等待5秒后继续")
                    time.sleep(5)
                    i -= 1  # 重试当前请求
                    continue
                logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        except Exception as e:
            logger.error(f"请求异常: {str(e)}")
            # 出现异常时等待一段时间后重试
            time.sleep(2)
            i -= 1  # 重试当前请求
            continue
    
    # 如果获取到了新数据
    if all_new_data:
        # 将新数据转换为DataFrame
        new_df = pd.DataFrame(all_new_data, columns=columns)
        
        # 将timestamp转换为datetime格式，方便排序和查看
        new_df['datetime'] = pd.to_datetime(new_df['timestamp'], unit='ms')
        
        # 如果存在现有数据，合并新旧数据
        if existing_data is not None:
            # 确保现有数据也有datetime列
            if 'datetime' not in existing_data.columns:
                existing_data['datetime'] = pd.to_datetime(existing_data['timestamp'], unit='ms')
            
            # 合并数据
            combined_df = pd.concat([existing_data, new_df])
            
            # 删除重复数据（基于timestamp）
            combined_df = combined_df.drop_duplicates(subset=['timestamp'])
            
            # 按时间排序
            combined_df = combined_df.sort_values('timestamp')
            
            # 重置索引
            combined_df = combined_df.reset_index(drop=True)
            
            logger.info(f"合并后共有 {len(combined_df)} 条记录")
            
            # 保存到CSV
            if save_to_csv:
                combined_df.to_csv(csv_path, index=False)
                logger.info(f"数据已保存到: {csv_path}")
            
            return combined_df
        else:
            # 如果没有现有数据，直接保存新数据
            # 按时间排序
            new_df = new_df.sort_values('timestamp')
            
            # 重置索引
            new_df = new_df.reset_index(drop=True)
            
            logger.info(f"共获取到 {len(new_df)} 条新记录")
            
            # 保存到CSV
            if save_to_csv:
                new_df.to_csv(csv_path, index=False)
                logger.info(f"数据已保存到: {csv_path}")
            
            return new_df
    else:
        logger.warning("未获取到任何新数据")
        return existing_data if existing_data is not None else pd.DataFrame(columns=columns)


if __name__ == '__main__':
    print("开始采集数据")
    # fetch_history_mark_price_candles('BTC-USDT-SWAP')
    fetch_histroy_funding_rates("BTC-USDT-SWAP")