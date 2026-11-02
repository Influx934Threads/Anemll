#!/bin/bash
#
# Test mechanical merge quality with real nanobot conversations
#

SESSIONS_DIR="$HOME/.nanobot/sessions"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find user session directory (first one found)
USER_SESSION=$(find "$SESSIONS_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)

if [ -z "$USER_SESSION" ]; then
    echo "Error: No nanobot sessions found in $SESSIONS_DIR"
    exit 1
fi

echo "=========================================="
echo "Nanobot Conversation Quality Checker"
echo "=========================================="
echo ""
echo "Available conversations in: $(basename "$USER_SESSION")"
echo ""

# List conversations with sizes
conversations=($(find "$USER_SESSION" -name "*.jsonl" -type f))

if [ ${#conversations[@]} -eq 0 ]; then
    echo "Error: No conversations found"
    exit 1
fi

echo "Found ${#conversations[@]} conversations:"
echo ""

# Show conversations with sizes and dates
for i in "${!conversations[@]}"; do
    conv="${conversations[$i]}"
    size=$(du -h "$conv" | cut -f1)
    date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$conv")
    name=$(basename "$conv" .jsonl)

    # Count messages
    msg_count=$(grep -c '"role"' "$conv" 2>/dev/null || echo "0")

    printf "%2d. %s  %6s  %s msgs  %s\n" "$((i+1))" "$date" "$size" "$msg_count" "$name"
done

echo ""
echo "Usage:"
echo "  # Test a specific conversation:"
echo "  $0 <number>"
echo ""
echo "  # Or test directly with conversation file:"
echo "  cd $SCRIPT_DIR"
echo "  python3 convert_nanobot_conversation.py <path> --output /tmp/conv.json"
echo "  python3 test_consolidation_quality.py --conversation /tmp/conv.json"
echo ""

# If number provided, run test
if [ $# -eq 1 ]; then
    idx=$((${1} - 1))

    if [ $idx -lt 0 ] || [ $idx -ge ${#conversations[@]} ]; then
        echo "Error: Invalid conversation number. Choose 1-${#conversations[@]}"
        exit 1
    fi

    selected="${conversations[$idx]}"
    echo "=========================================="
    echo "Testing conversation: $(basename "$selected" .jsonl)"
    echo "=========================================="
    echo ""

    # Convert conversation
    tmp_conv="/tmp/nanobot_conv_$$.json"
    python3 "$SCRIPT_DIR/convert_nanobot_conversation.py" "$selected" \
        --output "$tmp_conv" --stats

    if [ $? -ne 0 ]; then
        echo "Error: Failed to convert conversation"
        exit 1
    fi

    # Run quality check
    echo ""
    echo "Running quality check..."
    echo ""
    python3 "$SCRIPT_DIR/test_consolidation_quality.py" \
        --conversation "$tmp_conv"

    # Cleanup
    rm -f "$tmp_conv"
fi
