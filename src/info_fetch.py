import json
import requests
import pandas as pd
import re
import time
import datetime
import pandas as pd
from tqdm import tqdm  # 导入tqdm库
from sys import path as sys_path
from os import path as os_path
# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname((os_path.dirname(__file__))))
# 导入日志模块
from src.logger import setup_logger

# 获取logger实例
logger = setup_logger('InfoFetch')


okx_url = "https://www.okx.com/api/v5/public/funding-rate"
HL_MAINNET_URL = 'https://api.hyperliquid.xyz/info'  # HyperLiquid 主网 URL
HL_TESTNET_URL = 'https://api.hyperliquid-testnet.xyz/info'  # HyperLiquid 测试网 URL


def filter_usdc_pairs(df):
    # 筛选quoteAsset为USDC的记录
    usdc_records = df[df['quoteAsset'] == 'USDC']

    # 打印筛选结果
    print(f"共找到 {len(usdc_records)} 条 USDC 记录")

    # 可选：将筛选结果保存为新的CSV文件
    usdc_records.to_csv('./data/bin_perps_usdc.csv', index=False)
    print("USDC记录已保存到: bin_perps_usdc.csv")


def replace_none(value):
    _default = {
        'fundingRate': None,
        'nextFundingTime': None
    }
    return value if value is not None else _default


def time_trans(raw_time):
    # 将毫秒转换为秒
    seconds = raw_time / 1000
    
    # 获取本地时区的时间结构
    time_struct = time.localtime(seconds)
    
    # 格式化为datetime对象以保持返回类型一致
    # 注意：这里我们仍然需要使用datetime来创建对象，因为time库本身不提供类似的对象
    local_time = datetime.datetime(
        time_struct.tm_year, time_struct.tm_mon, time_struct.tm_mday,
        time_struct.tm_hour, time_struct.tm_min, time_struct.tm_sec
    )
    
    return local_time


def process_funding_rates(raw_data):
    """
    提取数据并构造各平台不同ticker的资金费率信息的DataFrame
    """
    rows = []
    # 使用tqdm创建进度条，total参数设置为数据总长度
    for item in tqdm(raw_data, desc="Fetch Funding Rates Data", unit="Tickers"):
        pair_name = item[0]  # 币对名
        print("\nCurrent Ticker: " + pair_name)
        pair_name = re.sub(r'^[a-z]+', '', pair_name)

        # 获取OKX上该Ticker的FR & FT
        okx_funding_rate, okx_funding_time = fetch_okx_funding_rates(pair_name)
        
        # 获取 Binance 上该Ticker的 FR & FT 
        bin_funding_rate = replace_none(item[1][0][1])['fundingRate']  # Binance Funding Rate
        bin_funding_time = replace_none(item[1][0][1])['nextFundingTime']  # Binance next FundingTime

        # 获取 HyperLiquid 上该Ticker的 FR & FT 
        hl_funding_rate = item[1][1][1]['fundingRate']
        hl_funding_time = item[1][1][1]['nextFundingTime']

        # 获取 Bybit 上该Ticker的 FR & FT 
        bybit_funding_rate = replace_none(item[1][2][1])['fundingRate']
        bybit_funding_time = replace_none(item[1][2][1])['nextFundingTime']

        rows.append([
            pair_name,
            bin_funding_rate, bin_funding_time,
            hl_funding_rate, hl_funding_time,
            bybit_funding_rate, bybit_funding_time,
            okx_funding_rate, okx_funding_time,
        ])

    # 创建DataFrame
    df = pd.DataFrame(rows,
                      columns=['ticker', 'BinFR', 'BinFT', 'HlFR', 'HlFT', 'BybitFR', 'BybitFT', 'OkxFR', 'OkxFT'])

    df['nextFT'] = df[['BinFT', 'HlFT', 'BybitFT', 'OkxFT']].min(axis=1)

    # 将生成的DataFrame保存为CSV文件
    df.to_csv('./data/funding_data.csv', index=False, encoding='utf-8')
    print("CSV文件已生成: funding_data.csv")


def fetch_okx_funding_rates(ticker):
    """根据HyperLiquid获取的合约数据，填充OKX下的资金费率"""
    params = {
        'instId': ticker+'-USDT-SWAP'
    }

    # 发送GET请求
    try:
        response = requests.get(okx_url, params=params)

        # 检查请求是否成功（HTTP状态码200表示成功）
        if response.status_code == 200:
            # 解析返回的数据（假设返回的是JSON格式）
            data = response.json()  # 将响应内容解析为Python字典

            code = data['code']  # 获取响应的Code, code=0
            if code == '0':
                fr = data['data'][0]['fundingRate']
                ft = int(data['data'][0]['fundingTime'])
            else:
                fr = None
                ft = None
            return fr, ft
        else:
            print(f"请求失败，状态码：{response.status_code}")
            print("响应内容：", response.text)  # 打印原始响应内容
            return None, None

    except requests.exceptions.RequestException as e:
        print(f"请求发生异常：{e}")
        return None, None


