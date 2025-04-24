"""
该脚本实现在OKX上进行合约开单操作

描述:
    主要功能包括：
    - 套利方开仓/平仓
    - 对冲方开仓/平仓
    - 价格获取和订单管理

作者: Luxy
创建日期: 25/03/24
版本: 1.0.0
"""

import websockets
import requests
import json
import asyncio
import time  # 添加time模块导入
from sys import path as sys_path
from os import path as os_path

# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logger import setup_logger
# 导入工具模块
from src.utils import set_price, set_size, ExchangeApiConfig, POSITION_RISK, POSITION_LEVERAGE

# 获取logger实例
logger = setup_logger('OKXTrading')

# 实现okx交易平台API配置类
# 注意：模拟盘的请求的header里面需要添加 "x-simulated-trading: 1"。
class OKXApiConfig(ExchangeApiConfig):
    def _setup_urls(self):
        """设置Binance的REST和WebSocket URL"""
        if self.type:  # 主网
            self.rest_url = "https://www.okx.com"
            self.ws_url = "wss://ws.okx.com:8443/ws/v5"
        else:  # 测试网
            self.rest_url = "https://www.okx.com"
            self.ws_url = "wss://wspap.okx.com:8443/ws/v5"

# Content-Type: application/json
# OK-ACCESS-KEY: 37c541a1-****-****-****-10fe7a038418
# OK-ACCESS-SIGN: leaVRETrtaoEQ3yI9qEtI1CZ82ikZ4xSG5Kj8gnl3uw=
# OK-ACCESS-PASSPHRASE: 1****6
# OK-ACCESS-TIMESTAMP: 2020-03-28T12:21:41.274Z
# x-simulated-trading: 1

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

    passphrase = _config["okx_passphrase"]
    if net:
        _api_key = _config["okx_api_key"]
        _secret_key = _config["okx_secret_key"]
    else:
        _api_key = _config["okx_testnet_api_key"]
        _secret_key = _config["okx_testnet_secret_key"]

    return _api_key, _secret_key, passphrase


def generate_timestamp():
    """
    生成时间戳，为ISO格式，如2020-12-08T09:08:57.715Z
    """
    from datetime import datetime, timezone
    
    # 使用 datetime.now(timezone.utc) 替代已弃用的 datetime.utcnow()
    dt = datetime.now(timezone.utc)
    # 格式化为ISO 8601标准格式
    timestamp = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    
    return timestamp


def generate_sign(secret_key, timestamp, method, request_path, body):
    """
    生成签名

    OK-ACCESS-SIGN的请求头是对timestamp + method + requestPath + body字符串（+表示字符串连接），以及SecretKey，
    使用HMAC SHA256方法加密，通过Base-64编码输出而得到的。

    Args:
        secret_key (str): 币安API密钥对应的私钥
        timestamp (str): 时间戳，格式为ISO 8601标准格式，如2020-12-08T09:08:57.715Z
        method (str): 请求方法，如GET、POST等
    Returns:
        str: 签名
    """
    import hmac
    import base64
    import hashlib

    # 构建待签名的字符串
    message = timestamp + method + request_path
    
    # 根据请求方法不同，处理body的方式不同
    if method == 'GET':
        # GET请求：将body参数转换为查询字符串格式
        if body:
            query_string = '?' + '&'.join([f"{key}={value}" for key, value in body.items()])
            message += query_string
    else:
        message += body
    
    # 使用HMAC SHA256算法进行加密
    mac = hmac.new(
        bytes(secret_key, encoding='utf8'),
        bytes(message, encoding='utf8'),
        digestmod=hashlib.sha256
    )
    
    # 对加密结果进行Base64编码
    signature = base64.b64encode(mac.digest()).decode('utf8')
    
    return signature


