"""
该脚本实现在Binance上进行合约开单操作

描述:
    主要功能包括：
    - 套利方开仓/平仓
    - 对冲方开仓/平仓
    - 价格获取和订单管理

作者: Luxy
创建日期: 25/03/16
版本: 1.0.0
"""

import websockets
import asyncio
import requests
import json
import uuid  # 添加uuid模块用于生成随机字符串
from sys import path as sys_path
from os import path as os_path
import time

# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logging import setup_logger
# 导入工具模块
from src.utils import set_price, set_size, ExchangeApiConfig, POSITION_RISK, POSITION_LEVERAGE

# 获取logger实例
logger = setup_logger('BinanceTrading')

# 实现Binance交易平台API配置类
class BinanceApiConfig(ExchangeApiConfig):
    def _setup_urls(self):
        """设置Binance的REST和WebSocket URL"""
        if self.type:  # 主网
            self.rest_url = "https://fapi.binance.com"
            self.ws_url = "wss://ws-fapi.binance.com/ws-fapi/v1"
        else:  # 测试网
            self.rest_url = "https://testnet.binancefuture.com"
            self.ws_url = "wss://testnet.binancefuture.com/ws-fapi/v1"


# 基础全局变量
# MAIN_REST_BASEURL = "https://fapi.binance.com"
# TEST_REST_BASEURL = "https://testnet.binancefuture.com"
# MAIN_WS_BASEURL = "wss://ws-fapi.binance.com/ws-fapi/v1"
# TEST_WS_BASEURL = "wss://testnet.binancefuture.com/ws-fapi/v1"


def get_server_time(base_url):
    """获取币安服务器时间
    
    Args:
        base_url (str): 币安API的基础URL
        
    Returns:
        int: 服务器时间戳(毫秒)，失败时返回本地时间
    """
    response = requests.get(f"{base_url}/fapi/v1/time")
    if response.status_code == 200:
        return response.json()['serverTime']
    else:
        logger.error(f"获取服务器时间失败: {response.text}")
        return int(time.time() * 1000)  # 失败时返回本地时间


def fetch_api_key():
    """从config.json文件中获取对应的API Key
    
    Returns:
        tuple: 包含API Key和Secret Key的元组
            - api_key (str): 币安API密钥
            - secret_key (str): 币安API密钥对应的私钥
    """
    # 获取config.json下的私钥，并获取account
    _config_path = os_path.join(os_path.dirname(__file__), "../config.json")
    with open(_config_path) as f:
        _config = json.load(f)

    _api_key = _config["bin_testnet_api_key"]
    _secret_key = _config["bin_testnet_secret_key"]

    return _api_key, _secret_key


def generate_sign(api_secret, params):
    """生成签名，签名使用HMAC SHA256算法
    
    API-KEY所对应的API-Secret作为HMAC SHA256的密钥，
    其他所有参数作为HMAC SHA256的操作对象，得到的输出即为签名。
    
    Args:
        api_secret (str): API-Secret密钥
        params (dict): 需要签名的参数字典
        
    Returns:
        str: 生成的签名字符串
    """
    import hmac
    import hashlib
    from urllib.parse import urlencode
    
    # 将参数转换为查询字符串
    query_string = urlencode(params)
    
    # 使用HMAC SHA256算法生成签名
    signature = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return signature


