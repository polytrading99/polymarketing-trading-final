#!/usr/bin/env python3
"""
Test bot startup and capture all errors.
This will try to actually start the bot processes and show what fails.
"""
import sys
import os
import subprocess
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"

def test_trade_script():
    """Test trade.py startup."""
    print("\n" + "="*70)
    print("  Testing trade.py (data feed)")
    print("="*70)
    
    trade_script = bot_dir / "trade.py"
    if not trade_script.exists():
        print(f"✗ trade.py not found: {trade_script}")
        return False
    
    print(f"Running: python {trade_script}")
    print("-" * 70)
    
    try:
        # Run for 3 seconds then kill
        process = subprocess.Popen(
            ["python", str(trade_script)],
            cwd=str(bot_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy()
        )
        
        # Wait a bit to see initial output
        time.sleep(3)
        
        # Check if still running
        if process.poll() is None:
            print("✓ Process is running (no immediate crash)")
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=5)
                if stdout:
                    print("\nOutput:")
                    print(stdout[:500])  # First 500 chars
            except subprocess.TimeoutExpired:
                process.kill()
            return True
        else:
            # Process exited
            returncode = process.returncode
            stdout, _ = process.communicate()
            print(f"✗ Process exited with code {returncode}")
            if stdout:
                print("\nOutput/Errors:")
                print(stdout[:1000])  # First 1000 chars
            return False
            
    except Exception as e:
        print(f"✗ Exception starting trade.py: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_main_script():
    """Test main_final.py startup."""
    print("\n" + "="*70)
    print("  Testing main_final.py (trading bot)")
    print("="*70)
    
    main_script = bot_dir / "main_final.py"
    if not main_script.exists():
        print(f"✗ main_final.py not found: {main_script}")
        return False
    
    print(f"Running: python {main_script}")
    print("-" * 70)
    
    try:
        # Run for 5 seconds then kill
        process = subprocess.Popen(
            ["python", str(main_script)],
            cwd=str(bot_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy()
        )
        
        # Wait a bit to see initial output
        time.sleep(5)
        
        # Check if still running
        if process.poll() is None:
            print("✓ Process is running (no immediate crash)")
            process.terminate()
            try:
                stdout, _ = process.communicate(timeout=5)
                if stdout:
                    print("\nOutput (first 1000 chars):")
                    print(stdout[:1000])
            except subprocess.TimeoutExpired:
                process.kill()
            return True
        else:
            # Process exited
            returncode = process.returncode
            stdout, _ = process.communicate()
            print(f"✗ Process exited with code {returncode}")
            if stdout:
                print("\nOutput/Errors:")
                print(stdout[:2000])  # First 2000 chars
            return False
            
    except Exception as e:
        print(f"✗ Exception starting main_final.py: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*70)
    print("  BOT STARTUP TEST")
    print("="*70)
    print("\nThis will test starting both bot processes.")
    print("Processes will run for a few seconds then be terminated.")
    print("\nNOTE: Make sure trade.py is NOT already running!")
    print("="*70)
    
    trade_ok = test_trade_script()
    time.sleep(1)
    main_ok = test_main_script()
    
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)
    print(f"trade.py:   {'✓ OK' if trade_ok else '✗ FAILED'}")
    print(f"main_final.py: {'✓ OK' if main_ok else '✗ FAILED'}")
    print("="*70 + "\n")
    
    return 0 if (trade_ok and main_ok) else 1

if __name__ == "__main__":
    sys.exit(main())

