#!/usr/bin/env python3
"""
Check bot logs for errors and recent activity.
"""
import sys
import subprocess
from pathlib import Path
from datetime import datetime

def check_docker_logs():
    """Check Docker container logs."""
    print("\n" + "="*70)
    print("  Docker Container Logs (Last 50 lines)")
    print("="*70)
    
    try:
        # Try to find backend container
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
        
        containers = [c for c in result.stdout.strip().split('\n') if 'backend' in c.lower()]
        
        if not containers:
            print("⚠ No backend container found")
            return
        
        container_name = containers[0]
        print(f"Checking container: {container_name}\n")
        
        # Get recent logs
        result = subprocess.run(
            ["docker", "logs", "--tail", "50", container_name],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        # Check for errors specifically
        print("\n" + "-"*70)
        print("  Recent Errors/Exceptions")
        print("-"*70)
        
        result = subprocess.run(
            ["docker", "logs", "--tail", "200", container_name],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.split('\n')
        error_lines = [l for l in lines if any(keyword in l.lower() for keyword in ['error', 'exception', 'traceback', 'failed', 'crash'])]
        
        if error_lines:
            for line in error_lines[-20:]:  # Last 20 error lines
                print(line)
        else:
            print("No obvious errors found in recent logs")
            
    except FileNotFoundError:
        print("⚠ Docker command not found (not in Docker environment?)")
    except Exception as e:
        print(f"✗ Error checking logs: {e}")

def check_bot_process_status():
    """Check if bot processes are running."""
    print("\n" + "="*70)
    print("  Bot Process Status")
    print("="*70)
    
    try:
        # Check for Python processes running bot scripts
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.split('\n')
        bot_processes = [
            l for l in lines 
            if 'main_final.py' in l or 'trade.py' in l
        ]
        
        if bot_processes:
            print("Found bot processes:")
            for proc in bot_processes:
                print(f"  {proc}")
        else:
            print("⚠ No bot processes found running")
            
    except Exception as e:
        print(f"✗ Error checking processes: {e}")

def main():
    print("\n" + "="*70)
    print("  BOT LOGS CHECKER")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    check_bot_process_status()
    check_docker_logs()
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()