def adjust_lever(base_url, api_key, secret_key, symbol, lever):
    """调整杠杆倍数
    
    Args:
        base_url (str): 币安API的基础URL
        api_key (str): 币安API密钥
        secret_key (str): 币安API密钥对应的私钥
        symbol (str): 交易对名称
        lever (int): 杠杆倍数
        
    Returns:
        int: 操作结果，0表示成功，-1表示失败
    """
    timestamp = get_server_time(base_url)

    url = base_url + '/fapi/v1/leverage'

    headers = {
        'X-MBX-APIKEY': api_key,
    }

    body = {
        'symbol': symbol,
        'leverage': lever,
        'recWindow': 3000,
        'timestamp': timestamp,
    }

    sign = generate_sign(secret_key, body)
    body['signature'] = sign

    res = requests.post(
        url,  
        headers=headers,
        data=body
    )

    if res.status_code == 200:
        data = res.json()
        return 0
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def query_user_data(base_url, api_key, secret_key):
    """查询用户数据，获取可用的保证金
    
    Args:
        base_url (str): 币安API的基础URL
        api_key (str): 币安API密钥
        secret_key (str): 币安API密钥对应的私钥
        
    Returns:
        float: 可用的USDT保证金余额，失败时返回-1
    """
    timestamp = get_server_time(base_url)

    # 正确的API路径
    url = base_url + '/fapi/v2/account'

    headers = {
        'X-MBX-APIKEY': api_key,
    }

    # 查询参数
    params = {
        'timestamp': timestamp,
        'recvWindow': 3000,  # 增加接收窗口时间
    }

    # 生成签名
    sign = generate_sign(secret_key, params)
    params['signature'] = sign

    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        headers=headers,
        params=params  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        # 查找asset为USDT的元素
        usdt_data = next((item for item in data['assets'] if item['asset'] == 'USDT'), None)
        if usdt_data:
            _available_balance = float(usdt_data['availableBalance'])
            return _available_balance
        else:
            logger.warning("未找到USDT资产信息")
            return -1
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def query_symbol_size(base_url, symbol):
    """查询标的的最小价格变动和最小数量变动
    
    Args:
        base_url (str): 币安API的基础URL
        symbol (str): 交易对名称
        
    Returns:
        int: 交易对数量精度，失败时返回-1
    """
    # 正确的API路径
    url = base_url + '/fapi/v1/exchangeInfo'

    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        params={}  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        symbols = data['symbols']
        # 查找目标symbol的元素
        symbol_data = next((item for item in symbols if item['symbol'] == symbol), None)
        if symbol_data:
            # min_size_step = symbol_data['filters'][1]['stepSize']
            size_decimals = symbol_data['quantityPrecision']
            # logger.info(f"{symbol}最小数量变动: {size_decimals}")
            return size_decimals
        else:
            logger.warning("未找到交易对信息")
            return -1
        # logger.info(f"API请求成功: {data[0]}, \n{data[1]}")
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def query_position(base_url, api_key, secret_key, symbol):
    """查询用户持仓信息
    
    Args:
        base_url (str): 币安API的基础URL
        api_key (str): 币安API密钥
        secret_key (str): 币安API密钥对应的私钥
        symbol (str): 交易对名称
        
    Returns:
        tuple: 包含开仓价格和持仓数量的元组
            - open_price (float): 开仓价格
            - position_size (float): 持仓数量
            失败时返回(-1, -1)
    """
    timestamp = get_server_time(base_url)

    # 正确的API路径
    url = base_url + '/fapi/v3/positionRisk'

    headers = {
        'X-MBX-APIKEY': api_key,
    }

    # 查询参数
    params = {
        'symbol': symbol,
        'timestamp': timestamp,
        'recvWindow': 3000,  # 增加接收窗口时间
    }

    # 生成签名
    sign = generate_sign(secret_key, params)
    params['signature'] = sign

    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        headers=headers,
        params=params  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        logger.info(f"仓位信息: {data}")
        open_price = float(data[0]['entryPrice'])
        position_size = float(data[0]['positionAmt'])
        logger.info(f"开仓价格: {open_price}, 持仓张数：{position_size}")
        return open_price, position_size
        # 查找asset为USDT的元素
        # position = next((item for item in data['positions'] if item['symbol'] == symbol), None)
        # if position:
        #     size = position['positionAmt']
        #     logger.info(f"仓位信息: {position}, 持仓张数：{size}")
        #     return size
        # else:
        #     logger.warning("未找到仓位信息")
        #     return -1
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1, -1
    # 查询参数


