"""
资金平衡模块，目标是在设定资金策略后，使得套利方和对冲方资金相同
例如，假设账户总资金为10000：
    如果此时套利方-对冲方为HL-BIN，资金在HL-OKX中，那么将资金从OKX中划转至BIN中，并保证两个平台仓位一致
"""
import websockets
import requests
import json
import asyncio
from sys import path as sys_path
from os import path as os_path

# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname(os_path.dirname(os_path.dirname(__file__))))
# 导入日志模块
from src.logger import setup_logger
# 导入工具模块
from src.perp_trade.okx_perp_trader import generate_sign as okx_generate_sign

def okx_login():
    """
    OKX登录
    Returns
        int: 0表示成功，-1表示失败
    """

    return -1


def okx_withdraw(balance, target_address):
    """
    OKX提现
    Args
        balance (str): 提现的资金
        target_address (str): 提现的目标地址
    Returns
        int: 0表示成功，-1表示失败
    """
    return -1


def okx_deposit():
    """
    OKX充值, 获取充币的地址
    Returns
        address (str): 充币的地址
    """
    return -1

def fund_balance(_from, _to):
    """
    资金划转
    :param balance: 账户总资金
    """
    # TODO 获取当前各平台仓位

    # TODO 制定划转策略

    # TODO 执行划转

    return -1