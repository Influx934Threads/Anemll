#!/bin/bash
#
# Health check for nanobot + ANE integration
#
# Usage: ./health_check.sh [--json]
#

JSON_OUTPUT=false
[[ "$1" == "--json" ]] && JSON_OUTPUT=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local name="$1"
    local url="$2"
    local response

    response=$(curl -s --connect-timeout 2 "$url" 2>/dev/null)
    if [[ $? -eq 0 && -n "$response" ]]; then
        echo "OK"
        return 0
    else
        echo "FAIL"
        return 1
    fi
}

get_json() {
    local url="$1"
    curl -s --connect-timeout 2 "$url" 2>/dev/null
}

if $JSON_OUTPUT; then
    # JSON output mode
    cat << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "services": {
    "nanobot_gateway": $(get_json "http://127.0.0.1:18790/health" || echo '{"status":"down"}'),
    "ane_daemon": $(get_json "http://127.0.0.1:8766/status" || echo '{"status":"down"}'),
    "gpu_llm": $(get_json "http://localhost:8080/v1/models" | head -c 500 || echo '{"status":"down"}')
  },
  "ane_metrics": $(get_json "http://127.0.0.1:8766/metrics" || echo '{}')
}
EOF
    exit 0
fi

# Human-readable output
echo "=== Nanobot + ANE Health Check ==="
echo "Timestamp: $(date)"
echo ""

# 1. Nanobot Gateway
echo -n "1. Nanobot Gateway (127.0.0.1:18790)... "
gw_status=$(check_service "gateway" "http://127.0.0.1:18790/health")
if [[ "$gw_status" == "OK" ]]; then
    echo -e "${GREEN}OK${NC}"
    gw_json=$(get_json "http://127.0.0.1:18790/health")
    echo "   Version: $(echo "$gw_json" | grep -o '"version":"[^"]*"' | cut -d'"' -f4)"
    echo "   Ready: $(echo "$gw_json" | grep -o '"ready":[^,}]*' | cut -d':' -f2)"
else
    echo -e "${RED}FAIL${NC}"
fi

# 2. ANE Daemon
echo ""
echo -n "2. ANE Daemon (127.0.0.1:8766)... "
ane_status=$(check_service "ane" "http://127.0.0.1:8766/status")
if [[ "$ane_status" == "OK" ]]; then
    echo -e "${GREEN}OK${NC}"
    ane_json=$(get_json "http://127.0.0.1:8766/status")
    echo "   Model: $(echo "$ane_json" | grep -o '"model_path":"[^"]*"' | cut -d'"' -f4 | xargs basename)"
    echo "   Active sessions: $(echo "$ane_json" | grep -o '"active_sessions":[0-9]*' | head -1 | cut -d':' -f2)"
    echo "   Pending turns: $(echo "$ane_json" | grep -o '"pending_turns":[0-9]*' | cut -d':' -f2)"
else
    echo -e "${RED}FAIL${NC}"
fi

# 3. ANE Metrics
echo ""
echo -n "3. ANE Compression Metrics... "
metrics=$(get_json "http://127.0.0.1:8766/metrics")
if [[ -n "$metrics" ]]; then
    echo -e "${GREEN}OK${NC}"
    echo "   Turns compressed: $(echo "$metrics" | grep -o '"turns_compressed":[0-9]*' | cut -d':' -f2)"
    echo "   Tokens saved: $(echo "$metrics" | grep -o '"tokens_saved":[0-9]*' | cut -d':' -f2)"
    echo "   Compression ratio: $(echo "$metrics" | grep -o '"compression_ratio":[0-9.]*' | cut -d':' -f2)x"
else
    echo -e "${YELLOW}NO DATA${NC}"
fi

# 4. GPU LLM Server
echo ""
echo -n "4. GPU LLM Server (localhost:8080)... "
gpu_status=$(check_service "gpu" "http://localhost:8080/v1/models")
if [[ "$gpu_status" == "OK" ]]; then
    echo -e "${GREEN}OK${NC}"
    gpu_json=$(get_json "http://localhost:8080/v1/models")
    model_name=$(echo "$gpu_json" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 | xargs basename)
    echo "   Model: $model_name"
else
    echo -e "${RED}FAIL${NC}"
fi

# 5. Nanobot Config Summary
echo ""
echo "5. Nanobot Config (key params):"
if [[ -f ~/.nanobot/config.json ]]; then
    config=$(cat ~/.nanobot/config.json)
    echo "   idleCompactAfterMinutes: $(echo "$config" | grep -o '"idleCompactAfterMinutes":[0-9]*' | cut -d':' -f2)"
    echo "   idleCompactCheckIntervalSeconds: $(echo "$config" | grep -o '"idleCompactCheckIntervalSeconds":[0-9]*' | cut -d':' -f2)"
    echo "   maxToolIterations: $(echo "$config" | grep -o '"maxToolIterations":[0-9]*' | cut -d':' -f2)"
    echo "   maxSessionMessagesPerMinute: $(echo "$config" | grep -o '"maxSessionMessagesPerMinute":[0-9]*' | cut -d':' -f2)"
    echo "   denyPatterns: $(echo "$config" | grep -o '"denyPatterns":\[[^]]*\]' | wc -l | xargs) rules"
else
    echo -e "   ${YELLOW}Config not found${NC}"
fi

echo ""
echo "=== Summary ==="
all_ok=true
[[ "$gw_status" != "OK" ]] && all_ok=false
[[ "$ane_status" != "OK" ]] && all_ok=false
[[ "$gpu_status" != "OK" ]] && all_ok=false

if $all_ok; then
    echo -e "${GREEN}All services healthy${NC}"
else
    echo -e "${YELLOW}Some services need attention${NC}"
fi
