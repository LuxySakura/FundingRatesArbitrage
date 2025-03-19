from info_fetch import fetch_funding_rates


def func_manager():
    """
    为步骤赋予执行的具体时刻，方便计时器在循环过程中触发
    例如：
        1. 在整点时刻的 前10min 进行资金费率信息的获取
        2. 在整点时刻的 前1min 根据 最优资金费率策略 进行开仓
        3. 在整点时刻的 后5s 根据 仓位信息 进行平仓 
    """
    from datetime import datetime, timedelta

    # 获取当前时间
    now = datetime.now()
    # 计算下一个整点时刻
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    # 根据整点时刻计算各个步骤的具体时刻
    # 资金费率信息获取时刻：10min Before
    t_fr_fetch = next_hour - timedelta(minutes=10)
    # 开仓时刻：1min Before
    t_open = next_hour - timedelta(minutes=1)
    # 平仓时刻：5s After
    t_close = next_hour + timedelta(seconds=5)
    
    return t_fr_fetch, t_open, t_close

def main_loop():
    import time
    from datetime import datetime

    ticker = ""  # 套利标的
    arb_obj = {}
    hedge_obj = {}

    while True:
        # 获取下一轮需要执行的时间点
        t_fr_fetch, t_open, t_close = func_manager()
        
        # 获取当前时间
        now = datetime.now()
        
        # 检查是否到达各个时间点
        if now >= t_fr_fetch and now < t_fr_fetch + timedelta(seconds=1):
            print("执行资金费率获取")
            # TODO: 调用资金费率获取函数
            fetch_funding_rates()
            
        elif now >= t_open and now < t_open + timedelta(seconds=1):
            print("执行开仓操作")
            # TODO: 套利方开仓
            # TODO: 对冲方开仓
            
        elif now >= t_close and now < t_close + timedelta(seconds=1):
            print("执行平仓操作")
            # TODO: 调用平仓函数
            
        # 休眠1秒
        time.sleep(1)

if __name__ == '__main__':
    """
    整个套利项目主程序
    """
    main_loop()
    