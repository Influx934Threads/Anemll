#!/bin/bash
#
# Install ANE compression integration patches into nanobot
#
# Usage: ./install_nanobot_patches.sh [--dry-run] [--uninstall]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NANOBOT_AGENT_DIR="/opt/homebrew/lib/python3.11/site-packages/nanobot/agent"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DRY_RUN=false
UNINSTALL=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--uninstall]"
            exit 1
            ;;
    esac
done

echo "=== ANE Compression Integration Patcher ==="
echo ""
echo "Nanobot path: $NANOBOT_AGENT_DIR"
echo "Patches from: $SCRIPT_DIR"
echo ""

if [ ! -d "$NANOBOT_AGENT_DIR" ]; then
    echo -e "${RED}Error: Nanobot agent directory not found${NC}"
    echo "Expected: $NANOBOT_AGENT_DIR"
    exit 1
fi

if [ "$UNINSTALL" = true ]; then
    echo -e "${YELLOW}Uninstalling ANE patches...${NC}"

    # Remove ane_client.py
    if [ -f "$NANOBOT_AGENT_DIR/ane_client.py" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] Would remove: $NANOBOT_AGENT_DIR/ane_client.py"
        else
            rm "$NANOBOT_AGENT_DIR/ane_client.py"
            echo -e "${GREEN}Removed: ane_client.py${NC}"
        fi
    fi

    # Restore memory.py backup if exists
    if [ -f "$NANOBOT_AGENT_DIR/memory.py.pre-ane" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "[DRY-RUN] Would restore: memory.py from memory.py.pre-ane"
        else
            mv "$NANOBOT_AGENT_DIR/memory.py.pre-ane" "$NANOBOT_AGENT_DIR/memory.py"
            echo -e "${GREEN}Restored: memory.py from backup${NC}"
        fi
    else
        echo -e "${YELLOW}Warning: No memory.py backup found, cannot restore${NC}"
    fi

    echo ""
    echo -e "${GREEN}Uninstall complete. Restart nanobot gateway to apply.${NC}"
    exit 0
fi

# --- Installation ---

echo "Installing ANE compression patches..."
echo ""

# 1. Install ane_client.py
echo "1. Installing ane_client.py..."
if [ -f "$NANOBOT_AGENT_DIR/ane_client.py" ]; then
    echo -e "   ${YELLOW}Already exists, will overwrite${NC}"
fi
if [ "$DRY_RUN" = true ]; then
    echo "   [DRY-RUN] Would copy: ane_client.py"
else
    cp "$SCRIPT_DIR/ane_client.py" "$NANOBOT_AGENT_DIR/ane_client.py"
    echo -e "   ${GREEN}Installed: ane_client.py${NC}"
fi

# 2. Patch memory.py
echo "2. Patching memory.py..."

MEMORY_PY="$NANOBOT_AGENT_DIR/memory.py"

# Check if already patched
if grep -q "ANE compression integration" "$MEMORY_PY" 2>/dev/null; then
    echo -e "   ${YELLOW}Already patched, skipping${NC}"
else
    # Create backup
    if [ "$DRY_RUN" = true ]; then
        echo "   [DRY-RUN] Would backup: memory.py -> memory.py.pre-ane"
        echo "   [DRY-RUN] Would apply patch: memory_ane_integration.patch"
    else
        cp "$MEMORY_PY" "$MEMORY_PY.pre-ane"
        echo "   Backup created: memory.py.pre-ane"

        # Try to apply patch
        if patch --dry-run -p2 "$MEMORY_PY" < "$SCRIPT_DIR/memory_ane_integration.patch" > /dev/null 2>&1; then
            patch -p2 "$MEMORY_PY" < "$SCRIPT_DIR/memory_ane_integration.patch"
            echo -e "   ${GREEN}Patched: memory.py${NC}"
        else
            echo -e "   ${YELLOW}Patch failed (nanobot version mismatch?), applying manually...${NC}"
            # Fall back to Python-based patching
            python3 "$SCRIPT_DIR/apply_memory_patch.py" "$MEMORY_PY"
            echo -e "   ${GREEN}Patched manually: memory.py${NC}"
        fi
    fi
fi

echo ""
echo "=== Installation Summary ==="
echo ""
echo "Files installed/modified:"
echo "  - $NANOBOT_AGENT_DIR/ane_client.py (new)"
echo "  - $NANOBOT_AGENT_DIR/memory.py (patched)"
echo "  - $NANOBOT_AGENT_DIR/memory.py.pre-ane (backup)"
echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart nanobot gateway:"
echo "     launchctl unload ~/Library/LaunchAgents/com.nanobot.gateway.plist"
echo "     launchctl load ~/Library/LaunchAgents/com.nanobot.gateway.plist"
echo ""
echo "  2. Ensure ANE daemon is running:"
echo "     anectl status"
echo ""
echo "  3. To uninstall later:"
echo "     $0 --uninstall"
