#!/usr/bin/env python3
"""
Verify if the bot is actually running and trading.
Checks processes, logs, and recent activity.
"""
import sys
import os
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta

def check_processes():
    """Check if bot processes are actually running."""
    print("="*70)
    print("  PROCESS CHECK")
    print("="*70)
    
    # Try to use bot service status first
    try:
        from app.services.mm_bot_service import get_bot_status
        status = get_bot_status()
        
        print(f"\nBot Service Status:")
        print(f"  is_running: {status.get('is_running', False)}")
        
        main_proc = status.get('main_process')
        if main_proc:
            pid = main_proc.get('pid')
            alive = main_proc.get('alive', False)
            returncode = main_proc.get('returncode')
            print(f"\nMain Process:")
            if alive:
                print(f"  ✓ Running - PID: {pid}")
            elif returncode is not None:
                print(f"  ✗ Crashed - PID: {pid}, Exit code: {returncode}")
            else:
                print(f"  ⚠ Unknown status - PID: {pid}")
        else:
            print(f"\nMain Process: ✗ NOT RUNNING")
        
        trade_proc = status.get('trade_process')
        if trade_proc:
            pid = trade_proc.get('pid')
            alive = trade_proc.get('alive', False)
            returncode = trade_proc.get('returncode')
            print(f"\nTrade Process:")
            if alive:
                print(f"  ✓ Running - PID: {pid}")
            elif returncode is not None:
                print(f"  ✗ Crashed - PID: {pid}, Exit code: {returncode}")
            else:
                print(f"  ⚠ Unknown status - PID: {pid}")
        else:
            print(f"\nTrade Process: ✗ NOT RUNNING")
        
        main_alive = main_proc and main_proc.get('alive', False) if main_proc else False
        trade_alive = trade_proc and trade_proc.get('alive', False) if trade_proc else False
        
        return main_alive and trade_alive
        
    except Exception as e:
        print(f"  ⚠ Could not check via service: {e}")
        # Fallback: check if logs are being written (indicates process is running)
        print("  (Will infer from log activity)")
        return None  # Unknown, will be determined by log activity

def check_log_files():
    """Check if log files exist and have recent activity."""
    print("\n" + "="*70)
    print("  LOG FILES CHECK")
    print("="*70)
    
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / "polymarket_mm_deliver" / "logs"
    
    if not log_dir.exists():
        print(f"  ✗ Log directory not found: {log_dir}")
        return False
    
    main_log = log_dir / "mm_main.log"
    trade_log = log_dir / "trade.log"
    
    print(f"\nMain Bot Log (mm_main.log):")
    if main_log.exists():
        stat = main_log.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        
        print(f"  ✓ Exists - Size: {size} bytes")
        print(f"  Last modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age.total_seconds():.0f}s ago)")
        
        if age.total_seconds() < 60:
            print("  ✓ Recent activity (log updated in last minute)")
        elif age.total_seconds() < 300:
            print("  ⚠ Somewhat recent (log updated in last 5 minutes)")
        else:
            print("  ⚠ No recent activity (log not updated recently)")
        
        # Show last few lines
        try:
            with open(main_log, 'r') as f:
                lines = f.readlines()
                if lines:
                    print(f"\n  Last 5 lines:")
                    for line in lines[-5:]:
                        print(f"    {line.rstrip()}")
        except Exception as e:
            print(f"  ⚠ Could not read log: {e}")
    else:
        print("  ✗ Log file not found")
    
    print(f"\nTrade Process Log (trade.log):")
    if trade_log.exists():
        stat = trade_log.stat()
        size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        
        print(f"  ✓ Exists - Size: {size} bytes")
        print(f"  Last modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age.total_seconds():.0f}s ago)")
        
        if age.total_seconds() < 60:
            print("  ✓ Recent activity")
        elif age.total_seconds() < 300:
            print("  ⚠ Somewhat recent")
        else:
            print("  ⚠ No recent activity")
    else:
        print("  ✗ Log file not found")
    
    return main_log.exists() or trade_log.exists()

