import logging
import os
from decimal import Decimal
from typing import Dict, List
from pydantic import Field
from statistics import stdev

from hummingbot.client.config.config_data_types import BaseClientModel
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory, CandlesConfig


class SimplePMMConfig(BaseClientModel):
    script_file_name: str = os.path.basename(__file__)
    exchange: str = Field("binance_paper_trade")
    trading_pair: str = Field("ETH-USDT")
    order_amount: Decimal = Field(0.05)
    bid_spread: Decimal = Field(0.001)
    ask_spread: Decimal = Field(0.001)
    order_refresh_time: int = Field(15)
    price_type: str = Field("mid")


class SimplePMM(ScriptStrategyBase):
    create_timestamp = 0
    price_source = PriceType.MidPrice

    @classmethod
    def init_markets(cls, config: SimplePMMConfig):
        cls.markets = {config.exchange: {config.trading_pair}}
        cls.price_source = PriceType.LastTrade if config.price_type == "last" else PriceType.MidPrice

    def __init__(self, connectors: Dict[str, ConnectorBase], config: SimplePMMConfig):
        super().__init__(connectors)
        self.config = config

        # Initialize candles for volatility
        self.candles = CandlesFactory.get_candle(CandlesConfig(
            connector="binance",
            trading_pair=config.trading_pair,
            interval="1m",
            max_records=1000
        ))
        self.candles.start()

    def on_stop(self):
        self.candles.stop()

    def on_tick(self):
        if self.create_timestamp <= self.current_timestamp:
            self.cancel_all_orders()
            proposal = self.create_proposal()
            proposal_adjusted = self.adjust_proposal_to_budget(proposal)
            self.place_orders(proposal_adjusted)
            self.create_timestamp = self.config.order_refresh_time + self.current_timestamp

    def create_proposal(self) -> List[OrderCandidate]:
        ref_price = self.connectors[self.config.exchange].get_price_by_type(
            self.config.trading_pair, self.price_source
        )

        volatility = self.calculate_volatility()
        spread_multiplier = max(Decimal("0.001"), min(volatility * Decimal("5"), Decimal("0.01")))

        buy_price = ref_price * (Decimal(1) - spread_multiplier)
        sell_price = ref_price * (Decimal(1) + spread_multiplier)

        return [
            OrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT,
                order_side=TradeType.BUY,
                amount=self.config.order_amount,
                price=buy_price,
            ),
            OrderCandidate(
                trading_pair=self.config.trading_pair,
                is_maker=True,
                order_type=OrderType.LIMIT,
                order_side=TradeType.SELL,
                amount=self.config.order_amount,
                price=sell_price,
            )
        ]

    def calculate_volatility(self, length: int = 30) -> Decimal:
        try:
            df = self.candles.candles_df
            if df is None or len(df) < length:
                self.logger().info("Not enough candle data to calculate volatility.")
                return Decimal("0.0")

            closes = df["close"].iloc[-length:]
            stddev = Decimal(str(stdev(closes)))
            last_price = Decimal(str(closes.iloc[-1]))
            return stddev / last_price
        except Exception as e:
            self.logger().warning(f"Volatility calculation failed: {str(e)}")
            return Decimal("0.0")

    def adjust_proposal_to_budget(self, proposal: List[OrderCandidate]) -> List[OrderCandidate]:
        return self.connectors[self.config.exchange].budget_checker.adjust_candidates(proposal, all_or_none=True)

    def place_orders(self, proposal: List[OrderCandidate]):
        for order in proposal:
            self.place_order(self.config.exchange, order)

    def place_order(self, connector_name: str, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(connector_name, order.trading_pair, order.amount, order.order_type, order.price)
        else:
            self.buy(connector_name, order.trading_pair, order.amount, order.order_type, order.price)

    def cancel_all_orders(self):
        for order in self.get_active_orders(self.config.exchange):
            self.cancel(self.config.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        msg = (
            f"{event.trade_type.name} {round(event.amount, 2)} {event.trading_pair} "
            f"{self.config.exchange} at {round(event.price, 2)}"
        )
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)

    def format_status(self) -> str:
        lines = []

        try:
            ref_price = self.connectors[self.config.exchange].get_price_by_type(
                self.config.trading_pair, self.price_source
            )
            volatility = self.calculate_volatility()
            spread_multiplier = max(Decimal("0.001"), min(volatility * Decimal("5"), Decimal("0.01")))

            buy_price = ref_price * (Decimal(1) - spread_multiplier)
            sell_price = ref_price * (Decimal(1) + spread_multiplier)

            lines.append("📊 Strategy Status:")
            lines.append(f"  Exchange        : {self.config.exchange}")
            lines.append(f"  Trading Pair    : {self.config.trading_pair}")
            lines.append(f"  Ref Price       : {round(ref_price, 2)}")
            lines.append(f"  Volatility (30) : {round(volatility * 100, 4)}%")
            lines.append(f"  Spread Mult     : {round(spread_multiplier * 100, 4)}%")
            lines.append(f"  Buy Price       : {round(buy_price, 2)}")
            lines.append(f"  Sell Price      : {round(sell_price, 2)}")
        except Exception as e:
            lines.append(f"⚠️ Error fetching price info: {e}")

        try:
            # Add wallet balances
            lines.append("\n💰 Balances:")
            balance_df = self.get_balance_df()
            lines.extend(["  " + line for line in balance_df.to_string(index=False).split("\n")])
        except Exception as e:
            lines.append(f"⚠️ Error fetching balances: {e}")

        try:
            # Add current active orders
            active_orders = self.active_orders_df()
            if not active_orders.empty:
                lines.append("\n📑 Active Orders:")
                lines.extend(["  " + line for line in active_orders.to_string(index=False).split("\n")])
            else:
                lines.append("\n📑 No active orders.")
        except Exception as e:
            lines.append(f"⚠️ Error fetching active orders: {e}")

        return "\n".join(lines)