async def retrieve_price(base_url, symbol, side):
    """获取标的当前价格并计算目标价格
    
    Args:
        base_url (str): WebSocket API的基础URL
        symbol (str): 交易对名称
        side (bool): 交易方向，True为买入，False为卖出
        
    Returns:
        float: 计算后的目标价格，失败时返回-1
    """
    target_price = -1
    async with websockets.connect(base_url) as websocket:
        # 发送订阅消息
        subscribe_message = {
            "id": str(uuid.uuid4()),  # 使用uuid生成随机字符串作为id
            "method": "ticker.price",
            "params": {
                "symbol": symbol,
            }
        }
        await websocket.send(json.dumps(subscribe_message))

        # 接收并处理消息
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)  # 假设消息是JSON格式

                if data['status'] == 200:
                    price_str = data['result']['price']  # 获取价格字符串
                    price = float(price_str)  # 标记价格

                    # 计算小数位数
                    decimal_places = 0
                    if '.' in price_str:
                        # 去除尾随零后再计算小数位数
                        decimal_part = price_str.split('.')[1].rstrip('0')
                        decimal_places = len(decimal_part)
                    
                    # 计算最小价格变动
                    min_price_movement = 10 ** (-decimal_places)
                    
                    # 计算目标价格
                    target_price = set_price(price, side, min_price_movement)
                    logger.info(f"当前价格: {price}; 目标价格: {target_price}")
                else:
                    logger.error(f"API请求失败: 状态码 {data['status']}, 响应: {data}")

                break
            except json.JSONDecodeError:
                logger.error("Received message is not valid JSON")
        
        await websocket.close()
    return target_price


def place_trade(base_url, api_key, secret_key, price, side, symbol, size):
    """下单交易
    
    Args:
        base_url (str): 币安API的基础URL
        api_key (str): 币安API密钥
        secret_key (str): 币安API密钥对应的私钥
        price (float): 下单价格
        side (bool): 交易方向，True为买入，False为卖出
        symbol (str): 交易对名称
        size (float): 下单数量
        
    Returns:
        int: 操作结果，0表示成功，-1表示失败
    """
    side_enum = "BUY" if side else "SELL"

    timestamp = get_server_time(base_url)

     # 正确的API路径
    url = base_url + '/fapi/v1/order'

    headers = {
        'X-MBX-APIKEY': api_key,
    }

    params = {
        "symbol": symbol,
        "side": side_enum,
        "type": "LIMIT",
        "quantity": size,
        "price": price,
        "timeInForce": "GTC",
        "timestamp": timestamp,
    }

    # 生成签名
    signature = generate_sign(secret_key, params)
    # 将签名添加到参数中
    params["signature"] = signature
    logger.info(f"下单参数: {params}")

    try:
        response = requests.post(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"下单成功: {data}")
            return 0
        else:
            logger.error(f"API请求失败: 状态码 {response.status_code}, 响应: {response.text}")
            return -1
    except Exception as e:
        logger.error(f"下单异常: {str(e)}")
        return -1


def open_position_arb(net, side, ticker):
    """Binance套利方开仓
    
    Args:
        net (bool): Binance的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        
    Returns:
        tuple: 包含开仓价格和开仓数量的元组
            - target_price (float): 套利方开仓价格
            - target_size (float): 套利方开仓张数
    """
    config = BinanceApiConfig(net)  # 构建对应网络的API配置
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL

    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对
    
    api_key, secret_key = fetch_api_key()

    # 查询账户余额
    fund = query_user_data(
        rest_base_url,
        api_key, secret_key
    )

    # 计算保证金
    logger.info(f"账户可用保证金余额: {fund}")
    position_fund = fund * POSITION_RISK
    logger.info(f"仓位保证金: {position_fund}")

    # 计算开仓价格 
    target_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )

    size_decimals = query_symbol_size(
        rest_base_url,
        target_perp
    )
    # 根据账户数据获取目标标的张数
    target_size = set_size(
        amount=position_fund, 
        leverage=POSITION_LEVERAGE, 
        price=target_price, 
        decimals=size_decimals
    )
    logger.info(f"目标标的张数: {target_size}")

    # 调整目标标的杠杆
    adjust_lever(
        rest_base_url, 
        api_key, secret_key, 
        target_perp, POSITION_LEVERAGE
    )

    # 下单
    place_trade(
        base_url=rest_base_url,
        api_key=api_key, secret_key=secret_key,
        price=target_price, side=side,
        symbol=target_perp, size=target_size
    )
    
    return target_price, target_size


