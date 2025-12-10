#!/usr/bin/env python3
"""
Capture the actual error when bot tries to start.
This runs the bot and captures stdout/stderr to see what fails.
"""
import sys
import os
import subprocess
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
bot_dir = project_root / "polymarket_mm_deliver" / "polymarket_mm_deliver"
main_script = bot_dir / "main_final.py"

print("="*70)
print("  CAPTURING BOT STARTUP ERROR")
print("="*70)
print(f"\nRunning: python {main_script}")
print(f"Working directory: {bot_dir}")
print("\n" + "-"*70 + "\n")

# Set environment variables if they exist
env = os.environ.copy()

try:
    # Run the bot and capture output
    process = subprocess.Popen(
        ["python", str(main_script)],
        cwd=str(bot_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Combine stderr into stdout
        text=True,
        env=env,
        bufsize=1  # Line buffered
    )
    
    # Collect output for 10 seconds or until process exits
    output_lines = []
    start_time = time.time()
    timeout = 10
    
    while True:
        # Check if process exited
        returncode = process.poll()
        if returncode is not None:
            # Process exited, read remaining output
            remaining, _ = process.communicate()
            if remaining:
                output_lines.extend(remaining.splitlines())
            break
        
        # Check timeout
        if time.time() - start_time > timeout:
            print(f"\n[Timeout after {timeout}s, process still running]")
            process.terminate()
            try:
                remaining, _ = process.communicate(timeout=5)
                if remaining:
                    output_lines.extend(remaining.splitlines())
            except subprocess.TimeoutExpired:
                process.kill()
            break
        
        # Try to read a line (non-blocking)
        try:
            line = process.stdout.readline()
            if line:
                output_lines.append(line.rstrip())
                print(line.rstrip())  # Print as we go
        except:
            time.sleep(0.1)
    
    print("\n" + "="*70)
    print("  FINAL OUTPUT")
    print("="*70)
    
    # Print all collected output
    for line in output_lines:
        print(line)
    
    print("\n" + "="*70)
    print(f"  Process exited with code: {returncode if returncode is not None else 'N/A'}")
    print("="*70)
    
    # Look for errors
    error_keywords = ['error', 'exception', 'traceback', 'failed', 'failed to', 'cannot', 'unable']
    error_lines = [l for l in output_lines if any(kw in l.lower() for kw in error_keywords)]
    
    if error_lines:
        print("\n" + "="*70)
        print("  ERROR LINES FOUND")
        print("="*70)
        for line in error_lines[-20:]:  # Last 20 error lines
            print(line)
    
except Exception as e:
    print(f"\n✗ Exception running bot: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

