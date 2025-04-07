"""
该脚本实现在Bybit上进行合约开单操作

描述:
    主要功能包括：
    - 套利方开仓/平仓
    - 对冲方开仓/平仓
    - 价格获取和订单管理

作者: Luxy
创建日期: 25/04/03
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
from src.logger import setup_logger
# 导入工具模块
from src.utils import set_price, set_size, ExchangeApiConfig, POSITION_RISK, POSITION_LEVERAGE

# 获取logger实例
logger = setup_logger('BybitTrading')

# 实现Binance交易平台API配置类
class BybitApiConfig(ExchangeApiConfig):
    def _setup_urls(self):
        """设置Bybit的REST和WebSocket URL"""
        if self.type:  # 主网
            self.rest_url = "https://api.bybit.com"
            self.ws_url = "wss://stream.bybit.com/v5"
        else:  # 测试网
            self.rest_url = "https://api-demo.bybit.com"
            self.ws_url = "wss://stream.bybit.com/v5"


def fetch_api_key(net):
    """
    从config.json文件中获取对应的API Key等信息
    
    Args:
        net (bool): 是否为主网
    Returns:
        tuple: 包含API Key, Secret Key和Passphrase的元组
            - api_key (str): OKX API密钥
            - secret_key (str): OKX API密钥对应的私钥
            - passphrase (str): OKX API密钥对应的Passphrase
    """
    # 获取config.json下的私钥，并获取account
    _config_path = os_path.join(os_path.dirname(__file__), "../config.json")
    with open(_config_path) as f:
        _config = json.load(f)

    if net:
        _api_key = _config["bybit_api_key"]
        _secret_key = _config["bybit_secret_key"]
    else:
        _api_key = _config["bybit_testnet_api_key"]
        _secret_key = _config["bybit_testnet_secret_key"]

    return _api_key, _secret_key


def get_server_time(base_url):
    """获取Bybit服务器时间
    
    Args:
        base_url (str): Bybit API的基础URL
        
    Returns:
        int: 服务器时间戳(毫秒)，失败时返回本地时间
    """
    response = requests.get(f"{base_url}/v5/market/time")
    if response.status_code == 200:
        # 服务器返回的是秒
        bybit_sec = response.json()['result']['timeSecond']
        # 转换成毫秒返回
        return str(int(bybit_sec) * 1000)
    else:
        logger.error(f"获取服务器时间失败: {response.text}")
        return str(int(time.time() * 1000))  # 失败时返回本地时间


def generate_sign(api_key, secret_key, timestamp, method, body):
    """
    生成签名

    BYBIT-SIGN的请求头是对timestamp + API Key + body字符串（+表示字符串连接），
    使用HMAC_SHA256算法對第1步中拼接的string簽名，
    並轉換為16進製字符串(HMAC_SHA256)，得出sign參數

    Args:
        secret_key (str): API密钥对应的私钥
        timestamp (str): 时间戳，格式为ISO 8601标准格式，如2020-12-08T09:08:57.715Z
        method (str): 请求方法，如GET、POST等
    Returns:
        str: 签名
    """
    import hmac
    import base64
    import hashlib

    # 构建待签名的字符串
    message = timestamp + api_key
    
    # 根据请求方法不同，处理body的方式不同
    if method == 'GET':
        # GET请求：将body参数转换为查询字符串格式
        if body:
            query_string = '&'.join([f"{key}={value}" for key, value in body.items()])
            message += query_string
    else:
        message += body
    
    # 使用HMAC SHA256算法进行加密
    mac = hmac.new(
        bytes(secret_key, encoding='utf8'),
        message.encode('utf8'),
        digestmod=hashlib.sha256
    )
    
    # 对加密结果转换为16进制字符串(HMAC_SHA256)
    sign = mac.hexdigest()
    return sign


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

     # 正确的API路径
    url = base_url + '/v5/position/set-leverage'

    body = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": lever,
        "sellLeverage": lever,
    }

    json_body = json.dumps(body)

    # 生成签名
    sign = generate_sign(
        timestamp=timestamp, api_key=api_key, secret_key=secret_key, 
        method='POST', body=json_body
    )

    headers = {
        'Content-Type': "application/json",
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': sign,
        'X-BAPI-TIMESTAMP': timestamp,
    }

    try:
        response = requests.post(url, headers=headers, data=json_body)
        if response.status_code == 200:
            data = response.json()
            if data['retCode'] == 0:
                logger.info(f"调整杠杆成功: {data}")
                return 0
            else:
                logger.error(f"调整杠杆失败: {data}")
                return -1
        else:
            logger.error(f"API请求失败: 状态码 {response.status_code}, 响应: {response.text}")
            return -1
    except Exception as e:
        logger.error(f"下单异常: {str(e)}")
        return -1


def query_balance(base_url, api_key, secret_key):
    """
    查询用户数据，获取可用的保证金
    
    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
        passphrase (str): OKX API密钥对应的Passphrase
        
    Returns:
        float: 可用的USDT保证金余额，失败时返回-1
    """
    method = 'GET'
    request_path = '/v5/account/wallet-balance'
    timestamp = get_server_time(base_url)
    body = {
        'accountType': 'UNIFIED',
        'coin': "USDT"
    }

    sign = generate_sign(api_key, secret_key, timestamp, method, body)

    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': sign,
        'X-BAPI-TIMESTAMP': timestamp,
    }
    
    # 使用GET请求而不是POST
    res = requests.get(
        url,
        headers=headers,
        params=body  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        if data['retCode'] == 0:
            balance = data['result']['list'][0]['coin'][0]['walletBalance']
            logger.info(f"API请求成功，账户余额: {balance}")
            return balance
        else:
            logger.error(f"API请求失败: {data}")
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
    url = base_url + '/v5/market/instruments-info'

    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        params={
            'category': 'linear',
            'symbol': symbol
        }  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        if data['retCode'] == 0:
            quantity_step = data['result']['list'][0]['lotSizeFilter']['qtyStep']
            # 计算qtyStep是10的几次幂
            qty_step_float = float(quantity_step)
            # 使用对数计算
            import math
            if qty_step_float > 0:
                decimal_places = abs(int(math.log10(qty_step_float)))
                logger.info(f"当前币种最小下单数目: {quantity_step}, 精度为小数点后{decimal_places}位")
                return decimal_places
            else:
                logger.error(f"无效的qtyStep值: {quantity_step}")
                return -1
        else:
            logger.error(f"API请求失败: {data}")
            return -1
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def query_position(base_url, api_key, secret_key, symbol):
    """
    查询标的的当前仓位
    """
    method = 'GET'
    request_path = '/v5/position/list'
    timestamp = get_server_time(base_url)
    body = {
        'category': 'linear',
        'symbol': symbol
    }

    sign = generate_sign(api_key, secret_key, timestamp, method, body)

    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': sign,
        'X-BAPI-TIMESTAMP': timestamp,
    }
    
    # 使用GET请求而不是POST
    res = requests.get(
        url,
        headers=headers,
        params=body  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        if data['retCode'] == 0:
            position = data['result']['list'][0]
            # {
            #     'symbol': 'BTCUSDT', 
            #     'leverage': '5', 
            #     'autoAddMargin': 0, 
            #     'avgPrice': '74939.5', 
            #     'liqPrice': '60326.3', 
            #     'riskLimitValue': '2000000', 
            #     'positionValue': '2473.0035', 
            #     'unrealisedPnl': '7.0422', 
            #     'markPrice': '75152.9', 
            #     'adlRankIndicator': 2, 
            #     'cumRealisedPnl': '-0.4946007', 
            #     'positionMM': '13.45313904', 
            #     'createdTime': '1743946509221', 
            #     'positionIdx': 0, 
            #     'positionIM': '495.68882154', 
            #     'seq': 140710062434461, 
            #     'updatedTime': '1744011345134', 
            #     'side': 'Buy', 
            #     'bustPrice': '', 
            #     'positionBalance': '495.68882154', 
            #     'curRealisedPnl': '-0.4946007', 
            #     'size': '0.033', 
            #     'positionStatus': 'Normal', 
            #     'tradeMode': 0, 
            # }
            open_price = position['avgPrice']
            size = position['size']
            logger.info(f"API请求成功，持仓信息: {position}")
            return open_price, size
        else:
            logger.error(f"API请求失败: {data}")
            return -1, -1
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1, -1


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
    url = base_url + "/public/linear"  # 实际订阅频道
    
    async with websockets.connect(url) as websocket:
        # 发送订阅消息
        subscribe_message = {
            "op": "subscribe",
            "args": [
                f"tickers.{symbol}"
            ]
        }
        await websocket.send(json.dumps(subscribe_message))
        # 接收并处理消息
        while True:
            try:
                message = await websocket.recv()
                
                data = json.loads(message)  # 解析JSON消息
                
                data = data['data']
                price_str = data["lastPrice"]
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
                logger.info(f"当前价格: {price}; 目标开仓价格: {target_price}")
                break
                
            except json.JSONDecodeError:
                logger.error("Received message is not valid JSON")
        
        await websocket.close()
    return target_price


def place_trade(base_url, api_key, secret_key, price, side, symbol, size):
    """下单交易
    
    Args:
        base_url (str): Bybit API的基础URL
        api_key (str): Bybit API密钥
        secret_key (str): Bybit API密钥对应的私钥
        price (float): 下单价格
        side (bool): 交易方向，True为买入，False为卖出
        symbol (str): 交易对名称
        size (float): 下单数量
        
    Returns:
        int: 操作结果，0表示成功，-1表示失败
    """
    side_enum = "Buy" if side else "Sell"

    timestamp = get_server_time(base_url)

     # 正确的API路径
    url = base_url + '/v5/order/create'

    body = {
        "category": "linear",
        "symbol": symbol,
        "side": side_enum,
        "orderType": "Limit",
        "qty": str(size),
        "price": str(price)
    }
    json_body = json.dumps(body)

    # 生成签名
    sign = generate_sign(
        timestamp=timestamp, api_key=api_key, secret_key=secret_key, 
        method='POST', body=json_body
    )

    headers = {
        'Content-Type': "application/json",
        'X-BAPI-API-KEY': api_key,
        'X-BAPI-SIGN': sign,
        'X-BAPI-TIMESTAMP': timestamp,
    }

    try:
        response = requests.post(url, headers=headers, data=json_body)
        if response.status_code == 200:
            data = response.json()
            if data['retCode'] == 0:
                logger.info(f"下单成功: {data}")
                return 0
            else:
                logger.error(f"下单失败: {data}")
                return -1
        else:
            logger.error(f"API请求失败: 状态码 {response.status_code}, 响应: {response.text}")
            return -1
    except Exception as e:
        logger.error(f"下单异常: {str(e)}")
        return -1


def open_position_arb(net, side, ticker):
    """
    Bybit 套利方开仓
    
    Args:
        net (bool): Bybit 的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        
    Returns:
        tuple: 包含开仓价格和开仓数量的元组
            - target_price (float): 套利方开仓价格
            - target_size (float): 套利方开仓张数
    """
    # 获取配置信息
    config = BybitApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    api_key, secret_key = fetch_api_key(net)  # 获取API Key和Secret Key
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对


    # 查询账户余额
    fund = query_balance(rest_base_url, api_key, secret_key)  # 查询账户余额
    # 计算保证金
    logger.info(f"账户可用保证金余额: {fund}")
    position_fund = float(fund) * POSITION_RISK
    logger.info(f"仓位保证金: {position_fund}")

    # 调整杠杆
    adjust_lever(
        rest_base_url, api_key, secret_key, 
        target_perp, str(POSITION_LEVERAGE)
    )

    # 计算开仓价格
    target_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )  # 获取目标价格

    # 计算开仓数量
    size_decimals = query_symbol_size(rest_base_url, target_perp)  # 获取标的的最小价格变动和最小数量变动
    target_size = set_size(position_fund, POSITION_LEVERAGE, target_price, size_decimals)  # 计算开仓数量
    
    logger.info(
        f"套利方开仓价格: {target_price}, "
        f"套利方开仓数量: {target_size}, "
        f"套利方开仓杠杆: {POSITION_LEVERAGE}"
    )

    # 下单
    place_trade(
        rest_base_url, api_key, secret_key, 
        target_price, side, target_perp, target_size
    )

    return target_price, target_size


def open_position_hedge(net, side, ticker, arb_size):
    """
    Bybit对冲方开仓
    
    Args:
        net (bool): Bybit的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        arb_size (float): 套利方开仓张数
        
    Returns:
        float: 对冲方开仓价格
    """
    # 获取配置信息
    config = BybitApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    api_key, secret_key = fetch_api_key(net)  # 获取API Key和Secret Key
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对

    # 调整杠杆
    adjust_lever(
        rest_base_url, api_key, secret_key, 
        target_perp, str(POSITION_LEVERAGE)
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


def close_position_arb(net, side, ticker):
    """
    Bybit套利方平仓
    
    Args:
        net (bool): Bybit的API URL类型，True为主网，False为测试网
        side (bool): 平仓方向，True为买入平仓，False为卖出平仓
        ticker (str): 目标标的，如"BTC"
        
    Returns:
        int: 操作结果，0表示成功
    """
    # 获取配置信息
    config = BybitApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    api_key, secret_key = fetch_api_key(net)  # 获取API Key和Secret Key
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对

    # 获取当前仓位信息
    open_price, size = query_position(
        base_url=rest_base_url,
        api_key=api_key, secret_key=secret_key,
        symbol=target_perp
    )
    
    # 计算平仓价格
    target_price = asyncio.run(
        retrieve_price(ws_base_url, target_perp, side)
    )

    logger.info(
        f"套利方平仓价格: {target_price}, "
        f"套利方平仓数量: {size}, "
        f"套利方平仓方向: {side}"
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
    """Binance对冲方平仓
    
    Args:
        net (bool): Bybit的API URL类型，True为主网，False为测试网
        side (bool): 平仓方向，True为买入平仓，False为卖出平仓
        ticker (str): 目标标的，如"BTC"
        arb_open_price (float): 套利方开仓价格
        arb_close_price (float): 套利方平仓价格
        
    Returns:
        int: 操作结果，0表示成功
    """
    # 获取配置信息
    config = BybitApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL
    api_key, secret_key = fetch_api_key(net)  # 获取API Key和Secret Key
    target_perp = ticker+"USDT"  # 根据ticker构建出目标perp的币对

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


if __name__ == "__main__":
    # 示例用法
    print("<==== Testing Bybit Perp Trade ====>")
    # open_position_arb(False, True, "BTC")
    close_position_arb(False, False, "BTC")
    print("<==== Testing Bybit Perp Trade End ====>")