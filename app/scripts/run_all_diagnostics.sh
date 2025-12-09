#!/bin/bash
# Run all diagnostic scripts and save output

echo "=========================================="
echo "  MM BOT DIAGNOSTIC SUITE"
echo "=========================================="
echo ""
echo "This will run all diagnostic scripts and save output to diagnostic_report.txt"
echo ""

OUTPUT_FILE="diagnostic_report.txt"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

{
    echo "=========================================="
    echo "  DIAGNOSTIC REPORT"
    echo "  Generated: $TIMESTAMP"
    echo "=========================================="
    echo ""
    
    echo ">>> Running comprehensive diagnostic..."
    echo ""
    python -m app.scripts.diagnose_bot_errors
    
    echo ""
    echo ""
    echo ">>> Testing bot startup..."
    echo ""
    python -m app.scripts.test_bot_startup
    
    echo ""
    echo ""
    echo ">>> Checking logs..."
    echo ""
    python -m app.scripts.check_bot_logs
    
} 2>&1 | tee "$OUTPUT_FILE"

echo ""
echo "=========================================="
echo "  Report saved to: $OUTPUT_FILE"
echo "=========================================="
echo ""
echo "Please share the contents of $OUTPUT_FILE for troubleshooting."