def query_balance(base_url, api_key, secret_key, passphrase):
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
    request_path = '/api/v5/account/balance'
    timestamp = generate_timestamp()
    body = {
        'ccy': 'USDT'
    }

    sign = generate_sign(secret_key, timestamp, method, request_path, body)

    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }
    
    # 使用GET请求而不是POST
    res = requests.get(
        url,
        headers=headers,
        params=body  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        # 查找asset为USDT的元素
        data = data['data'][0]['details'][0]
        balance = float(data['availBal'])
        logger.info(f"API请求成功，账户余额: {balance}")
        return balance
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1


def query_contract_specs(base_url, symbol):
    """
    获取交易合约的最小下单数量/合约面值/合约乘数数据
    
    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
        passphrase (str): OKX API密钥对应的Passphrase
        
    Returns:
        tuple: 包含合约面值和合约乘数的元组
            - decimal_places (int): 小数位数
            - ctVal (float): 合约面值
            - ctMult (float): 合约乘数
    """

    method = 'GET'
    request_path = '/api/v5/public/instruments'

    body = {
        'instType': 'SWAP',
        'instId': symbol
    }

    url = base_url + request_path
    
    # 使用GET请求而不是POST
    res = requests.get(
        url,  
        params=body  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        contract_data = data['data'][0]

        min_size = contract_data['lotSz']
        ct_val = float(contract_data['ctVal'])
        ct_mult = float(contract_data.get('ctMult', 1))  # 默认为1如果不存在

        decimal_part = min_size.split('.')
        decimal_places = len(decimal_part[1]) if len(decimal_part) > 1 else 0
        return decimal_places, ct_val, ct_mult      
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1, -1, -1


def query_position(base_url, api_key, secret_key, passphrase, symbol):
    """
    获取当前持仓信息

    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
    Returns:
        tuple: 包含当前持仓数量和开仓均价的元组
            - pos_size (float): 当前持仓数量
            - entry_price (float): 开仓均价
    """
    method = 'GET'
    request_path = '/api/v5/account/positions'
    timestamp = generate_timestamp()

    body = {
        'instId': symbol
    }

    sign = generate_sign(secret_key, timestamp, method, request_path, body)

    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }
    
    # 使用GET请求而不是POST
    res = requests.get(
        url,
        headers=headers,
        params=body  # 使用params而不是data
    )
    
    if res.status_code == 200:
        data = res.json()
        
        position = data['data'][0]
        pos_size = float(position['pos'])
        entry_price = float(position['avgPx'])
        return entry_price, pos_size
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
        return -1, -1


def adjust_leverage(base_url, api_key, secret_key, passphrase, symbol, leverage):
    """
    调整杠杆

    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
    """
    method = 'POST'
    request_path = '/api/v5/account/set-leverage'
    timestamp = generate_timestamp()
    body = {
        'instId': symbol,
        'lever': str(leverage),
        'mgnMode': 'cross',
    }
    # 将字典转换为JSON字符串
    json_body = json.dumps(body)

    sign = generate_sign(secret_key, timestamp, method, request_path, json_body)

    url = base_url + request_path

    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }

    res = requests.post(
        url,
        headers=headers,
        data=json_body
    )

    if res.status_code == 200:
        data = res.json()
        logger.info(f"API请求成功，调整杠杆成功")
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")


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
    url = base_url + "/public"  # 实际订阅频道
    async with websockets.connect(url) as websocket:
        # 发送订阅消息
        subscribe_message = {
            "op": "subscribe",
            "args": [{
                "channel": "tickers",
                "instId": symbol,
            }]
        }
        await websocket.send(json.dumps(subscribe_message))

        # 接收并处理消息
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)  # 解析JSON消息
                
                # 区分响应消息和推送数据
                if 'event' in data:
                    # 这是响应消息
                    if data['event'] == 'error':
                        logger.error(f"订阅失败: {data.get('arg', {}).get('channel')}")
                        break
                elif 'data' in data:
                    # 这是推送数据
                    price_str = data['data'][0]["last"]  # 提取最新价格
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


def check_order_filled(base_url, api_key, secret_key, passphrase, order_id, symbol):
    """
    检查订单是否已经成功填充
    
    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
        passphrase (str): OKX API密钥对应的Passphrase
        order_id (str): 订单ID
        
    Returns:
        bool: 订单是否已填充
    """
    if order_id == -1:
        return False
        
    method = 'GET'
    request_path = '/api/v5/trade/order'
    timestamp = generate_timestamp()
    
    body = {
        'instId': symbol,
        'ordId': order_id
    }
    
    sign = generate_sign(secret_key, timestamp, method, request_path, body)
    
    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }
    
    res = requests.get(
        url,
        headers=headers,
        params=body
    )
    
    if res.status_code == 200:
        data = res.json()
        if 'data' in data and len(data['data']) > 0:
            order_status = data['data'][0]['state']
            # 订单状态：canceled-已撤销，live-等待成交，partially_filled-部分成交，filled-完全成交
            if order_status == 'filled':
                return True
            elif order_status == 'partially_filled':
                # 部分成交也可以视为成功，具体取决于您的策略
                fill_ratio = float(data['data'][0]['fillSz']) / float(data['data'][0]['sz'])
                logger.info(f"订单部分成交，成交比例: {fill_ratio:.2%}")
                # 如果成交比例超过某个阈值，也可以视为成功
                if fill_ratio > 0.9:  # 例如90%以上视为成功
                    return True
    else:
        logger.error(f"查询订单状态失败: 状态码 {res.status_code}, 响应: {res.text}")
    
    return False


