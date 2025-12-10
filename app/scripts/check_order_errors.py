#!/usr/bin/env python3
"""
Check the actual API errors when bot tries to place orders.
Shows full error messages from logs.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
log_dir = project_root / "polymarket_mm_deliver" / "logs"
main_log = log_dir / "mm_main.log"

print("="*70)
print("  ORDER ERROR ANALYSIS")
print("="*70)

if not main_log.exists():
    print("\n✗ Log file not found:", main_log)
    sys.exit(1)

with open(main_log, 'r') as f:
    lines = f.readlines()

# Find all order attempts and their errors
print("\nRecent Order Attempts and Errors:")
print("-"*70)

# Look for entry attempts
entry_attempts = []
for i, line in enumerate(lines):
    if '[S1-ENTRY' in line or '[S2-ENTRY' in line:
        # Get the next few lines for context
        context = lines[i:min(i+5, len(lines))]
        entry_attempts.append((i, context))

# Show last 10 entry attempts
for idx, context in entry_attempts[-10:]:
    print(f"\nLine {idx}:")
    for line in context:
        line = line.rstrip()
        if len(line) > 120:
            line = line[:117] + "..."
        print(f"  {line}")

# Extract full error messages
print("\n" + "="*70)
print("  FULL ERROR MESSAGES")
print("="*70)

error_lines = []
for i, line in enumerate(lines):
    if 'PolyApiException' in line or 'status_code=40' in line or 'error' in line.lower():
        # Get surrounding context
        start = max(0, i-2)
        end = min(len(lines), i+3)
        context = lines[start:end]
        error_lines.append((i, context))

if error_lines:
    print(f"\nFound {len(error_lines)} error occurrences")
    print("\nLast 5 full error contexts:")
    print("-"*70)
    
    for idx, context in error_lines[-5:]:
        print(f"\n--- Error at line {idx} ---")
        for line in context:
            print(line.rstrip())
else:
    print("\nNo explicit errors found in recent logs")

# Look for specific status codes
print("\n" + "="*70)
print("  STATUS CODE SUMMARY")
print("="*70)

status_codes = {}
for line in lines[-500:]:  # Last 500 lines
    if 'status_code=' in line:
        # Try to extract status code
        try:
            parts = line.split('status_code=')
            if len(parts) > 1:
                code_part = parts[1].split()[0].rstrip(',')
                code = code_part.split(']')[0].split(',')[0]
                status_codes[code] = status_codes.get(code, 0) + 1
        except:
            pass

if status_codes:
    print("\nStatus codes found:")
    for code, count in sorted(status_codes.items()):
        print(f"  {code}: {count} occurrences")
    
    print("\nCommon status codes:")
    print("  400: Bad Request (invalid order parameters)")
    print("  401: Unauthorized (API key/authentication issue)")
    print("  403: Forbidden (permissions issue)")
    print("  429: Rate Limited (too many requests)")
    print("  500: Server Error (Polymarket side issue)")
else:
    print("\nNo status codes found in recent logs")

print("\n" + "="*70)