def check_recent_activity():
    """Check logs for recent trading activity."""
    print("\n" + "="*70)
    print("  RECENT ACTIVITY CHECK")
    print("="*70)
    
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / "polymarket_mm_deliver" / "logs"
    main_log = log_dir / "mm_main.log"
    
    if not main_log.exists():
        print("  ⚠ No log file to check")
        return False
    
    try:
        with open(main_log, 'r') as f:
            lines = f.readlines()
        
        # Look for key activity indicators
        activity_keywords = [
            'ENTRY', 'BUY', 'SELL', 'market_id', 'bucket', 'ROUND',
            'RESOLVE', 'placed', 'filled', 'order_id'
        ]
        
        recent_lines = lines[-100:] if len(lines) > 100 else lines
        activity_lines = [
            l for l in recent_lines 
            if any(kw in l.upper() for kw in activity_keywords)
        ]
        
        print(f"\n  Found {len(activity_lines)} activity lines in last 100 log entries")
        
        if activity_lines:
            print("\n  Recent activity (last 10 activity lines):")
            for line in activity_lines[-10:]:
                # Truncate long lines
                line = line.rstrip()
                if len(line) > 100:
                    line = line[:97] + "..."
                print(f"    {line}")
        else:
            print("  ⚠ No trading activity found in recent logs")
            print("  This could mean:")
            print("    - Bot is waiting for market conditions (bid < 0.6)")
            print("    - Bot is waiting for next 15-minute bucket")
            print("    - No markets found")
        
        # Check for errors
        error_lines = [
            l for l in recent_lines 
            if any(kw in l.lower() for kw in ['error', 'exception', 'failed', 'traceback'])
        ]
        
        if error_lines:
            print(f"\n  ⚠ Found {len(error_lines)} error lines in recent logs:")
            for line in error_lines[-5:]:
                line = line.rstrip()
                if len(line) > 100:
                    line = line[:97] + "..."
                print(f"    {line}")
        
        return len(activity_lines) > 0
        
    except Exception as e:
        print(f"  ✗ Error checking activity: {e}")
        return False

def check_market_conditions():
    """Explain what conditions need to be met for trading."""
    print("\n" + "="*70)
    print("  TRADING CONDITIONS")
    print("="*70)
    
    print("""
  The bot will ONLY trade when ALL of these conditions are met:
  
  1. ✓ Bot processes are running (main_final.py + trade.py)
  2. ⏳ Current 15-minute bucket has a BTC Up/Down market
  3. ⏳ Bid price ≥ 0.6 (60 cents) on the market
  4. ⏳ Position cap not exceeded ($12-16 depending on time)
  5. ⏳ Minimum trade size met ($10)
  
  If any condition is not met, the bot will WAIT and not place orders.
  
  The bot trades every 15 minutes when conditions are met.
  If you don't see activity, it's likely waiting for:
  - Bid price to reach 0.6 or higher
  - Next 15-minute market bucket to start
    """)

def main():
    print("\n" + "="*70)
    print("  BOT ACTIVITY VERIFICATION")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    processes_ok = check_processes()
    logs_ok = check_log_files()
    activity_ok = check_recent_activity()
    check_market_conditions()
    
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)
    print(f"Processes Running: {'✓ YES' if processes_ok else '✗ NO'}")
    print(f"Logs Available: {'✓ YES' if logs_ok else '✗ NO'}")
    print(f"Recent Activity: {'✓ YES' if activity_ok else '⚠ NO (may be waiting for conditions)'}")
    
    if processes_ok and logs_ok:
        print("\n✓ Bot appears to be running")
        if not activity_ok:
            print("⚠ But no recent trading activity - bot may be waiting for market conditions")
    elif processes_ok:
        print("\n⚠ Processes running but logs not found - may be starting up")
    else:
        print("\n✗ Bot does not appear to be running")
    
    print("="*70 + "\n")

if __name__ == "__main__":
    main()

