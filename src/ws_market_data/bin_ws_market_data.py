import websockets
import asyncio
import json
# Base URL: wss://fstream.binance.com
# 多个streams链接 wss://fstream.binance.com/stream?streams=bnbusdt@aggTrade/btcusdt@markPrice
# 服务端每3分钟会发送ping帧，客户端应当在10分钟内回复pong帧，否则服务端会主动断开链接。允许客户端发送不成对的pong帧(即客户端可以以高于15分钟每次的频率发送pong帧保持链接)。

MARGIN_RATE = 0.1


async def connet():
    base_uri = "wss://fstream.binance.com/ws/"
    mark_price_stream = "kaitousdt@markPrice"
    kline_stream = "kaitousdt@kline_1m"

    uri = base_uri + kline_stream
    # {
    #     "e": "markPriceUpdate", // 事件类型
    # "E": 1562305380000, // 事件时间
    # "s": "BTCUSDT", // 交易对
    # "p": "11794.15000000", // 标记价格
    # "i": "11784.62659091", // 现货指数价格
    # "P": "11784.25641265", // 预估结算价, 仅在结算前最后一小时有参考价值
    # "r": "0.00038167", // 资金费率
    # "T": 1562306400000 // 下次资金时间
    # }

    while True:  # 外层循环，确保连接中断后重连
        try:
            print("Connecting to WebSocket server...")
            async with websockets.connect(uri) as websocket:
                # 订阅消息（如果需要）
                # await websocket.send(json.dumps({"action": "subscribe", "channel": "your_channel"}))

                # 内层循环，持续接收消息
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)  # 假设消息是JSON格式

                        # price = data['p']  # 标记价格
                        high_p = float(data['k']['h'])  # 1min K线最高价
                        low_p = float(data['k']['l'])  # 1min K线最低价

                        rate = 200*(high_p - low_p)/(high_p + low_p)

                        print(f"Received variation rate: {rate}%")
                    except json.JSONDecodeError:
                        print("Received message is not valid JSON")
                    except websockets.ConnectionClosed:
                        print("WebSocket connection closed, reconnecting...")
                        break  # 退出内层循环，重新连接
        except Exception as e:
            print(f"An error occurred: {e}")
            await asyncio.sleep(5)  # 等待5秒后重试

if __name__ == "__main__":
    asyncio.run(connet())
