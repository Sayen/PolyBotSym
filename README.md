# 🧪 PolyBot - Polymarket Strategy Simulator

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-Web%20Dashboard-green?style=for-the-badge&logo=flask)
![Mode](https://img.shields.io/badge/Mode-Paper%20Trading-purple?style=for-the-badge)
![Data](https://img.shields.io/badge/Data-Live%20API-red?style=for-the-badge)

> [!IMPORTANT]
> **THIS IS A SIMULATOR / PAPER TRADING TOOL.**
> * **No Wallet Required:** You do **not** need to connect a crypto wallet or enter private keys.
> * **No Real Funds:** All trading is done with a virtual balance.
> * **Real Data:** The bot uses **LIVE** data from the Polymarket API to simulate how strategies would perform in real-time.

**PolyBot** is a high-performance simulation engine designed to test automated betting strategies on [Polymarket](https://polymarket.com) without financial risk. It treats live market conditions as if they were real trades, tracking PnL (Profit and Loss), ROI, and stop-loss execution in real-time.

---

## ✨ Key Features

### 🎮 Realistic Simulation
* **Paper Trading:** Start with a virtual balance (e.g., $1,000) and test your strategies against live market movements.
* **Live Orderbook Data:** Uses the official Gamma API to fetch real spread, liquidity, and pricing data.
* **Execution Latency:** Simulates realistic scanning intervals to see if your strategy can catch opportunities.

### ⚡ High-Performance Engine
* **Parallel Scanning:** Uses `ThreadPoolExecutor` to scan thousands of markets simultaneously.
* **Connection Pooling:** Implements `requests.Session` for fast data retrieval and TCP connection reuse.
* **Smart Pre-Processing:** Optimizes CPU usage by parsing massive JSON datasets centrally before strategy evaluation.

### 🛡️ Risk Management (Simulated)
* **Stop-Loss Automation:** Simulates selling a position immediately if the price drops below your defined threshold.
* **Ghost Bet Protection:** If a market is deleted or the API fails consistently (404s), the simulator detects the "Ghost Bet" and refunds the virtual cash to your balance automatically.
* **Liquidity Filters:** Ensures strategies only target markets with sufficient volume.

### 📊 Advanced Dashboard
* **Multi-Strategy Support:** Run aggressive and conservative strategies side-by-side.
* **Real-Time Logs:** See exactly why a trade was taken (or rejected) with detailed ROI stats.
* **Live Metrics:** Monitor Virtual Equity, Cash, Open Positions, and Win/Loss Ratios.
* **Dark Mode UI:** Built with Bootstrap 5 for a clean, responsive dark-themed interface.

---

## 🛠️ Installation

### Prerequisites
* Python 3.8 or higher
* pip (Python Package Manager)

### 1. Clone the Repository
```bash
git clone [https://github.com/YOUR_USERNAME/polybot-simulator.git](https://github.com/YOUR_USERNAME/polybot-simulator.git)
cd polybot-simulator
```
### 2. Install Dependencies
```bash
pip install flask requests
```
The dashboard will start automatically. Open your browser and visit: 👉 http://127.0.0.1:5111

## 🐳 Docker Support (e.g., Synology NAS)
This project includes full Docker support for easy deployment on a NAS or server.

### 1. Build & Run
Simply use `docker-compose`:
```bash
docker-compose up -d --build
```

### 2. Access
The dashboard will be available at: 👉 http://YOUR-NAS-IP:5111

### 📝 Persistence
The `docker-compose.yml` mounts the current directory to `/app` inside the container.
* **Strategies:** All data is saved to `polybot_data.json` on your host machine.
* **Updates:** You can edit `polybot.py` locally and restart the container to apply changes.

### ⚙️ Configuration
You can configure and tune strategies directly via the Web UI. Simulation data is saved locally to polybot_data.json.

#### Global Settings (Code Level)
Performance settings can be adjusted in polybot.py:

```python
GLOBAL_CONFIG = {
    "port": 5111,             # Web Interface Port (Changed for Synology compatibility)
    "api_fetch_limit": 3000,  # Max markets to scan per cycle
    "check_interval": 30      # Seconds between scans
}
```
#### Strategy Parameters (UI Level)

| Parameter | Description |
| :--- | :--- |
| **Start Balance** | The virtual amount of cash to start the simulation with. |
| **Min/Max Quote** | Probability range for entry (e.g., 0.90 - 0.98 for high probability bets). |
| **Max Time** | Filter markets by remaining time (e.g., only markets closing in < 30 mins). |
| **Min Liquidity** | Minimum liquidity required in the market to consider a trade. |
| **Stop Loss** | Multiplier (e.g., 0.75 simulates selling if value drops by 25%). |
| **Invest %** | Percentage of virtual balance to use per bet. |

