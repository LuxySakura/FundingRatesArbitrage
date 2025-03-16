import json
import requests
import pandas as pd
import re
import time
import datetime
from tqdm import tqdm  # 导入tqdm库


okx_url = "https://www.okx.com/api/v5/public/funding-rate"
HL_MAINNET_URL = 'https://api.hyperliquid.xyz/info'  # HyperLiquid 主网 URL
HL_TESTNET_URL = 'https://api.hyperliquid-testnet.xyz/info'  # HyperLiquid 测试网 URL


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
    提取数据并构造DataFrame
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


if __name__ == '__main__':
    headers = {
        'Content-Type': 'application/json',
    }

    body = {
        'type': "predictedFundings"
    }

    response = requests.post(HL_TESTNET_URL, headers=headers, data=json.dumps(body))

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
