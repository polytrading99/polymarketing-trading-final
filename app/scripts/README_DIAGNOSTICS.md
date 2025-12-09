# Bot Diagnostic Scripts

These scripts help diagnose why the MM bot is not starting or crashing.

## Scripts

### 1. `diagnose_bot_errors.py` (Comprehensive Check)
**Most important script - run this first!**

Checks:
- Environment variables (PK, BROWSER_ADDRESS)
- Configuration file existence and validity
- Python dependencies
- Module imports
- File paths
- Shared memory access

**Run:**
```bash
# Inside Docker container
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.diagnose_bot_errors

# Or locally (if running outside Docker)
python app/scripts/diagnose_bot_errors.py
```

### 2. `test_bot_startup.py` (Startup Test)
Tests if the bot processes can actually start without crashing.

**Run:**
```bash
# Inside Docker container
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.test_bot_startup

# Or locally
python app/scripts/test_bot_startup.py
```

**Note:** This will start the processes for a few seconds then stop them. Make sure trade.py is not already running!

### 3. `check_bot_logs.py` (Log Checker)
Checks Docker logs for recent errors and bot process status.

**Run:**
```bash
# Inside Docker container
docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.check_bot_logs

# Or locally (if Docker is available)
python app/scripts/check_bot_logs.py
```

## Quick Diagnostic Flow

1. **Run comprehensive check:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.diagnose_bot_errors
   ```
   This will show you what's missing or misconfigured.

2. **If config/env issues found, fix them and run again.**

3. **Test startup:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.test_bot_startup
   ```
   This will show the actual error when trying to start.

4. **Check logs:**
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.check_bot_logs
   ```
   This shows what happened when the bot tried to run.

## Common Issues

- **Missing environment variables:** Set PK and BROWSER_ADDRESS in .env or docker-compose.yml
- **Config file issues:** Check that config.json has valid API credentials
- **Import errors:** Missing dependencies - check pyproject.toml
- **Shared memory errors:** Usually OK if trade.py hasn't started yet

## Output

All scripts provide clear ✓ (pass) and ✗ (fail) indicators. Share the output with the developer to get help fixing issues.

