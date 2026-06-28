# TraderBot v5 — Scalp Grid Bot

A clean-slate scalping bot. No rectangle drawing needed — the bot
places a symmetric buy + sell limit grid around the current 1M candle
close price and closes everything the moment a profit target is hit.

---

## Strategy

```
Last 1M candle close → anchor price
         │
         ▼
  SELL LIMIT #10  ← anchor + dist + 9×step
  SELL LIMIT #9   ← anchor + dist + 8×step
  ...
  SELL LIMIT #1   ← anchor + dist
                     ─── anchor price ───
  BUY LIMIT  #1   ← anchor - dist
  ...
  BUY LIMIT  #9   ← anchor - dist - 8×step
  BUY LIMIT  #10  ← anchor - dist - 9×step
         │
         ▼
  Monitor every 1 second
         │
         ├─ Total floating profit ≥ session target → close all, STOP
         └─ Session time limit reached             → close all, STOP
```

---

## GUI Settings

| Setting        | Default | Description                                     |
|----------------|---------|-------------------------------------------------|
| Distance       | 5 pips  | Gap from anchor to nearest order                |
| Step           | 1 pip   | Gap between consecutive orders in the grid      |
| Count          | 10      | Number of buy orders AND sell orders            |
| Lot Size       | 0.01    | Volume per order                                |
| Profit Target  | 2%      | % of balance to trigger close-all               |
| Time Limit     | 1 min   | Max session duration before close-all           |

---

## Quick Start

### Prerequisites
- MetaTrader 5 (Windows)
- Python 3.11

### Install
```bash
pip install -r requirements.txt
```

### Configure
Edit `config.py` with your MT5 credentials and default settings.

### Run
```bash
python gui.py
```

---

## Project Structure

```
traderbotv5/
├── core/
│   ├── __init__.py
│   └── grid_engine.py     ← grid placement + session monitor
├── gui.py                 ← PyQt5 GUI entry point
├── config.py              ← all defaults
├── requirements.txt
└── README.md
```

---

## Notes
- All settings are adjustable in the GUI before each session
- The bot uses `MAGIC_NUMBER = 554433` to tag its own orders
- Only positions/orders with the matching magic number are managed
- MT5 filling mode is auto-detected per symbol (FOK / IOC / RETURN)