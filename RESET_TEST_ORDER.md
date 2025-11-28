# How to Reset Test Order Flag

If you've done a manual trade on Polymarket and want the bot to try placing an order again, you need to reset the `test_order_placed` flag.

## Option 1: Restart the Worker (Easiest)

The flag resets when the worker restarts:

```bash
docker compose restart worker
```

## Option 2: Reset via Python (If you need to reset without restart)

```bash
docker compose exec worker python -c "import poly_data.global_state as gs; gs.test_order_placed = False; print('Flag reset!')"
```

## Important: Do Manual Trade First!

Before resetting, make sure you've done a manual trade:

1. Go to https://polymarket.com
2. Connect wallet: `0xd432d6514fDCA3ba83Db61faC04FC6Fb5f748287`
3. Make ONE small manual trade (buy or sell any market)
4. Wait for transaction to confirm
5. Wait 1-2 minutes for permissions to propagate
6. Then restart the worker

