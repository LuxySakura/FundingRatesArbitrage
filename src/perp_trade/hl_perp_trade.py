import requests
import json
import os
import pandas as pd
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import signing
from hyperliquid.utils import constants
import time
import eth_account
from eth_account.signers.local import LocalAccount
import logging

# Hyperliquid中涉及的一些无需获取的全局常量
MAX_DECIMALS = 6
MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
"""
    Hyper Liquid上进行永续合约开单操作
"""
# 获取logger实例
logger = setup_logger('HyperliquidTrading')
# Ntl: Notional, USD amount, Px * Sz 
# Side: B = Bid = Buy, A = Ask = Short. Side is aggressing side for trades.
# Asset: An integer representing the asset being traded. See below for explanation
# Tif: Time in force, GTC = good until canceled, ALO = add liquidity only (post only), IOC = immediate or cancel
def set_price(price, side, min_base_price):
    """
    根据当前获取的价格，开单方向以及最小i多的最小价格变动单位，计算开单价格
    如果目标做多，则需要开仓价格略低于mark price
    如果目标做空，则需要开仓价格略高于mark price
    """
    return price - 20*min_base_price*side


def set_size(amount, leverage, price, decimals):
    """
    获取目标开仓张数
    Input:
        amount ==> 保证金额
        leverage ==> 开仓杠杆
        price ==> 开仓价格
        decimal ==> szDecimals
    Output:
        target_size ==> 开仓张数
    """
    # 获取目标开仓张数
    _target_size = (amount*leverage) / price  # 张数 = （保证金*杠杆）/开仓价格
    # 根据szDecimals规范化大小
    _target_size = round(_target_size, int(decimals))
    # 转换为字符串，确保精度正确
    _target_size_str = f"{{:.{decimals}f}}".format(_target_size)
    # 转回浮点数，去除多余的0
    _target_size = float(_target_size_str)
    return _target_size


def cal_min_price_move(mark_price, decimals):
    """
    根据获取的mark price, 以及szDecimals, 计算最小价格变动单位
    """
    available_decimal = MAX_DECIMALS - decimals
    # 计算最小价格变动单位
    return 10.0 ** (-available_decimal)


def retrieve_price(ticker, base_url, amount, side, decimals):
    """
    获取Hyper Liquid上的永续合约信息
    Input: 
        ticker ==> 用于获取对应合约价格的目标标的
        base_url ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 开仓方向
        decimals ==> szDecimals
    Output:
       target_price ==> 开仓价格
    """
    url = base_url + '/info'
    headers = {
        'Content-Type': 'application/json',
    }
    body = {
        'type': "l2Book",
        'coin': ticker,
    }
    res = requests.post(
        url, 
        headers=headers, 
        data=json.dumps(body)
    )

    if res.status_code == 200:
        data = res.json()
        # 获取当前最优买价
        _bid_price = data['levels'][0][0]["px"]
        # 计算最小价格变动单位
        _min_price_movement = cal_min_price_move(_bid_price, decimals)
        _bid_price = float(_bid_price)

        # _mark_price = data[1][index]['markPx']
        # _mid_price = float(data[1][index]['midPx'])
        
        # 获取目标价格
        _target_price = set_price(
            _price=_bid_price,
            _side=side,
            _min_base_price=_min_price_movement
        )
        return _target_price
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res}")
        return -1


