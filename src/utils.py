from abc import ABC, abstractmethod

POSITION_RISK = 0.01  # 风险度，每次开仓的保证金占比
POSITION_LEVERAGE = 5  # 开仓杠杆

# 创建交易平台API配置的抽象基类
class ExchangeApiConfig(ABC):
    def __init__(self, is_mainnet=True):
        """
        初始化交易平台API配置
        
        Args:
            is_mainnet (bool): 是否使用主网，True为主网，False为测试网
        """
        self.type = is_mainnet
        self._setup_urls()
    
    @abstractmethod
    def _setup_urls(self):
        """设置REST和WebSocket URL，由子类实现"""
        pass
    
    def get_rest_url(self):
        """获取REST API的基础URL"""
        return self.rest_url
    
    def get_ws_url(self):
        """获取WebSocket的基础URL"""
        return self.ws_url
    
    def is_mainnet(self):
        """检查当前配置是否为主网"""
        return self.type


# 该文件为常用的辅助函数
def set_price(price, side, min_base_price):
    """
    根据当前获取的价格，开单方向以及最小i多的最小价格变动单位，计算开单价格
    做多 需要 价格略低; 做空 需要 价格略高
    side为布尔值: True表示做多(相当于1), False表示做空(相当于-1)
    
    Args:
        price (str): 当前市场订单簿最优价格
        side (bool): 开仓方向
        min_base_price (str): 最小价格变动单位
        
    Returns:
        float: 目标价格
    """
    # 将布尔值side转换为1或-1
    side_value = 1 if side else -1
    return price - 100*min_base_price*side_value


def set_size(amount, leverage, price, decimals):
    """
    获取目标开仓张数

    Args:
        amount (float): 保证金额
        leverage (int): 开仓杠杆
        price (float): 开仓价格
        decimal (int): szDecimals

    Returns:
        target_size (float): 开仓张数
    """
    # 获取目标开仓张数
    _target_size = (amount*leverage) / price  # 张数 = （保证金*杠杆）/开仓价格
    print(f"raw target_size: {_target_size}")
    # 根据szDecimals规范化大小
    _target_size = round(_target_size, int(decimals))
    # 转换为字符串，确保精度正确
    _target_size_str = f"{{:.{decimals}f}}".format(_target_size)
    # 转回浮点数，去除多余的0
    _target_size = float(_target_size_str)
    return _target_size