def cancel_order(base_url, api_key, secret_key, passphrase, order_id, symbol):
    """
    取消未成交的订单
    
    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
        passphrase (str): OKX API密钥对应的Passphrase
        order_id (str): 订单ID
        symbol (str): 交易对
        
    Returns:
        bool: 是否成功取消订单
    """
    method = 'POST'
    request_path = '/api/v5/trade/cancel-order'
    timestamp = generate_timestamp()
    
    body = {
        'instId': symbol,
        'ordId': order_id
    }
    
    # 将字典转换为JSON字符串
    json_body = json.dumps(body)
    
    sign = generate_sign(secret_key, timestamp, method, request_path, json_body)
    
    url = base_url + request_path
    
    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }
    
    res = requests.post(
        url,
        headers=headers,
        data=json_body
    )
    
    if res.status_code == 200:
        data = res.json()
        if data.get('code') == '0':
            logger.info(f"成功取消订单: {order_id}")
            return True
        else:
            logger.error(f"取消订单失败: {data.get('msg')}")
    else:
        logger.error(f"取消订单请求失败: 状态码 {res.status_code}, 响应: {res.text}")
    
    return False


def place_trade(base_url, api_key, secret_key, passphrase, symbol, side, price, size):
    """
    下单

    Args:
        base_url (str): OKX API的基础URL
        api_key (str): OKX API密钥
        secret_key (str): OKX API密钥对应的私钥
        passphrase (str): OKX API密钥对应的Passphrase
        symbol (str): 交易对
        side (bool): 交易方向，True为买入，False为卖出
        price (float): 下单价格
        size (float): 下单数量
        
    Returns:
        str: 订单ID，失败时返回-1
    """
    method = 'POST'
    request_path = '/api/v5/trade/order'
    timestamp = generate_timestamp()

    # posSide
    # 持仓方向，买卖模式下此参数非必填，如果填写仅可以选择net；在开平仓模式下必填，且仅可选择 long 或 short。
    # 开平仓模式下，side和posSide需要进行组合
    # 开多：买入开多（side 填写 buy； posSide 填写 long ）
    # 开空：卖出开空（side 填写 sell； posSide 填写 short ）
    # 平多：卖出平多（side 填写 sell；posSide 填写 long ）
    # 平空：买入平空（side 填写 buy； posSide 填写 short ）
    # 组合保证金模式：交割和永续仅支持买卖模式
    body = {
        'instId': symbol,
        'tdMode': 'isolated',
        'ccy': 'USDT',
        'side': 'buy' if side else 'sell',
        'posSide': 'long' if side else'short',
        'ordType': 'limit',
        'px': str(price),
        'sz': str(size),
    }
    # 将字典转换为JSON字符串
    json_body = json.dumps(body)

    sign = generate_sign(secret_key, timestamp, method, request_path, json_body)

    url = base_url + request_path

    headers = {
        'Content-Type': "application/json",
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'x-simulated-trading': "1"  # 代表使用测试网进行测试
    }

    res = requests.post(
        url,
        headers=headers,
        data=json_body
    )

    if res.status_code == 200:
        data = res.json()
        if data.get('code') == '0' and 'data' in data and len(data['data']) > 0:
            order_id = data['data'][0]['ordId']
            logger.info(f"下单成功，订单ID: {order_id}")
            return order_id
        else:
            logger.error(f"下单失败: {data.get('msg')}")
    else:
        logger.error(f"API请求失败: 状态码 {res.status_code}, 响应: {res.text}")
    return -1


