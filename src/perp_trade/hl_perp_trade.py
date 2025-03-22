import requests
import json
from sys import path as sys_path
from os import path as os_path
import pandas as pd
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import signing
from hyperliquid.utils import constants
import time
import eth_account
from eth_account.signers.local import LocalAccount

# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logging import setup_logger
# 导入工具模块
from src.utils import set_price, set_size, ExchangeApiConfig, POSITION_RISK, POSITION_LEVERAGE

# 获取logger实例
logger = setup_logger('HyperliquidTrading')

# 实现Binance交易平台API配置类
class HyperLiquidApiConfig(ExchangeApiConfig):
    def _setup_urls(self):
        """设置Binance的REST和WebSocket URL"""
        if self.type:  # 主网
            self.rest_url = "https://api.hyperliquid.xyz"
            self.ws_url = None
        else:  # 测试网
            self.rest_url = "https://api.hyperliquid-testnet.xyz"
            self.ws_url = None

# Hyperliquid中涉及的一些无需获取的全局常量
MAX_DECIMALS = 6
MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"
"""
    Hyper Liquid上进行永续合约开单操作
"""


def fetch_account_address():
    # 获取config.json下的私钥，并获取account
    _config_path = os_path.join(os_path.dirname(__file__), "../config.json")
    with open(_config_path) as f:
        _config = json.load(f)
    _account: LocalAccount = eth_account.Account.from_key(_config["secret_key"])
    _address = _config["account_address"]
    if _address == "":
        _address = _account.address
    logger.info(f"使用账户地址: {_address}")
    if _address != _account.address:
        logger.info(f"使用代理地址: {_account.address}")
    return _account, _address


def cal_min_price_move(mark_price, decimals):
    # 根据获取的mark price, 以及szDecimals, 计算最小价格变动单位
    available_decimal = MAX_DECIMALS - decimals
    # 计算最小价格变动单位
    return 10.0 ** (-available_decimal)


def retrieve_price(ticker, base_url, side, decimals):
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
            price=_bid_price,
            side=side,
            min_base_price=_min_price_movement
        )
        return _target_price
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res}")
        return -1


def open_position_arb(net, side, ticker):
    """
    Hyper Liquid 套利方开仓
    Input:
        net ==> Hyper Liquid的API URL(Mainnet/Testnet)
        _side ==> 开仓方向
        _ticker ==> 目标标的
    Output:
        _target_size ==> 套利方开仓张数
        _target_price ==> 套利方开仓价格
    """
    _account, _address = fetch_account_address()
    base_url = HyperLiquidApiConfig(net).get_rest_url()

    # 获取账户信息
    _info = Info(constants.TESTNET_API_URL, skip_ws=True)
    _user_state = _info.user_state(_address)

    # 计算保证金
    _vault_fund = float(_user_state['marginSummary']['totalRawUsd'])
    _vault_fund = _vault_fund * POSITION_RISK  # 保证金(取整)
    logger.info(f"总保证金USD: {_vault_fund}")

    # 根据Ticker获取Hyper Liquid Token Index
    df = pd.read_csv('./data/hl_ticker_index.csv')
    # 根据ticker获取index/decimals/maxLeverage
    _target_record = df[df['name'] == ticker]
    
    _index = _target_record.iloc[0]['index']  # 获取index
    _decimals = _target_record.iloc[0]['szDecimals']  # 获取该标的的小数位信息
    _max_leverage = _target_record.iloc[0]['maxLeverage']  # 获取当前标的最大可支持杠杆
    # 获取目标杠杆，取5和最大可支持杠杆中的最小值
    _target_leverage = min(_max_leverage, POSITION_LEVERAGE)

    # 计算开仓价格/张数
    _target_price = retrieve_price(
        ticker=ticker, 
        base_url=base_url,
        side=side,
        decimals=_decimals
    )

    _target_size = set_size(
        amount=float(_vault_fund),
        leverage=_target_leverage,
        price=_target_price,
        decimals=_decimals
    )

    logger.info(
        f"目标价格: {_target_price}, "
        f"目标数量: {_target_size}, "
        f"目标杠杆: {_target_leverage}"
    )

    # 创建Exchange类
    exchange = Exchange(_account, base_url, account_address=_address)
    # 设置对应的杠杆（逐仓保证金模式）
    exchange.update_leverage(_target_leverage, ticker, False)
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
            order_status = _info.query_order_by_oid(_address, status["resting"]["oid"])
            logger.info(f"订单状态: {order_status}")
    return _target_price, _target_size


