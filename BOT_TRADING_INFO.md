# Bot Trading Information

## What Markets Does the Bot Trade?

The bot trades **BTC 15-minute Up/Down markets** on Polymarket.

- **Market Format**: `btc-updown-15m-{timestamp}`
- **Example**: `btc-updown-15m-1765373400`
- **Type**: Binary prediction markets (Up/Down)
- **Duration**: Each market lasts 15 minutes
- **New Market**: A new market starts every 15 minutes

## How Does the Bot Decide to Place Orders?

The bot places orders when **ALL** of these conditions are met:

1. **Bid Price Threshold**: The bid price must be >= `ENTRY_BID_THRESHOLD` (currently 0.6)
   - If bid is 0.59 or lower → No order
   - If bid is 0.60 or higher → Order can be placed

2. **Position Cap**: Current position must be below the cap for the time window:
   - 0-5 minutes: Max $3.0
   - 5-10 minutes: Max $4.0
   - 10-15 minutes: Max $5.0

3. **No Existing Position**: Bot won't place a new order if there's already an active position for that leg (Up or Down)

4. **Market Minimum**: The market must allow orders of at least `MIN_TRADE_SIZE` ($5.0)

## How Often Does the Bot Check?

- **Every minute**: The bot checks market conditions at the start of each minute
- **15-minute cycles**: Each market lasts 15 minutes, then a new one starts

## Why Might Orders Not Be Placed?

1. **Bid too low**: If the bid price is < 0.6, the bot won't enter
2. **Market minimum too high**: If the market requires > $5 minimum, orders will fail
3. **Already at cap**: If you've already used your position cap for that time window
4. **Waiting for conditions**: The bot is patient and only enters when conditions are right

## Current Settings (for $5 balance)

- **MIN_TRADE_SIZE**: $5.0
- **CAP_SCHEDULE**: 
  - 0-5 min: $3.0
  - 5-10 min: $4.0
  - 10-15 min: $5.0
- **ENTRY_BID_THRESHOLD**: 0.6 (60%)

## How to Monitor

1. **Check the dashboard**: See current market and recent errors
2. **Check logs**: 
   ```bash
   docker exec -it polymarketing-trading-final-backend-1 tail -f /app/polymarket_mm_deliver/logs/mm_main.log | grep -E "(ENTRY|bid|BUY)"
   ```
3. **Look for**: 
   - `[S1-ENTRY-YES] BUY 5.0 @ 0.XX` - Order attempt
   - `entry_resp = {'success': True}` - Order placed successfully
   - `bid >= 0.6` - Condition met

## Expected Behavior

- Bot checks every minute
- If bid >= 0.6 and conditions are met → Places $5 order
- If market minimum is $5 → Order succeeds
- If market minimum is > $5 → Order fails with "Size lower than minimum"
- Bot will try again in the next 15-minute market

## Testing with $5

With $5 balance, the bot can:
- Place one $5 order per 15-minute market
- Wait for the right conditions (bid >= 0.6)
- Try different markets until it finds one that accepts $5 orders

**Be patient** - The bot will place orders when:
1. Market conditions are right (bid >= 0.6)
2. A market accepts $5 minimum orders
3. You haven't already used your position cap

