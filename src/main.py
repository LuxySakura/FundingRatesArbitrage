from info_fetch import fetch_funding_rates
from logger import setup_logger
from sys import path as sys_path
from os import path as os_path
# 添加项目根目录到系统路径，确保可以导入src目录下的模块
sys_path.append(os_path.dirname((os_path.dirname(__file__))))
import src.perp_trade.bin_perp_trade as bin_perp_trade
import src.perp_trade.okx_perp_trade as okx_perp_trade
import src.perp_trade.hl_perp_trade as hl_perp_trade
import src.perp_trade.bybit_perp_trade as bybit_perp_trade

# 创建logger实例
logger = setup_logger()

def func_manager():
    """
    为步骤赋予执行的具体时刻，方便计时器在循环过程中触发
    支持两种执行模式：
    1. 每四小时执行一次
    2. 在奇数时刻(1,3,5,7)执行
    
    返回下一个需要执行的时间点列表
    """
    from datetime import datetime, timedelta

    # 获取当前时间
    now = datetime.now()
    
    # 计算下一个四小时时间点
    current_hour = now.hour
    next_four_hour = now.replace(minute=0, second=0, microsecond=0)
    hours_to_add = 4 - (current_hour % 4) if current_hour % 4 != 0 else 4
    next_four_hour += timedelta(hours=hours_to_add)
    
    # 计算下一个奇数时刻(1,3,5,7)
    odd_hours = [1, 3, 5, 7]
    current_hour = now.hour
    current_day = now.day
    
    # 找出今天剩余的奇数时刻
    next_odd_hours = [h for h in odd_hours if h > current_hour]
    
    if next_odd_hours:
        # 今天还有奇数时刻
        next_odd_hour = now.replace(hour=next_odd_hours[0], minute=0, second=0, microsecond=0)
    else:
        # 今天没有剩余奇数时刻，取明天的第一个
        next_odd_hour = now.replace(hour=odd_hours[0], minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    # 确定下一个执行时间点（取最近的一个）
    next_execution = min(next_four_hour, next_odd_hour)
    
    # 资金费率信息获取时刻：10min Before
    t_fr_fetch = next_execution - timedelta(minutes=10)
    # 开仓时刻：1min Before
    t_open = next_execution - timedelta(minutes=1)
    # 平仓时刻：5s After
    t_close = next_execution + timedelta(seconds=5)
    
    # 记录计算出的下一个执行时间点
    logger.info(f"计算得到下一个执行时间点: {next_execution}, 类型: {'四小时整点' if next_execution == next_four_hour else '奇数时刻'}")
    logger.debug(f"资金费率获取时间: {t_fr_fetch}, 开仓时间: {t_open}, 平仓时间: {t_close}")
    
    return t_fr_fetch, t_open, t_close, next_execution

def main_loop():
    import time
    from datetime import datetime, timedelta

    ticker = ""  # 套利标的
    arb_obj = {}
    hedge_obj = {}
    
    # 记录上一次执行的时间点，避免重复执行
    last_execution = None
    
    logger.info("套利程序主循环启动")

    while True:
        # 获取下一轮需要执行的时间点
        t_fr_fetch, t_open, t_close, next_execution = func_manager()
        
        # 获取当前时间
        now = datetime.now()
        
        # 如果已经执行过当前时间点的操作，则等待下一个时间点
        if last_execution and (next_execution - last_execution).total_seconds() < 60:
            logger.debug(f"已执行过当前时间点的操作，等待下一个时间点")
            time.sleep(10)  # 等待10秒后再检查
            continue
        
        # 检查是否到达各个时间点
        # 允许10秒误差
        if now >= t_fr_fetch and now < t_fr_fetch + timedelta(seconds=10):
            logger.info(f"执行资金费率获取 - 目标时间点: {next_execution}")
            # TODO: 调用资金费率获取函数
            try:
                fetch_funding_rates()
                logger.info("资金费率获取成功")
            except Exception as e:
                logger.error(f"资金费率获取失败: {str(e)}")
            
        elif now >= t_open and now < t_open + timedelta(seconds=10):
            logger.info(f"执行开仓操作 - 目标时间点: {next_execution}")
            # TODO: 套利方开仓
            # TODO: 对冲方开仓
            try:
                # 这里添加开仓逻辑
                logger.info("开仓操作执行成功")
            except Exception as e:
                logger.error(f"开仓操作执行失败: {str(e)}")
            
        elif now >= t_close and now < t_close + timedelta(seconds=10):
            logger.info(f"执行平仓操作 - 目标时间点: {next_execution}")
            # TODO: 调用平仓函数
            try:
                # 这里添加平仓逻辑
                logger.info("平仓操作执行成功")
            except Exception as e:
                logger.error(f"平仓操作执行失败: {str(e)}")
                
            last_execution = next_execution  # 记录已执行的时间点
            logger.info(f"完成当前时间点({next_execution})的所有操作")
            
        # 休眠1秒
        time.sleep(1)

if __name__ == '__main__':
    """
    整个套利项目主程序
    """
    logger.info("=== 套利程序启动 ===")
    # try:
    #     main_loop()
    # except KeyboardInterrupt:
    #     logger.info("程序被用户中断")
    # except Exception as e:
    #     logger.error(f"程序异常退出: {str(e)}", exc_info=True)
    # finally:
    #     logger.info("=== 套利程序结束 ===")
    # open_price, open_size = hl_perp_trade.open_position_arb(
    #     net=True, side=False, ticker="GAS"
    # )
    # logger.info(f"套利方开仓价格: {open_price}, 开仓张数: {open_size}")

    # hedge_open_price = bin_perp_trade.open_position_hedge(
    #     net=True, side=True, ticker="GAS", arb_size=7.1
    # )
    # logger.info(f"对冲方开仓价格: {hedge_open_price}, 开仓张数: ")

    # arb_close_price = hl_perp_trade.close_position_arb(
    #     net=True, side=True, ticker="GAS"
    # )

    bin_perp_trade.close_position_hedge(
        net=True, side=False, ticker="GAS", 
        arb_open_price=2.5383, arb_close_price=2.4899
    )



    