def open_position_hedge(net, side, ticker, arb_size):
    """
    Hyper Liquid 对冲方开仓
    Input:
        net ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 开仓方向
        ticker ==> 目标标的
        arb_size ==> 套利方开仓张数
    Output:
        target_price ==> 对冲方开仓价格
    """
    _account, _address = fetch_account_address()
    _info = Info(constants.TESTNET_API_URL, skip_ws=True)
    base_url = HyperLiquidApiConfig(net).get_rest_url()

    # 根据Ticker获取Hyper Liquid Token Index
    df = pd.read_csv('./data/hl_ticker_index.csv')
    # 根据ticker获取index/decimals/maxLeverage
    _target_record = df[df['name'] == ticker]
    
    _index = _target_record.iloc[0]['index']  # 获取index
    _decimals = _target_record.iloc[0]['szDecimals']  # 获取该标的的小数位信息
    _max_leverage = _target_record.iloc[0]['maxLeverage']  # 获取当前标的最大可支持杠杆
    # 获取目标杠杆，取5和最大可支持杠杆中的最小值
    _target_leverage = min(_max_leverage, POSITION_LEVERAGE)

    # 计算开仓价格
    _target_price = retrieve_price(
        ticker=ticker, 
        base_url=base_url, 
        side=side,
        decimals=_decimals
    )

    logger.info(
        f"对冲方开仓价格: {_target_price}, "
        f"对冲方开仓数量: {arb_size}, "
        f"对冲方开仓杠杆: {_target_leverage}"
    )

    # 创建Exchange类
    exchange = Exchange(_account, base_url, account_address=_address)
    # 设置对应的杠杆（逐仓保证金模式）
    exchange.update_leverage(_target_leverage, ticker, False)
    # 下单
    order_res = exchange.order(
        ticker,
        side,
        arb_size,
        _target_price,
        {"limit": {"tif": "Gtc"}}
    )
    logger.info(f"下单结果: {order_res}")

    # Query the order status by oid
    if order_res["status"] == "ok":
        status = order_res["response"]["data"]["statuses"][0]
        if "resting" in status:
            order_status = _info.query_order_by_oid(_address, status["resting"]["oid"])
            logger.info(f"订单状态: {order_status}")
    return _target_price


def close_position_arb(net, side, ticker):
    """
    Hyper Liquid 套利方平仓
    Args:
        net ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 套利方平仓方向
        ticker ==> 套利方平仓标的
    Output:
        _target_price ==> 套利方平仓价格
    """
    _account, _address = fetch_account_address()
    _info = Info(constants.TESTNET_API_URL, skip_ws=True)
    base_url = HyperLiquidApiConfig(net).get_rest_url()

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

        # 获取当前账户的仓位
        position = data['assetPositions'][0]['position']
        arb_size = abs(float(position['szi']))
        pnl = position['unrealizedPnl']  # 利润
        # p = {
        #     'szi': '-0.00024', 
        #     'entryPx': '83419.0', 
        #     'positionValue': '20.0208', 
        #     'unrealizedPnl': '-0.00024',   # 利润
        # }

        # 根据Ticker获取Hyper Liquid Token Index
        df = pd.read_csv('./data/hl_ticker_index.csv')
        # 根据ticker获取decimals
        _target_record = df[df['name'] == ticker]
        _decimals = _target_record.iloc[0]['szDecimals']  # 获取该标的的小数位信息

        # 计算平仓价格/张数
        _target_price = retrieve_price(
            ticker=ticker, 
            base_url=base_url,
            side=side,
            decimals=_decimals
        )
        logger.info(
            f"平仓价格: {_target_price}, "
            f"平仓数量: {arb_size}, "
            f"利润: {pnl}, "
            f"平仓方向: {side}"
        )

        # 创建Exchange类
        exchange = Exchange(_account, base_url, account_address=_address)
        # 平仓
        order_res = exchange.order(
            ticker,
            side,
            arb_size,
            _target_price,
            {"limit": {"tif": "Gtc"}}
        )
        logger.info(f"下单结果: {order_res}")

        # Query the order status by oid
        if order_res["status"] == "ok":
            status = order_res["response"]["data"]["statuses"][0]
            if "resting" in status:
                order_status = _info.query_order_by_oid(_address, status["resting"]["oid"])
                logger.info(f"订单状态: {order_status}")

        return _target_price
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res}")
        return -1


