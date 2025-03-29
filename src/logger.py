import logging
import os
from datetime import datetime

def setup_logger(name='FundingRatesArbitrage'):
    """
    配置并返回logger实例
    """
    # 创建logs文件夹（如果不存在）
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 生成日志文件名（包含时间戳）
    log_filename = os.path.join(log_dir, f'{name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

    # 创建logger实例
    logger = logging.getLogger(name)
    
    # 如果logger已经有处理器，说明已经被配置过，直接返回
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.INFO)

    # 创建文件处理器
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 创建格式器
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加处理器到logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger