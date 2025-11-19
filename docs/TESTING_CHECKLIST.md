# Pre-Flight Testing Checklist for Real Money Trading

## ⚠️ CRITICAL: Start with Small Amounts

Before deploying with significant capital, test thoroughly with minimum trade sizes.

## Pre-Deployment Checks

### 1. Environment Setup
- [ ] `.env` file created with all required variables
- [ ] `PK` (private key) is set correctly
- [ ] `BROWSER_ADDRESS` matches your wallet
- [ ] Wallet has done at least one manual trade through Polymarket UI (for permissions)
- [ ] Wallet has sufficient USDC balance for testing
- [ ] Google Sheets credentials configured (if using fallback)

### 2. Database & Services
- [ ] All Docker services running: `docker compose ps`
- [ ] Database is accessible and migrations applied
- [ ] Backend API responding: `curl http://localhost:8000/health/`
- [ ] Frontend accessible: `http://localhost:3000`
- [ ] Grafana accessible: `http://localhost:3001` (admin/admin)

### 3. Market Configuration
- [ ] Markets synced to database: Run `uv run python app/scripts/sync_config.py`
- [ ] At least one market configured with:
  - Small `trade_size` (start with $1-5)
  - Reasonable `max_spread` (e.g., 0.05 = 5%)
  - Appropriate `tick_size` (usually 0.01)
- [ ] Strategy parameters configured

### 4. Bot Control Testing
- [ ] Can start bot via UI: Click play button on a market
- [ ] Bot status shows "running" in database
- [ ] Can stop bot via UI: Click stop button
- [ ] Bot status updates to "stopped"
- [ ] No errors in backend logs when starting/stopping

### 5. Worker Connection Testing
- [ ] Worker container is running: `docker compose logs worker`
- [ ] Worker connects to Polymarket WebSocket (check logs)
- [ ] Worker loads markets from database (check logs for "Loaded X active markets")
- [ ] No connection errors in worker logs

## First Trade Testing

### 6. Initial Trade Verification
- [ ] Start bot for ONE market only
- [ ] Monitor worker logs: `docker compose logs -f worker`
- [ ] Verify WebSocket connections established:
  - Market WebSocket connected
  - User WebSocket authenticated
- [ ] Wait for order book updates (should see market data)
- [ ] Verify orders are placed (check Polymarket UI or API)
- [ ] Monitor first few trades closely:
  - Orders appear on both sides (buy/sell)
  - Orders are at reasonable prices
  - No unexpected large orders

### 7. Position Monitoring
- [ ] Check positions in UI dashboard
- [ ] Verify PnL calculation (should be near zero initially)
- [ ] Check fees are being tracked
- [ ] Verify position counts update

### 8. Metrics Verification
- [ ] Prometheus scraping: `curl http://localhost:9090/api/v1/targets`
- [ ] Metrics appear after first trade: `curl http://localhost:8000/metrics/ | grep poly_`
- [ ] Grafana shows data (may take a few minutes after first trade)

## Safety Checks

### 9. Risk Controls
- [ ] Trade sizes are small (start with $1-5 per order)
- [ ] Max position size limits set appropriately
- [ ] Spread limits configured (max_spread)
- [ ] Can stop bot quickly if needed (test stop button)

### 10. Error Handling
- [ ] Worker reconnects if WebSocket disconnects (check logs)
- [ ] No infinite loops or stuck processes
- [ ] Errors are logged clearly
- [ ] Bot stops cleanly when requested

## Scaling Up

### 11. Multi-Market Testing
- [ ] After single market works, add second market
- [ ] Verify both markets trade independently
- [ ] Check resource usage (CPU, memory)
- [ ] Monitor for any conflicts or issues

### 12. Production Readiness
- [ ] All services stable for extended period (1+ hours)
- [ ] No memory leaks (monitor container memory)
- [ ] Database queries performant
- [ ] Logs are manageable and informative
- [ ] Alerts configured in Grafana (optional)

## Emergency Procedures

### If Something Goes Wrong:
1. **STOP THE BOT IMMEDIATELY**: Use UI stop button or `docker compose stop worker`
2. **Check Positions**: Review current positions in Polymarket UI
3. **Review Logs**: `docker compose logs worker --tail=100`
4. **Cancel Orders**: May need to cancel orders manually in Polymarket UI
5. **Check Balance**: Verify wallet balance hasn't changed unexpectedly

## Monitoring During Testing

### Key Metrics to Watch:
- **Trade Count**: Should increase slowly as bot makes markets
- **Open Orders**: Should see orders on both sides of book
- **Position Size**: Should stay within configured limits
- **PnL**: Monitor for unexpected losses
- **Fees**: Track cumulative fees paid
- **Error Rate**: Should be near zero

### Log Monitoring:
```bash
# Watch worker logs
docker compose logs -f worker

# Watch backend logs
docker compose logs -f backend

# Check for errors
docker compose logs | grep -i error
```

## Success Criteria

✅ Bot successfully:
- Connects to Polymarket
- Places orders on both sides
- Executes trades
- Updates positions correctly
- Tracks PnL and fees
- Stops cleanly when requested

## Next Steps After Testing

1. Gradually increase trade sizes
2. Add more markets
3. Fine-tune strategy parameters
4. Set up production monitoring
5. Configure alerts for anomalies

---

**Remember**: Start small, monitor closely, scale gradually!