def close_position_hedge(net, side, ticker, arb_open_price, arb_close_price):
    """
    Hyper Liquid 对冲方平仓
    Input:
        net ==> Hyper Liquid的API URL(Mainnet/Testnet)
        side ==> 开仓方向
        ticker ==> 目标标的
        arb_open_price ==> 套利方开仓价格
        arb_close_price ==> 套利方平仓价格
    Output:
    """
    _account, _address = fetch_account_address()
    _info = Info(constants.TESTNET_API_URL, skip_ws=True)
    base_url = HyperLiquidApiConfig(net).get_rest_url()

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

        # 获取当前账户的仓位
        position = data['assetPositions'][0]['position']
        hedge_size = abs(float(position['szi']))
        pnl = position['unrealizedPnl']  # 利润
        hedge_open_price = float(position['entryPx'])
        # p = {
        #     'szi': '-0.00024', 
        #     'entryPx': '83419.0', 
        #     'positionValue': '20.0208', 
        #     'unrealizedPnl': '-0.00024',   # 利润
        # }

        # 根据Ticker获取Hyper Liquid Token Index
        df = pd.read_csv('./data/hl_ticker_index.csv')
        # 根据ticker获取decimals
        _target_record = df[df['name'] == ticker]
        _decimals = _target_record.iloc[0]['szDecimals']  # 获取该标的的小数位信息

        # TODO 检查价格计算逻辑
        # 计算当前市场价下的平仓价格
        current_market_price = retrieve_price(
            ticker=ticker, 
            base_url=base_url,
            side=side,
            decimals=_decimals
        )

        # 计算价格风险完全对冲的平仓价格
        hedge_price = arb_close_price + hedge_open_price - arb_open_price
        
        # 计算最终的平仓价格
        if side:
            # 如果side为True，即对冲方平仓方向为Long，则开仓方向为Short，则应取二者的较小值
            _target_price = min(hedge_price, current_market_price)
        else:
            # 反之side为False，即对冲方平仓方向为Short，则开仓方向为Long，则应取二者的较大值
            _target_price = max(hedge_price, current_market_price)
        
        logger.info(
            f"市场价格: {current_market_price}, "
            f"风险完全对冲价格: {hedge_price}, "
            f"最终平仓价格: {_target_price}, "
            f"平仓数量: {hedge_size}, "
            f"利润: {pnl}, "
            f"平仓方向: {side}"
        )

        # 创建Exchange类
        exchange = Exchange(_account, base_url, account_address=_address)
        # 平仓
        order_res = exchange.order(
            ticker,
            side,
            hedge_size,
            _target_price,
            {"limit": {"tif": "Gtc"}}
        )
        logger.info(f"下单结果: {order_res}")

        # Query the order status by oid
        if order_res["status"] == "ok":
            status = order_res["response"]["data"]["statuses"][0]
            if "resting" in status:
                order_status = _info.query_order_by_oid(_address, status["resting"]["oid"])
                logger.info(f"订单状态: {order_status}")
            
        return _target_price
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res}")
        return -1


if __name__ == "__main__":
    # arb_open_price, arb_size = open_position_arb(
    #     base_url=TESTNET_API_URL,
    #     side=False,
    #     ticker="BTC"
    # )

    # arb_close_price = close_position_arb(
    #     base_url=TESTNET_API_URL,
    #     side=True,
    #     ticker="BTC"
    # )

    # open_position_hedge(
    #     base_url=TESTNET_API_URL,
    #     side=False,
    #     ticker="BTC",
    #     arb_size=0.00025
    # )

    close_position_hedge(
        base_url=TESTNET_API_URL,
        side=True,
        ticker="BTC",
        arb_open_price=10000,
        arb_close_price=9979
    )
