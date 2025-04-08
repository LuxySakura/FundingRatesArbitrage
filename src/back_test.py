# 回测系统搭建
# 定义回测周期（至少包含牛熊周期）
# 设置初始资金和交易成本（佣金+滑点）
# 实现交易逻辑的代码化
# 示例：使用向量化回测或事件驱动回测

# 基础变量
# - 初始资金
# - 当前总资金
# - 持仓


# 触发时间点
# - 半点时刻 00：30
#    - 计算资金费率操作策略
# - 整点时刻前 1 min
# - 整点时刻 01：00

# TODO 获取流动性数据（主要包括订单簿深度和成交量信息，反映市场的交易活跃度和执行大额订单的能力。）
# - timestamp
# - 订单簿深度
# - 成交量

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os

class FundingRateArbitrageBacktest:
    def __init__(self, initial_capital=10000, commission_rate=0.0005, slippage=0.0002):
        """
        初始化回测系统
        
        参数:
        initial_capital: 初始资金
        commission_rate: 交易手续费率
        slippage: 滑点估计
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.positions = {}  # 持仓情况
        self.trades = []     # 交易记录
        self.equity_curve = []  # 资金曲线
        
    def load_data(self, funding_rate_file, price_data_file):
        """
        加载历史数据
        
        参数:
        funding_rate_file: 资金费率数据文件路径
        price_data_file: 价格数据文件路径
        """
        # 加载资金费率数据
        self.funding_rates = pd.read_csv(funding_rate_file, parse_dates=['timestamp'])
        
        # 加载价格数据
        self.price_data = pd.read_csv(price_data_file, parse_dates=['timestamp'])
        
        # 确保数据按时间排序
        self.funding_rates.sort_values('timestamp', inplace=True)
        self.price_data.sort_values('timestamp', inplace=True)
        
        print(f"数据加载完成: 资金费率数据 {len(self.funding_rates)} 条, 价格数据 {len(self.price_data)} 条")
        
    def calculate_funding_rate_spread(self):
        """计算不同交易所之间的资金费率差异"""
        # 根据实际数据结构调整此函数
        exchanges = self.funding_rates['exchange'].unique()
        
        spreads = []
        timestamps = []
        
        # 获取所有时间点
        all_timestamps = self.funding_rates['timestamp'].unique()
        
        for ts in all_timestamps:
            ts_data = self.funding_rates[self.funding_rates['timestamp'] == ts]
            
            # 如果在该时间点有多个交易所的数据
            if len(ts_data['exchange'].unique()) > 1:
                # 计算最高和最低资金费率之间的差异
                max_rate = ts_data['funding_rate'].max()
                min_rate = ts_data['funding_rate'].min()
                
                max_exchange = ts_data[ts_data['funding_rate'] == max_rate]['exchange'].iloc[0]
                min_exchange = ts_data[ts_data['funding_rate'] == min_rate]['exchange'].iloc[0]
                
                spread = max_rate - min_rate
                
                spreads.append({
                    'timestamp': ts,
                    'spread': spread,
                    'long_exchange': min_exchange,  # 资金费率低的交易所做多
                    'short_exchange': max_exchange  # 资金费率高的交易所做空
                })
                timestamps.append(ts)
        
        self.funding_spreads = pd.DataFrame(spreads)
        return self.funding_spreads
    
    def generate_signals(self, threshold=0.001):
        """
        生成交易信号
        
        参数:
        threshold: 资金费率差异阈值，超过此值才考虑交易
        """
        if not hasattr(self, 'funding_spreads'):
            self.calculate_funding_rate_spread()
            
        signals = []
        
        for _, row in self.funding_spreads.iterrows():
            if row['spread'] > threshold:
                # 当资金费率差异超过阈值时生成信号
                signals.append({
                    'timestamp': row['timestamp'],
                    'action': 'OPEN',
                    'long_exchange': row['long_exchange'],
                    'short_exchange': row['short_exchange'],
                    'spread': row['spread']
                })
            elif row['spread'] < threshold * 0.5:  # 当差异缩小到阈值一半以下时平仓
                signals.append({
                    'timestamp': row['timestamp'],
                    'action': 'CLOSE',
                    'spread': row['spread']
                })
                
        self.signals = pd.DataFrame(signals)
        return self.signals
    
    def execute_backtest(self, position_size=0.2):
        """
        执行回测
        
        参数:
        position_size: 每次交易使用的资金比例
        """
        if not hasattr(self, 'signals'):
            self.generate_signals()
            
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = [{
            'timestamp': self.price_data['timestamp'].iloc[0],
            'equity': self.capital
        }]
        
        for _, signal in self.signals.iterrows():
            timestamp = signal['timestamp']
            
            # 获取该时间点的价格数据
            current_prices = self.price_data[self.price_data['timestamp'] <= timestamp].iloc[-1]
            
            if signal['action'] == 'OPEN' and not self.positions:
                # 开仓
                trade_amount = self.capital * position_size
                
                # 计算交易成本
                commission = trade_amount * self.commission_rate * 2  # 两边交易
                slippage_cost = trade_amount * self.slippage * 2
                total_cost = commission + slippage_cost
                
                # 记录交易
                self.trades.append({
                    'timestamp': timestamp,
                    'action': 'OPEN',
                    'long_exchange': signal['long_exchange'],
                    'short_exchange': signal['short_exchange'],
                    'amount': trade_amount,
                    'cost': total_cost,
                    'spread': signal['spread']
                })
                
                # 更新持仓
                self.positions = {
                    'entry_time': timestamp,
                    'long_exchange': signal['long_exchange'],
                    'short_exchange': signal['short_exchange'],
                    'amount': trade_amount,
                    'entry_spread': signal['spread']
                }
                
                # 更新资金
                self.capital -= total_cost
                
            elif signal['action'] == 'CLOSE' and self.positions:
                # 平仓
                entry_time = self.positions['entry_time']
                exit_time = timestamp
                
                # 计算持有期间的资金费率收益
                # 找出持有期间的所有资金费率结算点
                funding_settlements = self.funding_rates[
                    (self.funding_rates['timestamp'] > entry_time) & 
                    (self.funding_rates['timestamp'] <= exit_time)
                ]
                
                funding_profit = 0
                for _, settlement in funding_settlements.iterrows():
                    if settlement['exchange'] == self.positions['long_exchange']:
                        # 做多方收取/支付资金费率
                        funding_profit -= settlement['funding_rate'] * self.positions['amount']
                    elif settlement['exchange'] == self.positions['short_exchange']:
                        # 做空方收取/支付资金费率 (相反)
                        funding_profit += settlement['funding_rate'] * self.positions['amount']
                
                # 计算交易成本
                commission = self.positions['amount'] * self.commission_rate * 2  # 平仓两边交易
                slippage_cost = self.positions['amount'] * self.slippage * 2
                total_cost = commission + slippage_cost
                
                # 计算总收益
                total_profit = funding_profit - total_cost
                
                # 记录交易
                self.trades.append({
                    'timestamp': timestamp,
                    'action': 'CLOSE',
                    'profit': total_profit,
                    'funding_profit': funding_profit,
                    'cost': total_cost,
                    'holding_period': (exit_time - entry_time).total_seconds() / 3600  # 小时
                })
                
                # 更新资金
                self.capital += self.positions['amount'] + total_profit
                
                # 清空持仓
                self.positions = {}
            
            # 更新资金曲线
            self.equity_curve.append({
                'timestamp': timestamp,
                'equity': self.capital
            })
        
        # 转换为DataFrame
        self.equity_curve = pd.DataFrame(self.equity_curve)
        self.trades = pd.DataFrame(self.trades)
        
        return self.equity_curve, self.trades
    
    def calculate_metrics(self):
        """计算回测绩效指标"""
        if len(self.trades) == 0:
            return {
                'total_return': 0,
                'annualized_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0
            }
        
        # 计算总收益率
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        
        # 计算年化收益率
        start_date = self.equity_curve['timestamp'].iloc[0]
        end_date = self.equity_curve['timestamp'].iloc[-1]
        years = (end_date - start_date).total_seconds() / (365 * 24 * 3600)
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 计算夏普比率 (假设无风险利率为0)
        daily_returns = self.equity_curve['equity'].pct_change().dropna()
        sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if len(daily_returns) > 0 else 0
        
        # 计算最大回撤
        equity = self.equity_curve['equity'].values
        max_dd = 0
        peak = equity[0]
        
        for value in equity:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        
        # 计算胜率
        if 'profit' in self.trades.columns:
            win_trades = self.trades[self.trades['profit'] > 0]
            win_rate = len(win_trades) / len(self.trades) if len(self.trades) > 0 else 0
        else:
            win_rate = 0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_dd,
            'win_rate': win_rate
        }
    
    def plot_results(self):
        """绘制回测结果图表"""
        if not hasattr(self, 'equity_curve') or len(self.equity_curve) == 0:
            print("没有回测数据可供绘图")
            return
        
        plt.figure(figsize=(14, 10))
        
        # 绘制资金曲线
        plt.subplot(2, 1, 1)
        plt.plot(self.equity_curve['timestamp'], self.equity_curve['equity'])
        plt.title('资金曲线')
        plt.xlabel('日期')
        plt.ylabel('资金')
        plt.grid(True)
        
        # 绘制资金费率差异
        if hasattr(self, 'funding_spreads'):
            plt.subplot(2, 1, 2)
            plt.plot(self.funding_spreads['timestamp'], self.funding_spreads['spread'])
            plt.title('资金费率差异')
            plt.xlabel('日期')
            plt.ylabel('差异')
            plt.grid(True)
        
        plt.tight_layout()
        plt.show()
        
        # 保存图表
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')
        os.makedirs(output_dir, exist_ok=True)
        plt.savefig(os.path.join(output_dir, f'backtest_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'))
        
    def save_results(self):
        """保存回测结果到CSV文件"""
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存资金曲线
        if hasattr(self, 'equity_curve'):
            self.equity_curve.to_csv(os.path.join(output_dir, f'equity_curve_{timestamp}.csv'), index=False)
        
        # 保存交易记录
        if hasattr(self, 'trades'):
            self.trades.to_csv(os.path.join(output_dir, f'trades_{timestamp}.csv'), index=False)
        
        # 保存资金费率差异
        if hasattr(self, 'funding_spreads'):
            self.funding_spreads.to_csv(os.path.join(output_dir, f'funding_spreads_{timestamp}.csv'), index=False)
        
        # 保存绩效指标
        metrics = self.calculate_metrics()
        pd.DataFrame([metrics]).to_csv(os.path.join(output_dir, f'metrics_{timestamp}.csv'), index=False)
        
        print(f"回测结果已保存到 {output_dir} 目录")


# 使用示例
if __name__ == "__main__":
    # 初始化回测系统
    backtest = FundingRateArbitrageBacktest(
        initial_capital=100000,  # 10万初始资金
        commission_rate=0.0004,  # 0.04%手续费
        slippage=0.0001          # 0.01%滑点
    )
    
    # 加载数据 (需要替换为实际数据文件路径)
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    backtest.load_data(
        funding_rate_file=os.path.join(data_dir, 'funding_rates.csv'),
        price_data_file=os.path.join(data_dir, 'prices.csv')
    )
    
    # 计算资金费率差异
    spreads = backtest.calculate_funding_rate_spread()
    print(f"找到 {len(spreads)} 个资金费率差异点")
    
    # 生成交易信号
    signals = backtest.generate_signals(threshold=0.0008)  # 0.08%的差异阈值
    print(f"生成 {len(signals)} 个交易信号")
    
    # 执行回测
    equity_curve, trades = backtest.execute_backtest(position_size=0.3)  # 使用30%资金
    
    # 计算绩效指标
    metrics = backtest.calculate_metrics()
    print("\n回测绩效指标:")
    for key, value in metrics.items():
        print(f"{key}: {value:.4f}")
    
    # 绘制结果
    backtest.plot_results()
    
    # 保存结果
    backtest.save_results()