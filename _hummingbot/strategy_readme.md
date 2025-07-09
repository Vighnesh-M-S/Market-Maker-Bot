
# 🧠 Custom Hummingbot Market Making Strategy: Trend + Volatility + Inventory-Aware PMM

## 📄 Overview
This strategy extends the classic Passive Market Making (PMM) approach in Hummingbot by integrating **volatility-based spreads**, **trend signals**, and **inventory management** for smarter and more adaptive trading.

---

## 🚀 Strategy Highlights

| Feature | Benefit | Impact |
|--------|---------|--------|
| 📈 Volatility-based spreads | Dynamically adjusts spread width based on market risk | Prevents overtrading in choppy markets |
| 📊 Trend detection | Favors tighter spread on trend-following side | Improves trade entry in trending markets |
| 🛡️ Inventory management | Adjusts quote spread based on portfolio exposure | Helps maintain target allocation and avoid overexposure |

---

## ⚙️ Strategy Parameters (Sample)
```python
exchange: binance_paper_trade
trading_pair: ETH-USDT
order_amount: 0.05
order_refresh_time: 15 seconds
price_source: mid / last
```
---

## 🔄 Order Placement Logic (Flow)

┌────────────────────────────┐
│        Bot Starts          │
└────────────┬───────────────┘
             ▼
    Initialize config & markets
             ▼
        start candles
             ▼
     ┌──────────────────┐
     │   on_tick() loop │
     └────────┬─────────┘
              ▼
     cancel_all_orders()
              ▼
     create_proposal()
              ▼
       ┌───────────────┐
       │ Market signal │
       ├───────────────┤
       │ - Volatility  │
       │ - Trend       │
       │ - Inventory   │
       └───────────────┘
              ▼
  adjust_proposal_to_budget()
              ▼
        place_orders()
              ▼
      Wait until next tick
              ▼
      Repeat on_tick() cycle


---

## 🧮 Key Logic Explained

### 1. Volatility Calculation
- The strategy fetches 1-minute OHLCV candles using Hummingbot's internal CandlesFactory.
- It accesses the closing prices from the candles DataFrame (candles_df['close']).
- Computes standard deviation (stdev) over the last N close prices (~30).
- This measures price variability over the given time window.
- Higher standard deviation = more volatile market.
- Volatility is normalized by dividing the standard deviation by the latest close price:
- This yields a unitless ratio (like 0.0025), expressing volatility as a % of the price.
- The normalized volatility is scaled and bounded
- Purpose:
    When volatility is low, use a tight spread (~0.1%).
    When volatility is high, widen the spread up to 1%.

Logic

├── 1️⃣ Volatility Signal
│   ├── Purpose: Adjust spread width based on market choppiness
│   ├── Source: Standard deviation of candle closes over N periods
│   ├── Logic:
│   │   ├── Get last 30 candle closes
│   │   ├── Compute standard deviation (stddev)
│   │   ├── Normalize: volatility = stddev / last close price
│   │   └── spread_multiplier = clamp(volatility * 5, min=0.001, max=0.01)
│   └── Use: 
│       - Higher volatility → Wider spreads (less aggressive)
│       - Lower volatility → Tighter spreads (more aggressive)


### 2. Trend Detection
- A trend is a directional movement of price over a recent time window (e.g., 5–15 mins).

  - Uptrend: Series of higher closes.
  - Downtrend: Series of lower closes.
  - Sideways: No strong directional movement.

- The bot checks if recent price closes are:

  - Increasing → Uptrend
  - Decreasing → Downtrend
  - Mixed or flat → Neutral

- It may use simple price slopes or moving averages.

Logic

├── 2️⃣ Trend Signal
│   ├── Purpose: Bias quote placement toward market direction
│   ├── Source: Moving average slope or crossover
│   ├── Logic:
│   │   ├── Get candle closes
│   │   ├── Compute:
│   │   │   ├── short_term_avg = average(closes[-5:])
│   │   │   └── long_term_avg = average(closes[-20:])
│   │   └── If short > long → "uptrend"
│   │       If short < long → "downtrend"
│   │       Else → "neutral"
│   └── Use:
│       - Uptrend:
│           • Tighter buy (aggressive)
│           • Wider sell (conservative)
│       - Downtrend:
│           • Tighter sell (aggressive)
│           • Wider buy (conservative)
│       - Neutral:
│           • Spread multiplier based pricing

### 3. Inventory Ratio Logic
- To maintain a target ratio of base vs quote asset (e.g., 50/50 or 60/40), while adapting spreads based on current portfolio imbalance.
- Measures how much of your total portfolio value is held in the base asset.

    Inventory Ratio = (Base Balance × Price) / (Base Value + Quote Balance)