def open_position_hedge(net, side, ticker, arb_size):
    """Binance对冲方开仓
    
    Args:
        net (bool): Binance的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        arb_size (float): 套利方开仓张数
        
    Returns:
        float: 对冲方开仓价格
    """
    # 获取基础信息
    config = BinanceApiConfig(net)  # 构建对应网络的API配置
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    target_perp = ticker+"USDC"  # 根据ticker构建出目标perp的币对
    api_key, secret_key = fetch_api_key()

    # 调整目标标的杠杆
    adjust_lever(
        rest_base_url, 
        api_key, secret_key, 
        target_perp, POSITION_LEVERAGE
    )

    # 计算价格
    target_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )

    logger.info(
        f"对冲方开仓价格: {target_price}, "
        f"对冲方开仓数量: {arb_size}, "
        f"对冲方开仓杠杆: {POSITION_LEVERAGE}"
    )

    # 下单
    place_trade(
        base_url=rest_base_url,
        api_key=api_key, secret_key=secret_key,
        price=target_price, side=side,
        symbol=target_perp, size=arb_size
    )

    return target_price


def close_position_arb(net, side, ticker):
    """Binance套利方平仓
    
    Args:
        net (bool): Binance的API URL类型，True为主网，False为测试网
        side (bool): 平仓方向，True为买入平仓，False为卖出平仓
        ticker (str): 目标标的，如"BTC"
        
    Returns:
        int: 操作结果，0表示成功
    """
    # 获取基础信息
    config = BinanceApiConfig(net)  # 构建对应网络的API配置
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对
    api_key, secret_key = fetch_api_key()

    # 获取仓位信息（仓位大小）
    open_price, size = query_position(
        rest_base_url,
        api_key, secret_key,
        target_perp
    )

    # 计算平仓价格
    target_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )

    # 下单平仓
    place_trade(
        base_url=rest_base_url,
        api_key=api_key, secret_key=secret_key,
        price=target_price, side=side,
        symbol=target_perp, size=size
    )

    return 0


def close_position_hedge(net, side, ticker, arb_open_price, arb_close_price):
    # 获取基础信息
    config = BinanceApiConfig(net)  # 构建对应网络的API配置
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对
    api_key, secret_key = fetch_api_key()

    # 获取当前账户的仓位/开仓价格
    hedge_open_price, hedge_size = query_position(
        rest_base_url,
        api_key, secret_key,
        target_perp
    )

    # 计算当前市场价下的平仓价格
    current_market_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )
    # 计算价格风险完全对冲的平仓价格
    hedge_price = arb_close_price + hedge_open_price - arb_open_price

    # 计算最终的平仓价格
    if side:
        # 如果side为True，即对冲方平仓方向为Long，则开仓方向为Short，则应取二者的较小值
        target_price = min(hedge_price, current_market_price)
    else:
        # 反之side为False，即对冲方平仓方向为Short，则开仓方向为Long，则应取二者的较大值
        target_price = max(hedge_price, current_market_price)
    
    logger.info(
        f"市场价格: {current_market_price}, "
        f"风险完全对冲价格: {hedge_price}, "
        f"最终平仓价格: {target_price}, "
        f"平仓数量: {hedge_size}, "
        f"平仓方向: {side}"
     )
    
    # 下单平仓
    place_trade(
        base_url=rest_base_url,
        api_key=api_key, secret_key=secret_key,
        price=target_price, side=side,
        symbol=target_perp, size=hedge_size
    )

    return 0

# 下单 API: POST /fapi/v1/order（测试下单 API: POST /fapi/v1/order/test）
# symbol 交易对名字 YES
# side 买卖方向(SELL/BUY) YES
# positionSide 持仓方向(LONG/SHORT) NO
# type 订单类型 YES
#   LIMIT/ 限价
#   STOP/ 止损
#   TAKE_PROFIT/ 止盈
# quantity 下单数量
# price 委托价格
# stopPrice 触发价格 仅 STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 需要此参数


if __name__ == "__main__":
    # open_position_arb(False, True, "BTC")

    # close_position_arb(False, False, "BTC")

    close_position_hedge(False, False, "BTC", 20000, 19950)