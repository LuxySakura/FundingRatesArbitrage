import requests
import json
import pandas as pd
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import signing
import time
import eth_account
from eth_account.signers.local import LocalAccount

# Hyperliquid中涉及的一些无需获取的全局常量
MAX_DECIMALS = 6
MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
"""
    Hyper Liquid上进行永续合约开单操作
"""
# Px: Price
# Sz: Size, In units of coin, i.e. base currency
# Szi: Signed size, Positive for long, negative for short
# Ntl: Notional, USD amount, Px * Sz 
# Side: B = Bid = Buy, A = Ask = Short. Side is aggressing side for trades.
# Asset: An integer representing the asset being traded. See below for explanation
# Tif: Time in force, GTC = good until canceled, ALO = add liquidity only (post only), IOC = immediate or cancel
def set_price(_price, _side, _min_base_price):
    """
    根据当前获取的价格，开单方向以及最小i多的最小价格变动单位，计算开单价格
    """
    return _price + 10 * _min_base_price * _side


def cal_min_price_move(_mark_price, _decimal):
    """
    根据获取的mark price, 以及szDecimals, 计算最小价格变动单位
    """
    available_decimal = MAX_DECIMALS - _decimal
    current_decimal = len(_mark_price) - 1
    # 检查是否包含小数点
    if '.' in _mark_price:
        # 分割字符串，获取小数部分
        decimal_part = _mark_price.split('.')[1]
        # 返回小数部分的长度
        current_decimal = len(decimal_part)
    else:
        # 如果没有小数点，则小数位数为0
        current_decimal = 0
    print(_mark_price, "Current Decimal: ", current_decimal)

    # 计算最小价格变动单位
    return 10.0 ** (-available_decimal)


def retrieve_perp_info(ticker, base_url):
    """
    获取Hyper Liquid上的永续合约信息
    """
    # 根据Ticker获取Hyper Liquid Token Index
    # 例如：BTC-USD-PERP，对应的index为1
    df = pd.read_csv('./data/hl_ticker_index.csv')
    # 根据ticker获取index以及decimals
    target_record = df[df['name'] == ticker]
    print("Found Target Record:\n", target_record)
    
    # 修改这两行，使用.iloc基于位置访问第一行
    index = target_record.iloc[0]['index']  # 使用iloc[0]访问第一行
    decimals = target_record.iloc[0]['szDecimals']  # 使用iloc[0]访问第一行
    
    print(f"Ticker: {ticker} ==> index: ", index, "Decimals: ", decimals)

    url = base_url + '/info'

    headers = {
        'Content-Type': 'application/json',
    }

    body = {
        'type': "metaAndAssetCtxs"
    }

    res = requests.post(
        url, 
        headers=headers, 
        data=json.dumps(body)
    )

    if res.status_code == 200:
        data = res.json()
        # 根据之前获取到的Hyper Liquid Token Index进行整合，提取价格数据
        mark_price = data[1][index]['markPx']
        min_price_movement = cal_min_price_move(mark_price, decimals)
        mark_price = float(mark_price)

        # 'funding': '0.0000125', 
        # 'openInterest': '10831.6516', 
        # 'dayNtlVlm': '1086148514.8667230606', 
        # 'premium': '0.00002399', 
        # 'oraclePx': '83368.0', 
        mid_price = float(data[1][index]['midPx'])
        # 'impactPxs': ['83370.0', '83371.0'], 
        # 'dayBaseVlm': '12726.7935299999'
        print("Mark Price: ", mark_price, "Mid Price:", mid_price)
        return mark_price, min_price_movement, mid_price
    else:
        print("Error: ", res.status_code, res)
        return -1, -1, -1


def fetch_hl_ticker_index(base_url):
    """
    获取Hyper Liquid上的所有ticker在universe上的index，方便后续根据index提取价格信息
    """
    url = base_url + '/info'
    headers = {
        'Content-Type': 'application/json',
    }
    body = {
        'type': "meta"
    }

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
        csv_path = './data/hl_ticker_index.csv'
        df.to_csv(csv_path, index=False)
        print(f"测试数据已保存至: {csv_path}")

    else:
        print("Error: ", res.status_code, res)

    return "test"


def place_order(base_url, _amount, _side, _assetID, _price):
    """
    Hyper Liquid 下单
    """
    # 下单时间为资金费收取的前一分钟
    order_open_tmp = set_order_tmp(funding_rate_tmp) # 开单时间
    order_close_tmp = set_order_tmp(funding_rate_tmp) # 平仓时间
    # 设置开仓价格，为标记价格符合开仓方向的0.2%，
    # 例如：做多，则向下浮动；做空，则向上浮动
    order_price = str(set_price(mark_price, side))  # 根据
    close_price = set_price(mark_price, side) # 平仓价格

    # TODO 设置止盈价格
    # TODO 设置止损价格
    _size = str(_amount / _price)
    
    # 构建交易主体的订单内容
    _action = {
        "type": "order",
        "orders": [{
            "a": _assetID,  # Asset ID
            "b": _side,  # Side, isBuy(True = Long/ False = Short),
            "p": order_price,  # Price
            "s": _size,  # Size
            "r": False,  # Reduce Only
            "t": {
                "limit": {
                    "tif": "Gtc" 
                },
                # "trigger": {
                #     "isMarket": Boolean,
                #     "triggerPx": String,
                #     "tpsl": "tp" | "sl"
                # },
            },
        }],
        "grouping": "na" | "normalTpsl" | "positionTpsl",
        # "builder": Optional({
        #     "b": "address",  # the address the should receive the additional fee
        #     "f": Number  # size of the fee in tenths of a basis point e.g. if f is 10, 1bp of the order notional
        #     })
    }
    _nonce = int(time.time() * 1000)  # 使用当前时间戳作为nonce
    # _signature = sign_l1_action(
    #     wallet, # 钱包地址 ==> LocalAccount = eth_account.Account.from_key(config["secret_key"])
    #     order_action,
    #     self.vault_address,
    #     timestamp,
    #     self.base_url == MAINNET_API_URL,
    # )

    # 获取config.json下的私钥，并获取account
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path) as f:
        config = json.load(f)
    _account: LocalAccount = eth_account.Account.from_key(config["secret_key"])

    # 构建提交订单所需要的签名
    _sign = signing.sign_l1_action(
        _account, # 钱包地址
        _action,
        None, # None
        _nonce,
        TESTNET_API_URL,
    )

    url = base_url + '/exchange'

    headers = {
        'Content-Type': 'application/json',
    }
    body = {
        'action': _action,
        'nonce': _nonce,
        'signature': _sign
    }
    
    return "test"

if __name__ == "__main__":
    # fetch_hl_ticker_index()
    retrieve_perp_info(ticker="BTC", base_url=TESTNET_API_URL)