- Base-heavy: Inventory Ratio > Target (e.g., holding too much ETH)
- Quote-heavy: Inventory Ratio < Target (e.g., holding too much USDT)

├── 3️⃣ Inventory Signal
│   ├── Purpose: Keep base/quote ratio near a desired target (e.g., 50/50)
│   ├── Source: Wallet balances + reference price
│   ├── Logic:
│   │   ├── base_value = base_balance * ref_price
│   │   ├── total_value = base_value + quote_balance
│   │   ├── inventory_ratio = base_value / total_value
│   │   ├── inventory_diff = inventory_ratio - target_base_ratio
│   │   └── spread_adjustment = inventory_diff * 0.02
│   └── Use:
│       - If you're holding *too much base*, widen buy spread (reduce buys)
│       - If you're holding *too much quote*, widen sell spread (reduce sells)
│       - Helps maintain neutrality and reduce exposure risk


---

## Market Signal Flow Diagram (create_proposal() Logic):

┌─────────────────────────────┐
│  Start: Fetch Exchange Data │
└────────────┬────────────────┘
             ↓
┌──────────────────────────────────────────┐
│  Get base_asset and quote_asset symbols  │
└────────────┬─────────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  Get Balances and Ref Price (Mid)   │
│  - base_balance                     │
│  - quote_balance                    │
│  - ref_price                        │
└────────────┬────────────────────────┘
             ↓
┌───────────────────────────────────────┐
│  Calculate Inventory Ratio            │
│  base_value = base_balance * price    │
│  total_value = base_value + quote     │
│  inventory_ratio = base / total       │
└────────────┬──────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│  ❗ Exposure Limit Check             │
│  (If ratio < 10% or > 90%)          │  → Skip order placement --| 
│                                     │                           |
└────────────┬────────────────────────┘                           |
             ↓                                                    |
┌────────────────────────────────────────┐                        |
│  📈 Detect Trend                       │                        |
│  - uptrend → target_base_ratio = 0.65 │                         |
│  - downtrend → target_base_ratio = 0.35│                        |
│  - neutral → target_base_ratio = 0.50 │                         |
└────────────┬───────────────────────────┘                        |
             ↓                                                    |
┌──────────────────────────────────────────────┐                  |
│  🧮 Spread Adjustment (Inventory-based)       │                 |
│  inventory_diff = inventory_ratio - target   │                  |
│  spread_adjustment = diff × 0.02             │                  |
└────────────┬─────────────────────────────────┘                  |
             ↓                                                    |
┌───────────────────────────────────────────────┐                 |
│  🌪️ Volatility-based Spread                  │                  |
│  - Calculate stdev of last 30 closes         │                  |
│  - raw_spread = clamp(volatility × 5)        │                  |
└────────────┬──────────────────────────────────┘                 |
             ↓                                                    |
┌───────────────────────────────────────────────┐                 |
│  🔄 Smooth Spread Transition (EMA)            │                 |
│  spread_multiplier =                         │                  |
│    alpha × raw + (1-alpha) × prev_multiplier │                  |
└────────────┬──────────────────────────────────┘                 |
             ↓                                                    |
┌────────────────────────────────────────────┐                    |
│  💸 Calculate Final Buy/Sell Prices        │                    |
│  - Based on trend                         │                     |
│  - Or use: ref_price ± spread ± adjust    │                     |
└────────────┬───────────────────────────────┘                    |
             ↓                                                    |
┌─────────────────────────────────────────────┐                   |
│  ✂️ Price Clipping                          │                   |
│  - Cap deviation to ±3% from mid price     │                    |
└────────────┬────────────────────────────────┘                   |
             ↓                                                    |
┌─────────────────────────────────────────────┐                   |
│  ⚠️ Inventory Imbalance Filter              │  → Skip           |
│  (If inv_ratio < 15% or > 85%)              │     |             |
└────────────┬────────────────────────────────┘     |             |
             ↓                                      |             |
┌─────────────────────────────────────────────┐     |             |
│  ✅ Create and Return Order Candidates       │    |             |
└─────────────────────────────────────────────┘     |             |
             ↑                                      |             |
             │ <------------------------------------              |  
      (Wait refresh_time)                                         |  
             │ <--------------------------------------------------
             └────────── Back to Start 🔁

## 📊 Sample `format_status()` Output



---

## 🎥 Video Demo

📌 _Insert YouTube/Drive link to your demo recording_

---

## 📂 Folder Structure

```
hummingbot/
│-Scripts
├── new_pmm.py  # Strategy logic with trend, volatility, and inventory logic
|
|-Conf
|--Scripts        
├──- conf_new_pmm_1.yml           # Config file with trading pair, spread, etc.
├── README.md            # ← This file

```

---



