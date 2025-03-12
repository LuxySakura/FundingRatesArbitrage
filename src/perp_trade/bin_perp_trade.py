# 基础全局变量
TEST_REST_BASEURL = "https://testnet.binancefuture.com"
TEST_WS_BASEURL = "wss://fstream.binancefuture.com"


def set_price(_mark_price):
    """
    根据获取来的 mark_price 来设置下单的价格
    """
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

def place_perp_trade(ticker):
    symbol = ticker + "-USDT"  # 构建交易对字符串

    # 构建请求参数
    params = {
        "symbol": symbol,
        "side": "BUY",
        "positionSide": "SHORT",
        "type": "LIMIT",
        "quantity": 0.01,
        "reduceOnly": False,
        "closePosition": False,
        "priceProtect": False,
    }

# 调整开仓杠杆 API: POST /fapi/v1/leverage
# "symbol": 交易对
# "leverage": 目标杠杆倍数