def open_position_arb(base_url, side, ticker):
    """
    Hyper Liquid 套利方开仓
    Input:
        base_url ==> Hyper Liquid的API URL(Mainnet/Testnet)
        _side ==> 开仓方向
        _ticker ==> 目标标的
        _role ==> 仓位角色（套利方 True/对冲方 False）
    Output:
    """
    # 获取config.json下的私钥，并获取account
    _config_path = os.path.join(os.path.dirname(__file__), "../config.json")
    with open(_config_path) as f:
        _config = json.load(f)
    _account: LocalAccount = eth_account.Account.from_key(_config["secret_key"])
    _address = _config["account_address"]
    if _address == "":
        _address = _account.address
    logger.info(f"使用账户地址: {_address}")
    if _address != _account.address:
        logger.info(f"使用代理地址: {_account.address}")
    
    # 获取账户信息
    _info = Info(constants.TESTNET_API_URL, skip_ws=True)
    _user_state = _info.user_state(_address)
    _vault_fund = float(user_state['marginSummary']['totalRawUsd'])
    logger.info(f"总保证金USD: {_vault_fund}")

    _vault_fund = 5  # 保证金

    # 根据Ticker获取Hyper Liquid Token Index
    df = pd.read_csv('./data/hl_ticker_index.csv')
    # 根据ticker获取index以及decimals
    _target_record = df[df['name'] == ticker]
    
    # 修改这两行，使用.iloc基于位置访问第一行
    _index = _target_record.iloc[0]['index']  # 使用iloc[0]访问第一行
    _decimals = _target_record.iloc[0]['szDecimals']  # 获取该标的的小数位信息
    _max_leverage = _target_record.iloc[0]['maxLeverage']  # 获取当前标的最大可支持杠杆
    # 获取目标杠杆，取5和最大可支持杠杆中的最小值
    _target_leverage = min(_max_leverage, 5)

    # 计算开仓价格/张数/杠杆
    _target_price = retrieve_price(
        ticker=_ticker, 
        base_url=base_url, 
        side=False,
        decimals=_decimals
    )

    _target_size = set_size(
        amount=float(vault_fund),
        leverage=_target_leverage,
        price=_target_price,
        decimal=_decimals
    )
    logger.info(
        f"目标价格: {_target_price}, "
        f"目标数量: {_target_size}, "
        f"目标杠杆: {_target_lever}"
    )

    # 创建Exchange类
    exchange = Exchange(_account, base_url, account_address=_address)
    # 设置对应的杠杆（逐仓保证金模式）
    exchange.update_leverage(target_lever, _ticker, False)
    # 下单
    order_res = exchange.order(
        ticker,
        side,
        _target_size,
        _target_price,
        {"limit": {"tif": "Gtc"}}
    )
    logger.info(f"下单结果: {order_res}")

    # Query the order status by oid
    if order_res["status"] == "ok":
        status = order_res["response"]["data"]["statuses"][0]
        if "resting" in status:
            order_status = info.query_order_by_oid(_address, status["resting"]["oid"])
            logger.info(f"订单状态: {order_status}")
    return target_size


def open_position_hedge(base_url, side, ticker, arb_size):
    """
    Hyper Liquid 对冲方开仓
    Input:
        base_url ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 开仓方向
        ticker ==> 目标标的
    Output:
        hedge_open_price ==> 对冲方开仓价格
    """

    
    return 0


def close_position_arb(base_url, side, ticker):
    """
    Hyper Liquid 套利方平仓
    Input:
        base_url ==> Hyper Liquid的API URL(Mainnet/Testnet)
        _side ==> 开仓方向
        _ticker ==> 目标标的
        _role ==> 仓位角色（套利方 True/对冲方 False）
    Output:
    """
    # 获取config.json下的私钥，并获取account
    config_path = os.path.join(os.path.dirname(__file__), "../config.json")
    with open(config_path) as f:
        config = json.load(f)
    _account: LocalAccount = eth_account.Account.from_key(config["secret_key"])
    _address = config["account_address"]
    if _address == "":
        _address = _account.address
    print("Running with account address:", _address)
    if _address != _account.address:
        print("Running with agent address:", _account.address)

    print("进行套利方平仓策略")
        # TODO 获取开仓订单下的开仓价格和Size
    url = base_url + '/info'
    headers = {
        'Content-Type': 'application/json',
    }
    body = {
        'type': "clearinghouseState",
        'user': _address,
    }
    res = requests.post(
        url, 
        headers=headers, 
        data=json.dumps(body)
    )
    if res.status_code == 200:
        data = res.json()
        position = data['assetPositions'][0]['position']
        print(position)
            # d = {
            #   'assetPositions': [
            #       {
            #       'type': 'oneWay', 
            #       'position': {
            #           'coin': 'BTC', 
            #           'szi': '-0.0003', 
            #           'leverage': {
            #               'type': 'isolated', 'value': 5, 'rawUsd': '29.840434'}, 
            #           'entryPx': '82890.0', 
            #           'positionValue': '24.876', 
            #           'unrealizedPnl': '-0.009', 
            #           'returnOnEquity': '-0.0018096272', 
            #           'liquidationPx': '98240.1119341564', 
            #           'marginUsed': '4.964434', 'maxLeverage': 40, 
            #           'cumFunding': {
            # 'allTime': '-0.460658', 'sinceOpen': '0.0', 'sinceChange': '0.0'}}}], 'time': 1742278592428}
    else:
        print("Error: ", res.status_code, res)


def close_position_hedge(base_url, side, ticker):
    """
    Hyper Liquid 对冲方平仓
    Input:
        base_url ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 开仓方向
        ticker ==> 目标标的
    Output:
    """

if __name__ == "__main__":
    # open_position(
    #     base_url=TESTNET_API_URL,
    #     _side=False,
    #     _ticker="BTC"
    # )
    print("")