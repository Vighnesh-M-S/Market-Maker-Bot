# 📈 Advanced Simple-PMM Strategy Bot (Hummingbot)

This project is a customized market-making strategy built on top of Hummingbot's `simple_pmm` template. It incorporates enhanced trading logic, including:

- 📊 Volatility-based dynamic spreads
- 📉 Trend detection
- ⚖️ Inventory and risk management
- 🔁 Smooth spread transitions
- 🔒 Exposure limits and price clipping

## 🛠️ Getting Started

### 🔁 Clone the Repository

```bash
git clone https://github.com/Vighnesh-M-S/Market-Maker-Bot
cd your-strategy-repo/Market-Maker-Bot
```
### Clone Hummingbot Repo

```bash
git https://github.com/hummingbot/hummingbot
cd hummingbot
```


### 📁 Folder Structure

```bash
hummingbot/
└── scripts/
    └── new_pmm.py # Your strategy file here
|--- conf/
|------scripts/
|---------conf_new_pmm_1.yml # Yor conf file goes here
```

### ▶️ Run the Strategy

1. Start Hummingbot:
```bash
./start
```

2. In the Hummingbot CLI:
```bash
start -script new_pmm.py -conf conf_new_pmm.py
```

## 🎥 Video Tutorials

   📌  

- 📽️ Strategy Explanation Video
- 🔄 Live Trading Demo

---

### 🤖 Strategy Features

- Dynamically adjusts spreads based on recent volatility (1-minute candle standard deviation).
- Detects short-term price trends to bias quoting direction.
- Applies inventory ratios to avoid asset overexposure.
- Smoothes rapid spread changes for price stability.
- Limits order placements based on exposure and inventory thresholds.

---

Happy Market Making 🚀