def open_position_arb(net, side, ticker):
    """
    OKX 套利方开仓
    
    Args:
        net (bool): OKX的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        
    Returns:
        tuple: 包含开仓价格和开仓数量的元组
            - target_price (float): 套利方开仓价格
            - target_size (float): 套利方开仓张数
    """
    config = OKXApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL

    target_perp = ticker+"-USDT-SWAP"  # 根据ticker构建出目标perp的币对
    
    api_key, secret_key, passphrase = fetch_api_key(net)

    # 查询账户余额
    balance = query_balance(rest_base_url, api_key, secret_key, passphrase)
    # 计算保证金
    position_fund = int(balance * POSITION_RISK)
    logger.info(f"保证金: {position_fund}")

    # 调整杠杆
    adjust_leverage(rest_base_url, api_key, secret_key, passphrase, target_perp, POSITION_LEVERAGE)
    
    # 获取合约规格信息
    # 计算开仓价值
    # 每个合约张数对应的币种数目不同，需要根据合约张数对应的币种数目计算开仓张数
    # 例如，目前使用的是BTC合约，每个合约张数对应的币种数目为0.01
    # 仓位价值 = 合约张数 * 合约面值 * 限价
    # 可开仓价值 = 保证金 × 杠杆倍数
    # 可开仓张数 = 可开仓价值 ÷ (合约面值 × 价格 × 合约乘数)
    size_decimals, ct_val, ct_mult = query_contract_specs(rest_base_url, target_perp)
    position_fund = position_fund / (ct_val * ct_mult)
    
    # 实现订单填充检查和重试逻辑
    max_retries = 10  # 最大重试次数
    retry_interval = 3  # 重试间隔（秒）
    order_id = None
    filled = False
    
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"第 {attempt} 次尝试下单...")
        
        # 计算开仓价格
        target_price = asyncio.run(
            retrieve_price(ws_base_url, target_perp, side)
        )

        # 计算开仓张数
        target_size = set_size(
            amount=position_fund, 
            price=target_price, 
            decimals=size_decimals, 
            leverage=POSITION_LEVERAGE
        )
        logger.info(f"开仓张数: {target_size}")

        # 下单
        order_id = place_trade(
            rest_base_url, 
            api_key, secret_key, passphrase, 
            target_perp, side, target_price, target_size
        )

        # 留出fill订单的时间
        time.sleep(10)
        
        # 检查订单是否成功填充
        filled = check_order_filled(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
        
        if filled:
            logger.info(f"订单已成功填充，订单ID: {order_id}")
            break
        
        # 如果订单未填充，取消订单
        if order_id != -1:
            cancel_order(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
            logger.info(f"订单未填充，已取消订单ID: {order_id}")
        
        # 等待一段时间后重试
        if attempt < max_retries - 1:  # 如果不是最后一次尝试
            logger.info(f"等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
    
    if not filled:
        logger.error(f"达到最大重试次数 {max_retries}，订单仍未成功填充")
        return -1, -1

    # 获取实际成交价格和数量
    entry_price, pos_size = query_position(rest_base_url, api_key, secret_key, passphrase, target_perp)
    logger.info(f"成功开仓，价格: {entry_price}, 数量: {pos_size}")

    return entry_price, pos_size


def open_position_hedge(net, side, ticker, arb_size):
    """OKX对冲方开仓
    
    Args:
        net (bool): OKX的API URL类型，True为主网，False为测试网
        side (bool): 开仓方向，True为买入开仓，False为卖出开仓
        ticker (str): 目标标的，如"BTC"
        arb_size (float): 套利方开仓张数
        
    Returns:
        float: 对冲方开仓价格
    """
    # 获取基础信息
    config = OKXApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL

    target_perp = ticker+"-USDT-SWAP"  # 根据ticker构建出目标perp的币对
    
    api_key, secret_key, passphrase = fetch_api_key(net)

    # 调整目标标的杠杆
    adjust_leverage(rest_base_url, api_key, secret_key, passphrase, target_perp, POSITION_LEVERAGE)

    # 转换OKX张数
    size_decimals, ct_val, ct_mult = query_contract_specs(rest_base_url, target_perp)
    okx_size = arb_size / (ct_val*ct_mult)
    logger.info(f"OKX张数: {okx_size}")

    # 实现订单填充检查和重试逻辑
    max_retries = 10  # 最大重试次数
    retry_interval = 3  # 重试间隔（秒）
    order_id = None
    filled = False
    
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"第 {attempt} 次尝试下单...")
        
        # 计算开仓价格
        target_price = asyncio.run(
            retrieve_price(ws_base_url, target_perp, side)
        )

        # 下单
        order_id = place_trade(
            rest_base_url, 
            api_key, secret_key, passphrase, 
            target_perp, side, target_price, okx_size
        )

        # 留出fill订单的时间
        time.sleep(10)
        
        # 检查订单是否成功填充
        filled = check_order_filled(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
        
        if filled:
            logger.info(f"订单已成功填充，订单ID: {order_id}")
            break
        
        # 如果订单未填充，取消订单
        if order_id != -1:
            cancel_order(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
            logger.info(f"订单未填充，已取消订单ID: {order_id}")
        
        # 等待一段时间后重试
        if attempt < max_retries - 1:  # 如果不是最后一次尝试
            logger.info(f"等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
    
    if not filled:
        logger.error(f"达到最大重试次数 {max_retries}，订单仍未成功填充")
        return -1, -1

    # 获取实际成交价格和数量
    entry_price, pos_size = query_position(rest_base_url, api_key, secret_key, passphrase, target_perp)
    logger.info(f"成功开仓，价格: {entry_price}, 数量: {pos_size}")

    return entry_price, pos_size


def close_position_arb(net, side, ticker):
    """OKX 套利方平仓

    Args:
        net (bool): OKX的API URL类型，True为主网，False为测试网
        side (bool): 平仓方向，True为平多，False为平空
        ticker (str): 目标标的，如"BTC"
    """
    # 获取基础信息
    config = OKXApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL

    target_perp = ticker+"-USDT-SWAP"  # 根据ticker构建出目标perp的币对
    
    api_key, secret_key, passphrase = fetch_api_key(net)

    # 获取仓位信息
    entry_price, pos_size = query_position(
        rest_base_url, 
        api_key, secret_key, passphrase, 
        target_perp
    )

    # 实现订单填充检查和重试逻辑
    max_retries = 10  # 最大重试次数
    retry_interval = 3  # 重试间隔（秒）
    order_id = None
    filled = False
    
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"第 {attempt} 次尝试下单...")
        
        # 计算开仓价格
        target_price = asyncio.run(
            retrieve_price(ws_base_url, target_perp, side)
        )

        # 下单
        order_id = place_trade(
            rest_base_url, 
            api_key, secret_key, passphrase, 
            target_perp, side, target_price, pos_size
        )

        # 留出fill订单的时间
        time.sleep(10)
        
        # 检查订单是否成功填充
        filled = check_order_filled(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
        
        if filled:
            logger.info(f"订单已成功成交，订单ID: {order_id}")
            break
        
        # 如果订单未填充，取消订单
        if order_id != -1:
            cancel_order(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
            logger.info(f"订单未成交，已取消订单ID: {order_id}")
        
        # 等待一段时间后重试
        if attempt < max_retries - 1:  # 如果不是最后一次尝试
            logger.info(f"等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
    
    if not filled:
        logger.error(f"达到最大重试次数 {max_retries}，订单仍未成功填充")
        return -1

    return 0


def close_position_hedge(net, side, ticker, arb_open_price, arb_close_price):
    """OKX 对冲方平仓

    Args:
        net (bool): OKX的API URL类型，True为主网，False为测试网
        side (bool): 平仓方向，True为平多，False为平空
    """
    # 获取基础信息
    config = OKXApiConfig(net)  # 初始化网络信息
    rest_base_url = config.get_rest_url()  # 获取REST API的基础URL
    ws_base_url = config.get_ws_url()  # 获取WebSocket的基础URL

    target_perp = ticker+"-USDT-SWAP"  # 根据ticker构建出目标perp的币对
    
    api_key, secret_key, passphrase = fetch_api_key(net)

    # 获取仓位信息
    hedge_entry_price, hedge_size = query_position(
        rest_base_url, 
        api_key, secret_key, passphrase, 
        target_perp
    )

    # 实现订单填充检查和重试逻辑
    max_retries = 10  # 最大重试次数
    retry_interval = 3  # 重试间隔（秒）
    order_id = None
    filled = False
    
    for attempt in range(max_retries):
        if attempt > 0:
            logger.info(f"第 {attempt} 次尝试下单...")
        
        # 计算开仓价格
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

        # 下单
        order_id = place_trade(
            base_url=rest_base_url,
            api_key=api_key, secret_key=secret_key, passphrase=passphrase,
            price=target_price, side=side,
            symbol=target_perp, size=hedge_size
        )

        # 留出fill订单的时间
        time.sleep(10)
        
        # 检查订单是否成功填充
        filled = check_order_filled(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
        
        if filled:
            logger.info(f"订单已成功填充，订单ID: {order_id}")
            break
        
        # 如果订单未填充，取消订单
        if order_id != -1:
            cancel_order(rest_base_url, api_key, secret_key, passphrase, order_id, target_perp)
            logger.info(f"订单未填充，已取消订单ID: {order_id}")
        
        # 等待一段时间后重试
        if attempt < max_retries - 1:  # 如果不是最后一次尝试
            logger.info(f"等待 {retry_interval} 秒后重试...")
            time.sleep(retry_interval)
    
    if not filled:
        logger.error(f"达到最大重试次数 {max_retries}，订单仍未成功填充")
        return -1

    return 0


if __name__ == "__main__":
    logger.info("OKX 合约下单测试")
    open_position_arb(False, True, "BTC")
    # open_position_hedge(False, True, "BTC", 0.005)
    # close_position_arb(False, False, "BTC")
