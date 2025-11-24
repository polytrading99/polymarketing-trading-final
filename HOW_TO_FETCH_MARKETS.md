# How to Fetch Current Open Markets from Polymarket

This guide shows you how to get data about currently open/active markets from Polymarket and display them.

## Method 1: Using the Python Script (Command Line)

### Step 1: Run the Script

```bash
cd /home/taka/Documents/Poly_markets\(final\)/poly-maker

# Fetch all markets (may take a few minutes)
uv run python fetch_current_markets.py

# Fetch first 50 markets (faster)
uv run python fetch_current_markets.py 50

# Fetch and save to CSV
uv run python fetch_current_markets.py 100 --save-csv
```

### Step 2: View Results

The script will display:
- Market question/title
- Condition ID
- End date
- Market slug
- Token information (YES/NO tokens)
- Reward rates

### Step 3: Save to CSV (Optional)

The `--save-csv` flag saves all markets to `current_polymarket_markets.csv` for easy viewing in Excel or Google Sheets.

## Method 2: Using the API Endpoint (Web Dashboard)

### Step 1: Access the API

If your backend is running, you can fetch markets via the API:

```bash
# Fetch current markets from Polymarket API
curl http://localhost:8000/markets/current

# Fetch first 50 markets
curl http://localhost:8000/markets/current?limit=50
```

### Step 2: View in Browser

Open in your browser:
- **API Docs**: http://localhost:8000/docs
- Navigate to `/markets/current` endpoint
- Click "Try it out" to test
- Set limit (default: 100)
- Click "Execute"

### Step 3: Use in Dashboard

The endpoint returns JSON that can be displayed in your web dashboard:

```json
[
  {
    "question": "Will X happen?",
    "condition_id": "0x...",
    "market_slug": "market-slug",
    "end_date_iso": "2024-12-31T23:59:59Z",
    "token_yes": "0x...",
    "token_no": "0x...",
    "outcome_yes": "Yes",
    "outcome_no": "No",
    "rewards_daily_rate": 0.05,
    "min_size": 1.0,
    "max_spread": 5.0
  }
]
```

## Method 3: Using Docker (If Running in Containers)

```bash
# Run the script inside the backend container
docker compose exec backend uv run python fetch_current_markets.py 50

# Or access the API endpoint
curl http://localhost:8000/markets/current?limit=50
```

## What Information You Get

Each market includes:

- **question**: The market question/title
- **condition_id**: Unique identifier for the market
- **market_slug**: URL-friendly identifier
- **end_date_iso**: When the market resolves
- **token_yes/token_no**: Token IDs for YES/NO outcomes
- **outcome_yes/outcome_no**: Outcome labels
- **rewards_daily_rate**: Daily maker reward rate
- **min_size**: Minimum trade size
- **max_spread**: Maximum spread allowed

## Example Usage

### Find High-Reward Markets

```bash
# Fetch markets and filter for high rewards
uv run python fetch_current_markets.py 500 --save-csv

# Then open the CSV and sort by rewards_daily_rate
```

### Check Specific Market

```bash
# Fetch markets and search for a specific question
uv run python fetch_current_markets.py | grep "your search term"
```

### Monitor New Markets

```bash
# Run periodically to see new markets
watch -n 300 "uv run python fetch_current_markets.py 20"
```

## Troubleshooting

### "Error: Could not create Polymarket client"

- Check your `.env` file has `PK` (private key) set
- Verify the private key is correct
- Make sure you're in the project directory

### "No markets found"

- Check your internet connection
- Verify Polymarket API is accessible
- Try again (API may be temporarily unavailable)

### API Endpoint Returns 500 Error

- Check backend logs: `docker compose logs backend`
- Verify `.env` file has `PK` set
- Restart backend: `docker compose restart backend`

## Notes

- The script fetches markets directly from Polymarket's API
- Results are real-time (current open markets)
- Large fetches (1000+ markets) may take several minutes
- The API endpoint is limited to 100 markets by default (configurable)
- Markets are sorted by Polymarket's default order

## Next Steps

After fetching markets, you can:

1. **Add to Database**: Use the sync script to add markets to your database
2. **Configure Trading**: Set up trading parameters for markets you want to trade
3. **Monitor**: Add markets to your dashboard for monitoring

---

**Quick Reference:**

```bash
# Fetch 50 markets and display
uv run python fetch_current_markets.py 50

# Fetch and save to CSV
uv run python fetch_current_markets.py --save-csv

# API endpoint
curl http://localhost:8000/markets/current?limit=50
```

