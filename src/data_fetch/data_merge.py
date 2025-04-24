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
import pandas as pd
import os

logger = setup_logger('data_merge')

def merge_exchange_data(ticker, flag):
    """
    合并四个交易所的数据文件
    
    Args:
        ticker (str): 交易对标识，如'BTC'
        flag (bool): 是否为资金费率数据（True）或历史K线数据（False）
    
    Returns:
        bool: 合并是否成功
    """
    try:
        # 定义四个交易所的文件路径
        if flag:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os_path.dirname(__file__))), "data/fundingRates")
            okx_file = os.path.join(data_dir, f"okx_{ticker}_fr.csv")
            bin_file = os.path.join(data_dir, f"bin_{ticker}_fr.csv")
            hl_file = os.path.join(data_dir, f"hl_{ticker}_fr.csv")
            bybit_file = os.path.join(data_dir, f"bybit_{ticker}_fr.csv")
            output_path = os.path.join(data_dir, f"{ticker}_fr.csv")  # 保存路径
        else:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os_path.dirname(__file__))), "data/candles")
            okx_file = os.path.join(data_dir, f"okx_{ticker}_1m.csv")
            bin_file = os.path.join(data_dir, f"bin_{ticker}_1m.csv")
            hl_file = os.path.join(data_dir, f"hl_{ticker}_1m.csv")
            bybit_file = os.path.join(data_dir, f"bybit_{ticker}_1m.csv")
            output_path = os.path.join(data_dir, f"{ticker}_candles.csv")
        
        # 检查文件是否存在
        files = [hl_file, bin_file, okx_file, bybit_file]
        exchanges = ['hl', 'bin', 'okx', 'bybit']
        
        dfs = []
        for i, file_path in enumerate(files):
            if os.path.exists(file_path):
                try:
                    # 读取CSV文件
                    df = pd.read_csv(file_path)
                    
                    # 确保timestamp列存在
                    if 'timestamp' not in df.columns:
                        logger.warning(f"文件 {file_path} 中没有timestamp列，跳过")
                        continue
                    
                    dfs.append(df)
                    logger.info(f"成功读取 {file_path}")
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {e}")
            else:
                logger.warning(f"文件不存在: {file_path}")
        
        if not dfs:
            logger.warning("没有有效的数据可以合并")
            return False
        
        # 按timestamp合并所有数据框
        merged_df = dfs[0]
        for i, df in enumerate(dfs[1:]):
            # 如果不是第一个数据框且包含datetime列，则在合并前删除
            if 'datetime' in df.columns and 'datetime' in merged_df.columns:
                df = df.drop(columns=['datetime'])
                logger.info(f"从 {exchanges[i+1]} 数据中删除重复的datetime列")
            
            merged_df = pd.merge(merged_df, df, on='timestamp', how='outer')
        
        # 按timestamp排序
        merged_df = merged_df.sort_values('timestamp')
        
        # 去除首尾数据
        if len(merged_df) > 2:  # 确保数据框至少有3行，才能去除首尾
            merged_df = merged_df.iloc[1:-1]
            logger.info(f"已去除首尾数据，剩余数据行数: {len(merged_df)}")
        else:
            logger.warning(f"数据行数不足，无法去除首尾数据，当前行数: {len(merged_df)}")
        
        # 保存合并后的数据
        merged_df.to_csv(output_path, index=False)
        logger.info(f"合并数据已保存至: {output_path}")
        
        # 删除原始数据文件
        for file_path in files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"已删除原始数据文件: {file_path}")
                except Exception as e:
                    logger.warning(f"删除文件 {file_path} 时出错: {e}")
        
        return True
    
    except Exception as e:
        logger.error(f"合并数据时发生错误: {e}")
        return False


def fetch_ticker_data(ticker, k_segments, fr_segments):
    """
    从四个交易所获取历史数据

    Args:
        ticker (str): 交易对标识，如'BTC'
        k_segments (list): K线数据的时间段
        fr_segments (list): 资金费率数据的时间段

    Returns:
        bool: 数据获取是否成功
    """
    # 定义四个交易所的symbol
    okx_symbol = f'{ticker}-USDT-SWAP'  # OKX symbol
    bin_symbol = f'{ticker}USDT'  # Binance symbol
    bybit_symbol = f'{ticker}USDT'  # 要采集的symbol

    # 获取历史K线数据
    okx_fetch_history_mark_price_candles(symbol=okx_symbol, segments=k_history_segments, ticker=ticker)
    hl_fetch_history_mark_price_candles(symbol=ticker, segments=k_history_segments, ticker=ticker)
    bin_fetch_history_mark_price_candles(symbol=bin_symbol, segments=k_history_segments, ticker=ticker)
    bybit_fetch_history_mark_price_candles(symbol=bybit_symbol, segments=k_history_segments, ticker=ticker)
   
    # # 获取历史资金费率数据
    bin_fetch_history_funding_rates(symbol=bin_symbol, segments=fr_segments, ticker=ticker)
    okx_fetch_history_funding_rates(symbol=okx_symbol, segments=fr_segments, ticker=ticker)
    bybit_fetch_history_funding_rates(symbol=bybit_symbol, segments=fr_segments, ticker=ticker)
    hl_fetch_history_funding_rates(symbol=ticker, segments=fr_segments, ticker=ticker)

    # 合并数据
    merge_exchange_data(ticker, True)
    merge_exchange_data(ticker, False)


if __name__ == '__main__':
    days = 1  # 要收集的天数
    
    # 读取CSV文件中的ticker列
    try:
        # 定义CSV文件路径
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data/funding_data.csv")
        
        if os.path.exists(csv_path):
            # 读取CSV文件
            tickers_df = pd.read_csv(csv_path)
            
            # 检查是否存在ticker列
            if 'ticker' in tickers_df.columns:
                tickers = tickers_df['ticker'].unique().tolist()
                logger.info(f"从CSV文件中读取到{len(tickers)}个ticker: {tickers}")
                
                # 为每个ticker生成时间段
                k_history_segments = genearate_history_moments(interval=1, batch=60, days=days)  # K线数据的时间段
                fr_segments = genearate_history_moments(interval=60, batch=24, days=days)  # 资金费率数据的时间段
                
                # 为每个ticker调用函数
                for ticker in tickers:
                    logger.info(f"开始处理ticker: {ticker}")
                    # fetch_ticker_data(ticker, k_history_segments, fr_segments)
        else:
            logger.warning(f"CSV文件不存在: {csv_path}")
    except Exception as e:
        logger.error(f"读取CSV文件时发生错误: {e}")
