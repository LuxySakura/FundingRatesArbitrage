import json
import requests
import pandas as pd
import datetime
import pytz
import re

default_obj = {'fundingRate': '0', 'nextFundingTime': 1739980800000}
okx_url = "https://www.okx.com/api/v5/public/funding-rate"


def replace_none(value, default=default_obj):
    return value if value is not None else default


def time_trans(raw_time):
    # 将毫秒转换为秒
    seconds = raw_time / 1000

    # 转换为 UTC 时间
    utc_time = datetime.datetime.fromtimestamp(seconds, datetime.UTC)

    # 设置 UTC-8 时区
    utc_minus_8 = pytz.timezone('Asia/Shanghai')  # UTC-8 时区

    # 将 UTC 时间转换为 UTC-8 时间
    utc_minus_8_time = utc_time.astimezone(utc_minus_8)
    return utc_minus_8_time


def process_funding_rates(raw_data):
    # 提取数据并构造DataFrame
    rows = []
    for item in data:
        pair_name = item[0]  # 币对名
        print("Current Ticker: " + pair_name)
        pair_name = re.sub(r'^[a-z]+', '', pair_name)

        okx_funding_rate, okx_funding_time = fetch_okx_funding_rates(pair_name)

        bin_funding_rate = float(replace_none(item[1][0][1])['fundingRate'])*100  # Binance Funding Rate
        bin_funding_time = time_trans(replace_none(item[1][0][1])['nextFundingTime'])  # Binance next FundingTime

        hl_funding_rate = float(item[1][1][1]['fundingRate'])*100  # fundingRate
        hl_funding_time = time_trans(item[1][1][1]['nextFundingTime'])  # nextFundingTime

        bybit_funding_rate = float(replace_none(item[1][2][1])['fundingRate'])*100  # fundingRate
        bybit_funding_time = time_trans(replace_none(item[1][2][1])['nextFundingTime'])  # nextFundingTime

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

    df = df[~((df['BinFR'] == 0) & (df['BybitFR'] == 0) & (df['OkxFR'] == 0))]

    df['BinHlFR'] = df['BinFR'] - df['HlFR']  # Binance 资金费率差
    df['BybitHlFR'] = df['BybitFR'] - df['HlFR']  # Bybit 资金费率差
    df['OkxHlFR'] = df['OkxFR'] - df['HlFR']  # OKX 资金费率差

    df['maxFR'] = df[['BinFR', 'HlFR', 'BybitFR', 'OkxFR', 'BinHlFR', 'BybitHlFR', 'OkxHlFR']].abs().max(axis=1)

    # # 创建目录（如果不存在）
    # import os
    # output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)
    #     print(f"创建目录: {output_dir}")
    # 
    # # 保存为CSV文件
    # output_file = os.path.join(output_dir, 'funding_data.csv')
    # df.to_csv(output_file, index=False, encoding='utf-8')
    # print(f"CSV文件已生成: {output_file}")
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
                fr = float(data['data'][0]['fundingRate']) * 100
                ft = time_trans(int(data['data'][0]['fundingTime']))
                
            else:
                fr = 0
                ft = default_obj['nextFundingTime']
                print("Ticker", ticker, "No Current Pair in OKX!")
            print("Ticker", ticker, "==> FR:", fr, "FT:", ft)
            return fr, ft

        else:
            print(f"请求失败，状态码：{response.status_code}")
            print("响应内容：", response.text)  # 打印原始响应内容
            return default_obj['fundingRate'], default_obj['nextFundingTime']

    except requests.exceptions.RequestException as e:
        print(f"请求发生异常：{e}")

        return default_obj['fundingRate'], default_obj['nextFundingTime']


if __name__ == '__main__':
    headers = {
        'Content-Type': 'application/json',
    }

    body = {
        'type': "predictedFundings"
    }

    response = requests.post('https://api.hyperliquid.xyz/info', headers=headers, data=json.dumps(body))

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
                  [
                    "HlPerp",
                    {
                      "fundingRate": "0.0000125",
                      "nextFundingTime": 1733958000000
                    }
                  ],
                  [
                    "BybitPerp",
                    {
                      "fundingRate": "0.0001",
                      "nextFundingTime": 1733961600000
                    }
                  ]
                ]
              ]
        """
        process_funding_rates(data)
    else:
        print(f"请求失败，状态码: {response.status_code}")
