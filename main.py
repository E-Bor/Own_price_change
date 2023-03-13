import asyncio
import collections
import aiohttp
from decimal import getcontext, Decimal
import numpy as np
from sklearn.linear_model import LinearRegression

getcontext().prec = 10


class CheckRealCostChangeAPP:
    """Application class that monitors the change in its own price ETHUSDT"""
    def __init__(self):
        self.GET_URL = "wss://fstream.binance.com/stream?streams=btcusdt@markPrice@1s/ethusdt@markPrice@1s"
        self.GET_HISTORY_URL = "https://fapi.binance.com/fapi/v1/trades"
        self.BTC_VALS = collections.deque(maxlen=3600)
        self.ETH_VALS = collections.deque(maxlen=3600)
        self.BTC_PROF = collections.deque(maxlen=3600)
        self.ETH_PROF = collections.deque(maxlen=3600)
        self.ETH_CHANGE_LIST = collections.deque(maxlen=3600)

        self.coins = {"BTCUSDT": self.BTC_VALS, "ETHUSDT": self.ETH_VALS}
        self.profitability = {"BTCUSDT": self.BTC_PROF, "ETHUSDT": self.ETH_PROF}
        asyncio.run(self.__init_task_group_create())

    # A function that creates 2 tasks for getting transaction histories ETHUSDT and BTCUSDT
    async def __init_task_group_create(self):
        async with asyncio.TaskGroup() as tg:
            get_btc_usdt_history = tg.create_task(self.__get_history(self.GET_HISTORY_URL, "BTCUSDT"))
            get_btc_usdt_history = tg.create_task(self.__get_history(self.GET_HISTORY_URL, "ETHUSDT"))

    # Get request to api to get the history of operations
    async def __get_history(self, url: str, symbol: str) -> None:
        params = {"symbol": f"{symbol}", "limit": "1000"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                response = await resp.json()
                length = len(response)
                for i in range(length):
                    if i >= 1:
                        self.profitability.get(f"{symbol}").append(
                            self.__calc_profitability(response[i-1]["price"], response[i]["price"]))
                self.coins.get(f"{symbol}").append(response[-1]["price"])

    # Calculate or recalculate a linear regression model, predict a value.
    def __calc_predict(self, value: Decimal) -> Decimal:
        x_train = np.array(self.BTC_PROF).reshape((-1, 1))
        y_train = np.array(self.ETH_PROF)
        model = LinearRegression().fit(x_train, y_train)
        return Decimal(model.predict(np.array([value]).reshape((-1, 1)))[0])

    # Calculating profitability based on new value and previous
    def __calc_profitability(self, old: str, new: str) -> Decimal:
        return (Decimal(new)/Decimal(old)) - Decimal(1)

    # Calculation of own price increase ETHUSDT and accumulation of changes
    def __calc_clear_change(self) -> None:
        btc_old, eth_old = self.BTC_VALS[-2], self.ETH_VALS[-2]
        btc_new, eth_new = self.BTC_VALS[-1], self.ETH_VALS[-1]
        profitability_btc = self.__calc_profitability(btc_old, btc_new)
        profitability_eth = self.__calc_profitability(eth_old, eth_new)
        self.BTC_PROF.append(profitability_btc)
        self.ETH_PROF.append(profitability_eth)
        eth_clear_change = profitability_eth - self.__calc_predict(profitability_btc)
        self.ETH_CHANGE_LIST.append(eth_clear_change)
        percent_change = (Decimal(sum(self.ETH_CHANGE_LIST)) * Decimal(100)) / Decimal(self.ETH_VALS[0])
        if abs(percent_change) >= 1:
            print(f"Own price value of ETHUSDT has changed for the last hour by more than 1%: {percent_change}")

    # Creating a web socket connection to get the price "BTCUSDT, ETHUSDT" every second
    async def __create_websocket_with_binance(self, url: str) -> None:
        counter_btc = 0
        counter_eth = 0
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        message = msg.json()
                        self.coins.get(f"{message['data']['s']}").append(message['data']['p'])
                        if message['data']['s'] == "ETHUSDT":
                            counter_eth += 1
                        if message['data']['s'] == "BTCUSDT":
                            counter_btc += 1
                        if counter_btc and counter_eth:
                            self.__calc_clear_change()
                            counter_eth, counter_btc = 0, 0

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print("connection error")

    # Method to launch the application
    def run(self) -> None:
        asyncio.run(self.__create_websocket_with_binance(self.GET_URL))


if __name__ == "__main__":
    try:
        print("Program started")
        app = CheckRealCostChangeAPP()
        app.run()
    except KeyboardInterrupt:
        print("Program stopped")