def fetch_hl_ticker_index(net):
    """
    获取Hyper Liquid上的所有ticker在universe上的index，方便后续根据index提取价格信息
    """
    headers = {
        'Content-Type': 'application/json',
    }
    body = {
        'type': "meta"
    }

    if net:
        url = HL_MAINNET_URL
        csv_path = './data/hl_ticker_index_mainnet.csv'
    else:
        url = HL_TESTNET_URL
        csv_path = './data/hl_ticker_index_testnet.csv'

    res = requests.post(
        url, 
        headers=headers, 
        data=json.dumps(body)
    )

    if res.status_code == 200:
        data = res.json().get('universe', [])
        
         # 创建一个列表来存储提取的数据
        extracted_data = []
        
        # 遍历universe数组，提取索引、name和maxLeverage
        for index, item in enumerate(data):
            extracted_data.append({
                'index': index,
                'name': item.get('name', ''),
                'maxLeverage': item.get('maxLeverage', 0),
                'szDecimals': item.get('szDecimals', 0),
            })
            print("New Record Added ==>", extracted_data[len(extracted_data)-1])
    
        # 创建DataFrame
        df = pd.DataFrame(extracted_data)
        
        # 保存为CSV文件
        df.to_csv(csv_path, index=False)
        print(f"测试数据已保存至: {csv_path}")

    else:
        print("Error: ", res.status_code, res)


def fetch_funding_rates():
    """
    获取各平台所有ticker的资金费率
    """
    # 从CSV文件中读取数据
    headers = {
        'Content-Type': 'application/json',
    }

    body = {
        'type': "predictedFundings"
    }

    # 记录开始时间
    # start_time = time.time()
    
    response = requests.post(HL_MAINNET_URL, headers=headers, data=json.dumps(body))

    # 检查请求是否成功
    if response.status_code == 200:
        # 获取响应内容
        data = response.json()
        """
            [
                "ticker",
                [
                  [
                    "BinPerp",
                    {
                      "fundingRate": "0.0001",
                      "nextFundingTime": 1733961600000
                    }
                  ],
                ]
              ]
        """
        process_funding_rates(data)
    else:
        print(f"请求失败，状态码: {response.status_code}")
    
    # 记录结束时间并计算执行时间
    # end_time = time.time()
    # execution_time = end_time - start_time
    # print(f"代码执行时间: {execution_time:.2f} 秒")


def fetch_bin_perps():
    """
    获取Binance上所有的perp
    """
     # 正确的API路径
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'

    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        params={}  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        symbols = data['symbols']
        new_data = []
        # 查找目标symbol的元素
        for symbol in symbols:
            new_data.append({
                'symbol': symbol['symbol'],
                'pair': symbol['pair'],
                'quoteAsset': symbol['quoteAsset'],
            })
        symbols_df = pd.DataFrame(new_data)
        logger.info(f"共获取到 {len(symbols_df)} 条资金费率记录")
        symbols_df.to_csv('./data/bin_perps.csv', index=False)
        logger.info(f"数据已保存到: bin_perps.csv")
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def fetch_bybit_perps():
    """
    获取Bybit上所有的perp
    """
    url = "https://api.bybit.com/v5/market/instruments-info"
    body = {
        'category': 'linear',
    }

    # 发送GET请求
    res = requests.get(
        url,
        params=body
    )

    # 检查请求是否成功
    if res.status_code == 200:
        # 获取响应内容
        msg = res.json()
        symbols = msg['result']['list']
        new_data = []
        # 查找目标symbol的元素
        for symbol in symbols:
            new_data.append({
                'symbol': symbol['symbol'],
                'baseCoin': symbol['baseCoin'],
                'quoteAsset': symbol['quoteCoin'],
            })
        symbols_df = pd.DataFrame(new_data)
        logger.info(f"共获取到 {len(symbols_df)} 条资金费率记录")
        symbols_df.to_csv('./data/bybit_perps.csv', index=False)
        logger.info(f"数据已保存到: bybit_perps.csv")


if __name__ == '__main__':
    fetch_funding_rates()
    # 获取Hyper Liquid上所有的perp标的，并将结果存储在"./data/hl_ticker_index_mainnet.csv中"
    fetch_hl_ticker_index(net=True)
    # fetch_bin_perps()
    # fetch_bybit_perps()

    # data = pd.read_csv('./data/bybit_perps.csv')
    # filter_usdc_pairs(data)
