# Market Making Bot Integration

This document describes the integration of the new Polymarket Market Making bot (`polymarket_mm_deliver`) into the Poly Maker system.

## Overview

The new bot is a market-making bot for BTC 15m Up/Down contracts on Polymarket. It:
- Uses shared memory for real-time market data
- Implements two strategies (S1 and S2) with configurable parameters
- Runs in 15-minute time buckets
- Uses WebSocket for order updates and fills

## Architecture

### Bot Components

1. **`main_final.py`**: Main trading loop that runs strategies
2. **`trade.py`**: Data feed that writes market data to shared memory
3. **`state_machine/polymarket_client.py`**: Wrapper around py-clob-client
4. **`config.json`**: All bot parameters (API keys, strategy settings, etc.)

### Backend Integration

1. **`app/services/mm_bot_service.py`**: Service to manage bot lifecycle
   - Start/stop bot processes
   - Load/save configuration
   - Monitor bot status

2. **`app/api/routes/mm_bot.py`**: API endpoints for bot control
   - `POST /mm-bot/start`: Start the bot
   - `POST /mm-bot/stop`: Stop the bot
   - `POST /mm-bot/restart`: Restart the bot
   - `GET /mm-bot/status`: Get bot status
   - `GET /mm-bot/config`: Get configuration
   - `PUT /mm-bot/config`: Update configuration

### Frontend Integration

1. **`web/app/mm-bot/page.tsx`**: UI page for bot control
   - Display bot status
   - Start/stop/restart controls
   - View/edit configuration

2. **`web/lib/api.ts`**: API client functions for MM bot

3. **`web/app/components/Navigation.tsx`**: Navigation between Markets and MM Bot pages

## Configuration

The bot configuration is stored in `polymarket_mm_deliver/polymarket_mm_deliver/config.json`.

### Environment Variables

The bot service automatically updates the config from environment variables:
- `PK`: Private key for signing
- `BROWSER_ADDRESS`: Proxy address (Polymarket proxy)
- `SIGNATURE_TYPE`: Signature type (1 or 2)

### Strategy Configuration

- **Strategy 1 (S1)**: Main market-making strategy
  - Entry thresholds
  - Take profit/stop loss settings
  - Position caps
  - Time windows

- **Strategy 2 (S2)**: Secondary strategy (can be disabled)

## Running the Bot

### Via API

```bash
# Start bot
curl -X POST http://localhost:8000/mm-bot/start

# Check status
curl http://localhost:8000/mm-bot/status

# Stop bot
curl -X POST http://localhost:8000/mm-bot/stop
```

### Via UI

1. Navigate to `/mm-bot` in the web interface
2. Click "Start Bot" to begin trading
3. Monitor status in real-time
4. Use "Stop Bot" or "Restart Bot" as needed

## Dependencies

The bot requires:
- `numpy`: For shared memory operations
- `websocket-client`: For WebSocket connections
- `py-clob-client`: For Polymarket API
- Standard Python libraries (multiprocessing, threading, etc.)

All dependencies are included in `pyproject.toml`.

## Process Management

The bot runs two processes:
1. **trade.py**: Data feed process (writes to shared memory)
2. **main_final.py**: Trading bot process (reads from shared memory and places orders)

Both processes are managed by `mm_bot_service.py` and can be monitored via the status endpoint.

## Notes

- Configuration changes require a bot restart to take effect
- The bot uses shared memory (`poly_tob_shm`) for inter-process communication
- Make sure environment variables (`PK`, `BROWSER_ADDRESS`) are set before starting
- The bot automatically rotates to new 15-minute buckets

