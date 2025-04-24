from abc import ABC, abstractmethod

POSITION_RISK = 0.05  # 风险度，每次开仓的保证金占比
POSITION_LEVERAGE = 2  # 开仓杠杆

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
    return price - 5*min_base_price*side_value


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
    # 根据szDecimals规范化大小
    _target_size = round(_target_size, int(decimals))
    # 转换为字符串，确保精度正确
    _target_size_str = f"{{:.{decimals}f}}".format(_target_size)
    # 转回浮点数，去除多余的0
    _target_size = float(_target_size_str)
    return _target_size


def genearate_history_moments(interval, batch, days):
    """
    生成过去特定时间段内通过API获取历史数据的时间戳节点
    例如，如果要获取过去一周内的数据，由于获取的K线数据的时间间隔为1分钟，
    则需要获取7 * 24 * 60 = 10080个时间戳节点，
    每次最多获取100条，如果每次API获取的时间段为1min * 60，
    需要获取7 * 24次，本函数需要为每一次生成对应的起始时间戳，以便后续调用。
    函数返回一个列表，列表中每个元素为一个元组，元组中包含起始时间戳和结束时间戳。

    Args:
        interval (int): 时间间隔，单位为分钟
        batch (int): 每次API请求获取的记录数
        days (int): 持续天数
    """
    import time
    from datetime import datetime, timedelta
    
    # 设置参数
    max_records_per_request = interval * batch  # 每次API请求获取60条记录
    
    # 计算当前时间并对齐到最近的分钟边界
    current_time = datetime.now().replace(second=0, microsecond=0)
    end_time = current_time
    time_segments = []
    
    # 计算总共需要获取的时间段数量
    total_minutes = days * 24 * 60
    total_segments = total_minutes // max_records_per_request
    if total_minutes % max_records_per_request > 0:
        total_segments += 1
    
    # 生成每个时间段的起始和结束时间戳
    for i in range(total_segments):
        # 计算当前段的结束时间
        if i == 0:
            segment_end_time = end_time
        else:
            segment_end_time = segment_start_time
        
        # 计算当前段的起始时间（确保对齐到分钟边界）
        segment_start_time = segment_end_time - timedelta(minutes=max_records_per_request)
        
        # 转换为时间戳（毫秒）
        start_timestamp = int(segment_start_time.timestamp() * 1000)
        end_timestamp = int(segment_end_time.timestamp() * 1000)
        
        # 添加到结果列表
        time_segments.append((start_timestamp, end_timestamp))
    
    return time_segments