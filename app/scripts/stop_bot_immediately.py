#!/usr/bin/env python3
"""
Stop the bot immediately to prevent further losses.
"""
import requests
import sys

print("="*70)
print("  STOPPING BOT IMMEDIATELY")
print("="*70)

try:
    response = requests.post("http://localhost:8000/mm-bot/stop", timeout=5)
    if response.status_code == 200:
        print("✓ Bot stopped successfully")
    else:
        print(f"⚠️  Response: {response.status_code} - {response.text}")
except Exception as e:
    print(f"✗ Error stopping bot: {e}")
    print("\n⚠️  Try manually:")
    print("   curl -X POST http://localhost:8000/mm-bot/stop")
    sys.exit(1)

print("\n" + "="*70)
print("  BOT STOPPED")
print("="*70)

