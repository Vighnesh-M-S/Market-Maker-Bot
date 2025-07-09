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

        self.target_base_ratio = Decimal("0.5")

    # def on_stop(self):
    #     self.cancel_all_orders()
        
    #     self.candles.stop()

    #     self.logger().info(f"🛑 Strategy stopped. All orders cancelled for {self.config.trading_pair}.")

    def on_tick(self):
        if self.create_timestamp <= self.current_timestamp:
            self.cancel_all_orders()
            proposal = self.create_proposal()
            proposal_adjusted = self.adjust_proposal_to_budget(proposal)
            self.place_orders(proposal_adjusted)
            self.create_timestamp = self.config.order_refresh_time + self.current_timestamp
            

    def create_proposal(self) -> List[OrderCandidate]:
        connector = self.connectors[self.config.exchange]
        base_asset, quote_asset = self.config.trading_pair.split("-")

        # Balances and ref price
        base_balance = Decimal(connector.get_balance(base_asset))
        quote_balance = Decimal(connector.get_balance(quote_asset))
        ref_price = connector.get_price_by_type(self.config.trading_pair, self.price_source)

        # Inventory value and ratio
        base_value = base_balance * ref_price
        total_value = base_value + quote_balance
        inventory_ratio = base_value / total_value if total_value > 0 else Decimal("0.5")

        # === 1. Exposure Limits ===
        max_exposure = Decimal("0.90")
        if inventory_ratio < (1 - max_exposure) or inventory_ratio > max_exposure:
            self.logger().warning("❌ Exposure too high, skipping order placement.")
            return []

        # === 2. Trend & Target Inventory Ratio ===
        self.trend = self.detect_trend()
        if self.trend == "uptrend":
            self.target_base_ratio = Decimal("0.65")
        elif self.trend == "downtrend":
            self.target_base_ratio = Decimal("0.35")
        else:
            self.target_base_ratio = Decimal("0.5")

        # === 3. Spread Adjustment Based on Inventory ===
        inventory_diff = inventory_ratio - self.target_base_ratio
        spread_adjustment = inventory_diff * Decimal("0.02")

        # === 4. Volatility-based Spread ===
        volatility = self.calculate_volatility()
        raw_spread = max(Decimal("0.001"), min(volatility * Decimal("5"), Decimal("0.01")))

        # === 5. Smooth Spread Transition ===
        if not hasattr(self, "prev_spread_multiplier"):
            self.prev_spread_multiplier = raw_spread
        smoothing_alpha = Decimal("0.2")
        spread_multiplier = (
            smoothing_alpha * raw_spread + (Decimal("1") - smoothing_alpha) * self.prev_spread_multiplier
        )
        self.prev_spread_multiplier = spread_multiplier

        # === 6. Final Buy/Sell Prices ===
        if self.trend == "uptrend":
            buy_price = ref_price * Decimal("0.9995")
            sell_price = ref_price * Decimal("1.002")
        elif self.trend == "downtrend":
            buy_price = ref_price * Decimal("0.998")
            sell_price = ref_price * Decimal("1.0015")
        else:
            buy_price = ref_price * (Decimal("1") - spread_multiplier + spread_adjustment)
            sell_price = ref_price * (Decimal("1") + spread_multiplier + spread_adjustment)

        # === 7. Price Clipping ===
        clip_limit = Decimal("0.03")  # max 3% deviation from mid
        buy_price = max(ref_price * (1 - clip_limit), min(buy_price, ref_price * (1 + clip_limit)))
        sell_price = min(ref_price * (1 + clip_limit), max(sell_price, ref_price * (1 - clip_limit)))

        # === 8. Imbalance Filter ===
        if inventory_ratio < Decimal("0.15") or inventory_ratio > Decimal("0.85"):
            self.logger().info("⚠️ Inventory imbalance too high, skipping order placement.")
            return []

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
        
    def detect_trend(self, fast: int = 5, slow: int = 20) -> str:
        """
        Detects trend direction based on moving average crossover.
        Returns: "uptrend", "downtrend", or "sideways"
        """
        try:
            df = self.candles.candles_df
            if df is None or len(df) < slow:
                return "sideways"

            closes = df["close"]
            ma_fast = closes.rolling(window=fast).mean().iloc[-1]
            ma_slow = closes.rolling(window=slow).mean().iloc[-1]

            if ma_fast > ma_slow:
                return "uptrend"
            elif ma_fast < ma_slow:
                return "downtrend"
            else:
                return "sideways"
        except Exception as e:
            self.logger().warning(f"Trend detection failed: {str(e)}")
            return "sideways"

    def inventory_ratio(self):
        base = self.connectors[self.config.exchange].get_balance("ETH")
        quote = self.connectors[self.config.exchange].get_balance("USDT")
        price = self.connectors[self.config.exchange].get_price(self.config.trading_pair)
        base_value = base * price
        total_value = base_value + quote
        return base_value / total_value if total_value > 0 else Decimal("0")

    def adjust_spreads_based_on_inventory(self, base_ratio: Decimal):
        """
        Adjust spread to encourage balancing:
        - If too much ETH → sell aggressively
        - If too much USDT → buy aggressively
        """
        if base_ratio > Decimal("0.6"):  # too much ETH, widen buy spread
            return Decimal("0.002"), Decimal("0.0005")
        elif base_ratio < Decimal("0.4"):  # too much USDT, widen sell spread
            return Decimal("0.0005"), Decimal("0.002")
        else:  # balanced
            return Decimal("0.001"), Decimal("0.001")

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
            connector = self.connectors[self.config.exchange]
            base_asset, quote_asset = self.config.trading_pair.split("-")

            base_balance = Decimal(connector.get_balance(base_asset))
            quote_balance = Decimal(connector.get_balance(quote_asset))
            ref_price = self.connectors[self.config.exchange].get_price_by_type(
                self.config.trading_pair, self.price_source
            )
            base_value = base_balance * ref_price
            total_value = base_value + quote_balance

            inventory_ratio = base_value / total_value if total_value > 0 else Decimal("0.5")

            volatility = self.calculate_volatility()
            trend = getattr(self, "trend", "neutral")
            spread_multiplier = max(Decimal("0.001"), min(volatility * Decimal("5"), Decimal("0.01")))
            inventory_diff = inventory_ratio - self.target_base_ratio
            spread_adjustment = inventory_diff * Decimal("0.02")

            if trend == "uptrend":
                buy_price = ref_price * (Decimal("1") - spread_multiplier * Decimal("0.5"))
                sell_price = ref_price * (Decimal("1") + spread_multiplier * Decimal("1.5"))
            elif trend == "downtrend":
                buy_price = ref_price * (Decimal("1") - spread_multiplier * Decimal("1.5"))
                sell_price = ref_price * (Decimal("1") + spread_multiplier * Decimal("0.5"))
            else:
                buy_price = ref_price * (Decimal(1) - spread_multiplier + spread_adjustment)
                sell_price = ref_price * (Decimal(1) + spread_multiplier + spread_adjustment)

            lines.append("📊 Strategy Status:")
            lines.append(f"  Exchange        : {self.config.exchange}")
            lines.append(f"  Trading Pair    : {self.config.trading_pair}")
            lines.append(f"  Ref Price       : {round(ref_price, 2)} USDT")
            lines.append(f"📍 Trend Detected: {trend.capitalize()}")
            lines.append(f"  Volatility (normalized): {volatility:.5f}")
            lines.append(f"  Inventory Ratio (Base): {inventory_ratio:.4%}")
            lines.append(f"  Spread Mult     : {round(spread_multiplier * 100, 4)}%")
            lines.append(f"  Base Balance: {base_balance:.4f} {base_asset}")
            lines.append(f"  Quote Balance: {quote_balance:.2f} {quote_asset}")
            lines.append(f"  Buy Price       : {round(buy_price, 2)}")
            lines.append(f"  Sell Price      : {round(sell_price, 2)}")
           
            lines.append(f"📦 Order Size: {self.config.order_amount} {self.config.trading_pair.split('-')[0]}")

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
