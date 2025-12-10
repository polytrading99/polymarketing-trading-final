# MM Bot Strategy Explanation

## Overview

This is a **Market Making bot** for **Polymarket BTC 15-minute Up/Down contracts**. The bot provides liquidity by placing buy orders and managing positions with take-profit and stop-loss strategies.

## What Markets Does It Trade?

- **Market Type**: BTC (Bitcoin) Up/Down 15-minute contracts
- **Contract Duration**: 15 minutes (900 seconds)
- **Market Format**: Binary markets where you can bet:
  - **YES/Up**: BTC price will be UP at the end of 15 minutes
  - **NO/Down**: BTC price will be DOWN at the end of 15 minutes

## Strategy 1 (Currently Active)

### Entry Conditions
- **Entry Threshold**: Only buys when bid price ≥ **0.6** (60 cents)
  - This means the bot only enters when there's a reasonable chance of profit
- **Position Caps** (time-based):
  - **0-5 minutes**: Max $12 exposure
  - **5-10 minutes**: Max $14 exposure  
  - **10-15 minutes**: Max $16 exposure
- **Minimum Trade Size**: $10 per order

### Trading Logic

1. **Entry Phase**:
   - Bot monitors BTC Up/Down markets every 15 minutes
   - When a new 15-minute bucket starts, it finds the corresponding market
   - If bid price ≥ 0.6, it places a BUY order
   - Can trade on either YES (Up) or NO (Down) leg, whichever has better conditions

2. **Take Profit (TP)**:
   - After entry fills, bot places a SELL order at: `entry_price + 0.01` (minimum profit)
   - TP price is capped at 0.99 (99 cents) maximum
   - Bot will reprice the exit order if market moves favorably

3. **Stop Loss (SL)**:
   - **Trigger**: If bid price drops below **0.5** (50 cents)
   - **Action**: Immediately places aggressive SELL order at **0.01** (1 cent) to exit
   - This limits losses if the market moves against the position

4. **Late Window** (Last 2 minutes):
   - In the final 2 minutes of the 15-minute contract:
   - If entry price was ≥ 0.9, bot enters "hold mode"
   - No take profit, just holds until expiry
   - Stop loss still active at 0.7 threshold
   - Can re-enter once if stopped out (if price goes back to ≥ 0.9)

### Position Management
- **Dust Handling**: Small leftover positions (< $10) are accumulated across rounds
- **Repricing**: Entry orders are repriced if market moves significantly before fill
- **Exit Delay**: 1 second delay before placing exit orders (prevents immediate exits)

## Strategy 2 (Currently Disabled)

- Only activates in the last 7 minutes of the contract
- Entry threshold: Ask price ≥ 0.9
- Target position: $100
- Stop loss at 0.7

## What You'll See on Polymarket

When the bot is running, you'll see:

1. **Open Orders**: BUY orders on BTC Up/Down markets
2. **Positions**: Active positions in your portfolio
3. **Trade History**: Filled orders showing entries and exits
4. **Activity**: New orders every 15 minutes (when conditions are met)

## Risk Management

- **Maximum Exposure**: $12-16 per 15-minute contract (depending on time)
- **Stop Loss**: Automatic exit if price drops below 0.5
- **Take Profit**: Automatic exit when price increases by at least 0.01
- **Position Limits**: Time-based caps prevent over-exposure

## Expected Behavior

- **If BTC market is active and liquid**: Bot will place orders regularly
- **If bid prices are below 0.6**: Bot waits (no entry)
- **If market conditions are met**: Bot trades every 15 minutes
- **Positions are managed automatically**: TP/SL orders placed after entry

## Important Notes

- Bot only trades when **bid ≥ 0.6** - this is a safety feature
- Positions are small ($12-16) to limit risk
- Bot automatically exits positions (TP or SL)
- Each 15-minute contract is independent

