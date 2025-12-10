#!/usr/bin/env python3
"""
Comprehensive bot status checker:
- Checks if bot is running
- If not running, why not
- If running, checks if it's placing $1 orders
- Shows recent order attempts and results
"""
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Paths
project_root = Path(__file__).parent.parent.parent
bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
log_dir = bot_dir.parent / "logs"
config_file = bot_dir / "config.json"
main_log = log_dir / "mm_main.log"
trade_log = log_dir / "trade.log"

print("="*70)
print("  BOT STATUS CHECKER")
print("="*70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 1. Check if processes are running
print("1. CHECKING PROCESS STATUS")
print("-" * 70)
main_process = []
trade_process = []
try:
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    lines = result.stdout.split('\n')
    
    main_process = [l for l in lines if 'main_final.py' in l and 'grep' not in l]
    trade_process = [l for l in lines if 'trade.py' in l and 'grep' not in l and 'main_final' not in l]
    
    if main_process:
        print("✓ Main bot process (main_final.py) is RUNNING")
        print(f"  PID: {main_process[0].split()[1]}")
    else:
        print("✗ Main bot process (main_final.py) is NOT RUNNING")
    
    if trade_process:
        print("✓ Trade process (trade.py) is RUNNING")
        print(f"  PID: {trade_process[0].split()[1]}")
    else:
        print("✗ Trade process (trade.py) is NOT RUNNING")
    
    if not main_process and not trade_process:
        print("\n⚠️  BOT IS NOT RUNNING")
        print("   Run: curl -X POST http://localhost:8000/mm-bot/start")
        print()
except Exception as e:
    print(f"⚠️  Cannot check processes directly: {e}")
    print("   (This is normal in Docker - checking via log files instead)")
    # Try alternative method - check if log files are being updated
    if main_log.exists():
        mtime = datetime.fromtimestamp(main_log.stat().st_mtime)
        age = datetime.now() - mtime
        if age.seconds < 60:
            print("   ✓ Bot appears to be running (log updated recently)")
            main_process = ["running"]  # Mark as running
        else:
            print("   ✗ Bot may not be running (log not updated recently)")

print()

# 2. Check log files
print("2. CHECKING LOG FILES")
print("-" * 70)
if main_log.exists():
    size = main_log.stat().st_size
    mtime = datetime.fromtimestamp(main_log.stat().st_mtime)
    age = datetime.now() - mtime
    print(f"✓ mm_main.log exists ({size:,} bytes, last updated {age.seconds}s ago)")
    
    if age.seconds > 300:  # 5 minutes
        print("  ⚠️  Log file hasn't been updated in 5+ minutes - bot may be stuck")
else:
    print("✗ mm_main.log NOT FOUND - bot may not have started")

if trade_log.exists():
    size = trade_log.stat().st_size
    mtime = datetime.fromtimestamp(trade_log.stat().st_mtime)
    age = datetime.now() - mtime
    print(f"✓ trade.log exists ({size:,} bytes, last updated {age.seconds}s ago)")
else:
    print("✗ trade.log NOT FOUND")

print()

# 3. Check config
print("3. CHECKING CONFIG")
print("-" * 70)
if config_file.exists():
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        api_cfg = config.get("api", {})
        s1_cfg = config.get("strategies", {}).get("strategy_1", {})
        pos_ctrl = s1_cfg.get("position_control", {})
        
        min_trade_size = pos_ctrl.get("MIN_TRADE_SIZE", "NOT SET")
        cap_schedule = pos_ctrl.get("CAP_SCHEDULE", [])
        
        print(f"MIN_TRADE_SIZE: {min_trade_size}")
        if isinstance(min_trade_size, (int, float)):
            if min_trade_size <= 1.0:
                print("  ✓ MIN_TRADE_SIZE is set to $1 or less (good for low balance)")
            else:
                print(f"  ⚠️  MIN_TRADE_SIZE is ${min_trade_size} - may be too high for low balance")
        
        if cap_schedule:
            print(f"CAP_SCHEDULE: {cap_schedule}")
            max_cap = max([c.get('cap_usd', 0) for c in cap_schedule])
            if max_cap <= 2.0:
                print(f"  ✓ Max cap is ${max_cap} (good for low balance)")
            else:
                print(f"  ⚠️  Max cap is ${max_cap} - may be too high")
        
        # Check API config
        pk = api_cfg.get("PRIVATE_KEY", "")
        proxy = api_cfg.get("PROXY_ADDRESS", "")
        sig_type = api_cfg.get("SIGNATURE_TYPE", "")
        
        if pk and pk.upper() not in ("API", "NOT SET", "NONE", ""):
            print(f"PRIVATE_KEY: ✓ SET")
        else:
            print(f"PRIVATE_KEY: ✗ NOT SET or placeholder")
        
        if proxy and proxy.upper() not in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
            print(f"PROXY_ADDRESS: ✓ SET ({proxy[:20]}...)")
        else:
            print(f"PROXY_ADDRESS: ✗ NOT SET or placeholder")
        
        print(f"SIGNATURE_TYPE: {sig_type} (type: {type(sig_type).__name__})")
        if isinstance(sig_type, int):
            print("  ✓ SIGNATURE_TYPE is integer (correct)")
        else:
            print("  ⚠️  SIGNATURE_TYPE should be integer")
            
    except Exception as e:
        print(f"✗ Error reading config: {e}")
else:
    print("✗ config.json NOT FOUND")

print()

# 4. Check recent order attempts
print("4. CHECKING RECENT ORDER ATTEMPTS (last 50 lines)")
print("-" * 70)
if main_log.exists():
    try:
        with open(main_log, 'r') as f:
            lines = f.readlines()
        
        # Get last 50 lines
        recent_lines = lines[-50:] if len(lines) > 50 else lines
        
        # Look for order attempts
        order_attempts = []
        for i, line in enumerate(recent_lines):
            if "entry_resp" in line or "BUY" in line or "SELL" in line:
                order_attempts.append((i, line.strip()))
        
        if order_attempts:
            print(f"Found {len(order_attempts)} recent order-related log entries:")
            print()
            
            # Check last few attempts
            for idx, line in order_attempts[-5:]:
                if "entry_resp" in line:
                    if "'success': True" in line or '"success": true' in line:
                        print(f"  ✓ SUCCESS: {line[:100]}")
                    elif "'success': False" in line or '"success": false' in line:
                        print(f"  ✗ FAILED: {line[:100]}")
                    else:
                        print(f"  ? {line[:100]}")
                elif "BUY" in line or "SELL" in line:
                    # Extract order size
                    if "@" in line:
                        parts = line.split("@")
                        if len(parts) > 0:
                            size_part = parts[0]
                            if "BUY" in size_part or "SELL" in size_part:
                                try:
                                    size = float(size_part.split()[-1])
                                    if size <= 1.0:
                                        print(f"  ✓ Order size: ${size} (correct for $1 orders)")
                                    else:
                                        print(f"  ⚠️  Order size: ${size} (should be $1)")
                                except:
                                    pass
                    print(f"  {line[:100]}")
                elif "WARN" in line or "ERROR" in line or "exception" in line.lower():
                    if "invalid signature" in line.lower():
                        print(f"  ✗ ERROR: Invalid signature")
                    elif "not enough balance" in line.lower() or "allowance" in line.lower():
                        print(f"  ✗ ERROR: Not enough balance/allowance")
                    else:
                        print(f"  ⚠️  {line[:100]}")
        else:
            print("  No recent order attempts found in logs")
            print("  Bot may be waiting for market conditions or not running")
        
        # Check for successful orders
        success_count = 0
        fail_count = 0
        for line in recent_lines:
            if "entry_resp" in line:
                if "'success': True" in line or '"success": true' in line:
                    success_count += 1
                elif "'success': False" in line or '"success": false' in line:
                    fail_count += 1
        
        print()
        print(f"Recent order results (last 50 lines):")
        print(f"  ✓ Successful: {success_count}")
        print(f"  ✗ Failed: {fail_count}")
        
        if success_count > 0:
            print("\n  🎉 BOT IS PLACING ORDERS SUCCESSFULLY!")
        elif fail_count > 0:
            print("\n  ⚠️  Bot is trying to place orders but they're failing")
        else:
            print("\n  ⚠️  No recent order attempts - bot may be waiting")
            
    except Exception as e:
        print(f"✗ Error reading log: {e}")
else:
    print("✗ Cannot check orders - log file not found")

print()

# 5. Check for errors
print("5. CHECKING FOR ERRORS")
print("-" * 70)
if main_log.exists():
    try:
        with open(main_log, 'r') as f:
            lines = f.readlines()
        
        recent_lines = lines[-100:] if len(lines) > 100 else lines
        
        errors = []
        for line in recent_lines:
            if any(keyword in line.lower() for keyword in ["error", "exception", "traceback", "failed", "warn"]):
                # Get full error message (may span multiple lines)
                full_error = line.strip()
                if "PolyApiException" in line:
                    # Try to get the full error message
                    if "error_message" in line:
                        # Extract the error message part
                        try:
                            # Look for the error message in the line
                            if "error':" in line or '"error":' in line:
                                # Get more context
                                idx = line.find("error_message")
                                if idx > 0:
                                    # Get up to 200 chars from error_message
                                    full_error = line[idx:idx+200]
                        except:
                            pass
                
                if "invalid signature" in line.lower():
                    errors.append(("Invalid Signature", full_error[:200]))
                elif "not enough balance" in line.lower() or "allowance" in line.lower():
                    errors.append(("Balance/Allowance", full_error[:200]))
                elif "order" in line.lower() and "invalid" in line.lower():
                    errors.append(("Order Invalid", full_error[:200]))
                elif "exception" in line.lower() or "PolyApiException" in line:
                    errors.append(("API Exception", full_error[:200]))
        
        if errors:
            print(f"Found {len(errors)} recent errors:")
            for error_type, error_msg in errors[-5:]:  # Last 5 errors
                print(f"  [{error_type}] {error_msg}")
        else:
            print("✓ No recent errors found")
            
    except Exception as e:
        print(f"✗ Error checking for errors: {e}")
else:
    print("✗ Cannot check errors - log file not found")

print()

# 6. Summary
print("="*70)
print("  SUMMARY")
print("="*70)

# Determine overall status
if main_process and trade_process:
    print("✓ Bot processes: RUNNING")
    
    if main_log.exists():
        # Check if orders are being placed
        try:
            with open(main_log, 'r') as f:
                lines = f.readlines()
            recent = lines[-50:] if len(lines) > 50 else lines
            
            has_success = any("'success': True" in l or '"success": true' in l for l in recent)
            has_attempts = any("entry_resp" in l or "BUY" in l for l in recent)
            
            if has_success:
                print("✓ Orders: BEING PLACED SUCCESSFULLY")
            elif has_attempts:
                print("⚠️  Orders: ATTEMPTING BUT FAILING")
                print("   Check errors above for details")
            else:
                print("⚠️  Orders: NO RECENT ATTEMPTS")
                print("   Bot may be waiting for market conditions")
        except:
            print("? Orders: Cannot determine")
    else:
        print("⚠️  Cannot verify order status - log file missing")
else:
    print("✗ Bot processes: NOT RUNNING")
    print("   Start the bot to begin trading")

print("="*70)

