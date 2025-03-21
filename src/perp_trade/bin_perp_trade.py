import websockets
import asyncio
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
from src.utils import set_price, set_size, ExchangeApiConfig

# 获取logger实例
logger = setup_logger('HyperliquidTrading')

# 实现Binance交易平台API配置类
class BinanceApiConfig(ExchangeApiConfig):
    def _setup_urls(self):
        """设置Binance的REST和WebSocket URL"""
        if self.type:  # 主网
            self.rest_url = "https://fapi.binance.com"
            self.ws_url = "wss://ws-fapi.binance.com/ws-fapi/v1"
        else:  # 测试网
            self.rest_url = "https://testnet.binancefuture.com"
            self.ws_url = "wss://fstream.binancefuture.com"


# 基础全局变量
MAIN_REST_BASEURL = "https://fapi.binance.com"
TEST_REST_BASEURL = "https://testnet.binancefuture.com"
MAIN_WS_BASEURL = "wss://ws-fapi.binance.com/ws-fapi/v1"
TEST_WS_BASEURL = "wss://fstream.binancefuture.com"


def fetch_api_key():
    """
    从config.json文件中获取对应的API Key
    """
    return ""


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


def generate_sign(api_secret, params):
    """
    生成签名，签名使用HMAC SHA256算法. 
    API-KEY所对应的API-Secret作为 HMAC SHA256 的密钥，
    其他所有参数作为HMAC SHA256的操作对象，得到的输出即为签名。
    
    Input:
        api_secret: API-Secret密钥
        params: 需要签名的参数字典
    Output:
        签名字符串
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


async def retrieve_price(base_url, symbol, side):
    """
    获取 mark_price 数据
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
                        decimal_places = len(price_str.split('.')[1])
                    
                    # 计算最小价格变动
                    min_price_movement = 10 ** (-decimal_places)
                    
                    # 计算目标价格
                    target_price = set_price(price, side, min_price_movement)
                    logger.info(f"目标价格: {target_price}")
                else:
                    logger.error(f"API请求失败: 状态码 {data['status']}, 响应: {data}")

                break
            except json.JSONDecodeError:
                logger.error("Received message is not valid JSON")
        
        await websocket.close()
    return target_price


async def place_trade(base_url, api_key, price, side, symbol, size):
    """
    下单
    """
    side_enum = "BUY" if side else "SELL"
    timestamp = int(time.time() * 1000)

    params = {
        "apikey": api_key,
        "symbol": symbol,
        "side": side_enum,
        "type": "LIMIT",
        "quantity": size,
        "price": price,
        "timeInForce": "GTC",
        "timestamp": timestamp,
    }

    # 生成签名
    signature = generate_sign(api_key, params)
    # 将签名添加到参数中
    params["signature"] = signature

    async with websockets.connect(base_url) as websocket:
        # 发送订阅消息
        subscribe_message = {
            "id": str(uuid.uuid4()),  # 使用uuid生成随机字符串作为id
            "method": "order.place",
            "params": params
        }
        await websocket.send(json.dumps(subscribe_message))

        # 接收并处理消息
        while True:
            try:
                message = await websocket.recv()
                data = json.loads(message)  # 假设消息是JSON格式

                if data['status'] == 200:
                    logger.info(f"下单成功: {data}")
                else:
                    logger.error(f"API请求失败: 状态码 {data['status']}, 响应: {data}")

                break
            except json.JSONDecodeError:
                logger.error("Received message is not valid JSON")
        
        await websocket.close()
    return 0


def open_position_arb(net, side, ticker):
    """
    Binance 开仓

    """
    config = BinanceApiConfig(net)  # 构建对应网络的API配置

    target_perp = ticker+"USDC"  # 根据ticker构建出目标perp的币对
    target_price = asyncio.run(
        retrieve_price(config.get_ws_url(), target_perp, side)
    )
    
    # TODO 调整目标标的杠杆
    lever = 5
    url = config.get_rest_url() + '/fapi/v1/leverage'
    headers = {
        'X-MBX-APIKEY': fetch_api_key(),
    }
    body = {
        'symbol': target_perp,
        'leverage': lever,
    }
    res = requests.post(
        url,  
        data=json.dumps(body)
    )
    logger.info(res)
    # TODO 获取目标标的张数

    # TODO 下单
    return 0


def open_position_hedge(net, side, ticker, arb_size):
    return 0


def close_position_arb(net, side, ticker):
    return 0


def close_position_hedge(net, side, ticker, arb_open_price, arb_close_price):
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
# timeInForce 有效方法 YES
#   GTC - Good Till Cancel 成交为止（下单后仅有1年有效期，1年后自动取消）
#   IOC - Immediate or Cancel 无法立即成交(吃单)的部分就撤销
#   FOK - Fill or Kill 无法全部立即成交就撤销
#   GTX - Good Till Crossing 无法成为挂单方就撤销
#   GTD - Good Till Date 在特定时间之前有效，到期自动撤销
# [

# 调整开仓杠杆 API: POST /fapi/v1/leverage
# "symbol": 交易对
# "leverage": 目标杠杆倍数
if __name__ == "__main__":
    print("Price: ")