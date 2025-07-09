
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

👉 _Insert architecture flow diagram here_

---

## 🧮 Key Logic Explained

### 1. Volatility Calculation
- Uses standard deviation of 1-minute candle close prices.
- Normalizes by latest price to compute percentage-based volatility.
- Adjusts base spread dynamically:
  ```python
  spread_multiplier = clamp(volatility * 5, min=0.001, max=0.01)
  ```

### 2. Trend Detection
- If price shows consistent rise/fall over a short window:
  - `uptrend`: tight buy price, wider sell
  - `downtrend`: tight sell price, wider buy

### 3. Inventory Ratio Logic
- Compares quote vs base holdings.
- If base-heavy: widen buy spread, tighten sell.
- If quote-heavy: widen sell spread, tighten buy.

---

## 📊 Sample `format_status()` Output

👉 _Include CLI screenshot of status command output_

---

## 🎥 Video Demo

📌 _Insert YouTube/Drive link to your demo recording_

---

## 📂 Folder Structure

```
custom_strategy/
│
├── strategy.py          # Strategy logic with trend, volatility, and inventory logic
├── config.yml           # Config file with trading pair, spread, etc.
├── README.md            # ← This file
└── assets/              # Screenshots, diagrams, and video links
```

---

## 📬 Contact
For feedback or contributions, reach out to `@your_handle` or submit a pull request.

