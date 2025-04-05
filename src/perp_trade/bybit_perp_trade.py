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
            self.ws_url = "wss://stream.bybit.com"
        else:  # 测试网
            self.rest_url = "https://api-testnet.bybit.com"
            self.ws_url = "wss://stream.bybit.com"


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


if __name__ == "__main__":
    # 示例用法
    print("<==== Testing Bybit Perp Trade ====>")