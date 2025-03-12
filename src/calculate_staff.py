import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.use('TkAgg')

U_FUND = 2000  # 初始USDT资金量
TON_AMOUNT = 100  # 初始TON数量
CEX_USDT_TRANSFER = 0.15  # CEX上提U的网络费用
CEX_TON_TRANSFER = 0.01  # Transfer Fee(TON)


def plot_staff(df):
    # 2. 计算 margin = buy - sell
    df['margin'] = df['buy'] - df['sell']
    df['marginRate'] = (df['margin'] / df['sell']) * 100

    margin_median = df['marginRate'].median()
    print(f'Median Margin: {margin_median:.2f}% ')

    # 计算中位数
    median_time = df['Time (ms)'].median()
    print(f'Median Execution Time: {median_time:.2f} ms')

    # 3. 创建两幅子图
    fig, (ax1, ax2) = plt.subplots(1, 2)  # 2 行 1 列的子图布局

    # 4. 绘制第一幅图：margin 折线图
    ax1.plot(df['Iteration'], df['marginRate'], marker='o', linestyle='-', color='b', label='Margin')
    ax1.set_title('Margin (Buy - Sell) Over Time')
    ax1.set_xlabel('Index (Record Number)')
    ax1.set_ylabel('Margin')
    ax1.legend()
    ax1.grid(True)

    ax2.violinplot(df['Time (ms)'])
    ax2.set_title('Execution Time')
    ax2.set_xlabel('Index (Record Number)')
    ax2.set_ylabel('Exec Time (ms)')
    ax2.legend()
    ax2.grid(True)

    # 显示图表
    plt.show()


# 根据实际测算的CEX和DEX数据绘制对应的arbitrage plot
def plot_arbitrage(df):
    # 计算DEX上买和卖的差值
    df['margin'] = df['DexBuy'] - df['DexSell']
    df['marginRate'] = (df['margin'] / df['DexBuy']) * 100

    # 判断是否存在套利机会
    # df['arbitrage'] = arbitrage_search(dex_sell=df['DexSell'], dex_buy=df['DexBuy'], cex=df['CexPrice'])
    # 统计套利点的数目
    # total_num = len(df['arbitrage'])
    # arb_num = total_num - (df['arbitrage'] == 0).sum()
    # arb_rate = arb_num / total_num
    # print("Total Treat Point Num:", arb_num, "Treat Point Rate:", arb_rate)
    #

    # 3. 创建两幅子图
    fig, (ax1, ax2) = plt.subplots(1, 2)  # 2 行 1 列的子图布局

    # 第一幅图绘制折线图，X为记录Index，Y为对应三种不同的价格
    ax1.plot(df['Iteration'], df['DexSell'], marker='.', linestyle='-', color='black', label='DexSell')
    ax1.plot(df['Iteration'], df['DexBuy'], marker='.', linestyle='-', color='blue', label='DexBuy')
    ax1.plot(df['Iteration'], df['CexPrice'], marker='.', linestyle='-', color='red', label='CEX')
    ax1.set_title('Price Variation')
    ax1.set_xlabel('Index (Record Number)')
    ax1.set_ylabel('Price(TON/USDT)')
    ax1.legend()
    ax1.grid(True)

    # 第二幅图
    # ave_profit = 0.009  # 每个TON下套利的利润
    # fund_series = np.linspace(start=0, stop=FUND, num=10000)
    # price = np.linspace(start=2, stop=10, num=1000)
    # loss = 0.0186*price + CEX_TON_TRANSFER * price
    # profit = ave_profit * (FUND / price) * 0.999 - loss

    ax2.scatter(df['Iteration'], df['arbitrage'])
    ax2.set_title('Arbitrage Point')
    ax2.set_xlabel('Index (Record Number)')
    ax2.set_ylabel('Treat Point')
    ax2.grid(True)

    # 显示图表
    plt.show()


if __name__ == '__main__':
    file_path = './data/funding_data.csv'  # CSV 文件路径
    data = pd.read_csv(file_path)  # 读取数据

    res = data['maxFR'].abs().max() - 0.003
    print("Max Funding Rate:", res)
    res_index = data['maxFR'].abs().idxmax()
    res_record = data.loc[res_index]

    day_rate = res * 6 + abs(res_record['HlFR']) * 18

    print(res_record)
    print("Current Max Funding Rate(Per Hour):", res, "%")
    print("Estimated Max Funding Rate(Per Day):", day_rate, "%")
    print("Estimated Max Funding Rate(Per Year):", day_rate * 365, "%")
    print("Profit Per Day:", 7.3 * day_rate * U_FUND/100, "￥")
