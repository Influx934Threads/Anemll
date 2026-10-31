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
BOLD='\033[1m'
NC='\033[0m'

# Check if jq is available
HAS_JQ=false
command -v jq &>/dev/null && HAS_JQ=true

get_json() {
    curl -s --connect-timeout 2 "$1" 2>/dev/null
}

json_get() {
    local json="$1"
    local key="$2"
    if $HAS_JQ; then
        echo "$json" | jq -r "$key // empty" 2>/dev/null
    else
        # Fallback: simple grep extraction
        echo "$json" | grep -o "\"${key#.}\":[^,}]*" | head -1 | sed 's/.*://' | tr -d '" '
    fi
}

print_table_header() {
    printf "${BOLD}%-30s │ %-8s │ %s${NC}\n" "$1" "$2" "$3"
    printf "%-30s─┼──────────┼─%s\n" "──────────────────────────────" "──────────────────────────────"
}

print_table_row() {
    local name="$1"
    local status="$2"
    local details="$3"

    if [[ "$status" == "OK" ]]; then
        printf "%-30s │ ${GREEN}%-8s${NC} │ %s\n" "$name" "$status" "$details"
    elif [[ "$status" == "FAIL" ]]; then
        printf "%-30s │ ${RED}%-8s${NC} │ %s\n" "$name" "$status" "$details"
    else
        printf "%-30s │ ${YELLOW}%-8s${NC} │ %s\n" "$name" "$status" "$details"
    fi
}

# Collect data
gw_json=$(get_json "http://127.0.0.1:18790/health")
ane_json=$(get_json "http://127.0.0.1:8766/status")
metrics_json=$(get_json "http://127.0.0.1:8766/metrics")
gpu_json=$(get_json "http://localhost:8080/v1/models")

if $JSON_OUTPUT; then
    cat << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "services": {
    "nanobot_gateway": ${gw_json:-'{"status":"down"}'},
    "ane_daemon": ${ane_json:-'{"status":"down"}'},
    "gpu_llm": ${gpu_json:-'{"status":"down"}'}
  },
  "ane_metrics": ${metrics_json:-'{}'}
}
EOF
    exit 0
fi

# Human-readable table output
echo ""
echo "${BOLD}═══════════════════════════════════════════════════════════════════════════${NC}"
echo "${BOLD}                    NANOBOT + ANE HEALTH CHECK${NC}"
echo "${BOLD}═══════════════════════════════════════════════════════════════════════════${NC}"
echo "Timestamp: $(date)"
echo ""

# Services Table
print_table_header "Service" "Status" "Details"

# 1. Nanobot Gateway
if [[ -n "$gw_json" ]]; then
    gw_status="OK"
    if $HAS_JQ; then
        gw_version=$(echo "$gw_json" | jq -r '.runtime.version // "?"')
        gw_ready=$(echo "$gw_json" | jq -r '.ready // "?"')
    else
        gw_version=$(echo "$gw_json" | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
        gw_ready=$(echo "$gw_json" | grep -o '"ready":[^,}]*' | sed 's/.*://')
    fi
    print_table_row "Nanobot Gateway (:18790)" "$gw_status" "v${gw_version}, ready=${gw_ready}"
else
    gw_status="FAIL"
    print_table_row "Nanobot Gateway (:18790)" "$gw_status" "Not responding"
fi

# 2. ANE Daemon
if [[ -n "$ane_json" ]]; then
    ane_status="OK"
    if $HAS_JQ; then
        ane_model=$(echo "$ane_json" | jq -r '.model_path // "?"' | xargs basename)
        ane_sessions=$(echo "$ane_json" | jq -r '.active_sessions // 0')
        ane_pending=$(echo "$ane_json" | jq -r '.pending_turns // 0')
    else
        ane_model=$(echo "$ane_json" | grep -o '"model_path":"[^"]*"' | cut -d'"' -f4 | xargs basename)
        ane_sessions=$(echo "$ane_json" | grep -o '"active_sessions":[0-9]*' | head -1 | sed 's/.*://')
        ane_pending=$(echo "$ane_json" | grep -o '"pending_turns":[0-9]*' | sed 's/.*://')
    fi
    print_table_row "ANE Daemon (:8766)" "$ane_status" "${ane_sessions} sessions, ${ane_pending} pending"
else
    ane_status="FAIL"
    print_table_row "ANE Daemon (:8766)" "$ane_status" "Not responding"
fi

# 3. GPU LLM
if [[ -n "$gpu_json" ]]; then
    gpu_status="OK"
    if $HAS_JQ; then
        gpu_model=$(echo "$gpu_json" | jq -r '.data[0].id // .models[0].model // "?"' | xargs basename)
    else
        gpu_model=$(echo "$gpu_json" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4 | xargs basename)
    fi
    print_table_row "GPU LLM Server (:8080)" "$gpu_status" "$gpu_model"
else
    gpu_status="FAIL"
    print_table_row "GPU LLM Server (:8080)" "$gpu_status" "Not responding"
fi

echo ""

# ANE Metrics Table
if [[ -n "$metrics_json" ]]; then
    echo "${BOLD}ANE Compression Metrics${NC}"
    print_table_header "Metric" "Value" "Description"

    if $HAS_JQ; then
        turns=$(echo "$metrics_json" | jq -r '.turns_compressed // 0')
        saved=$(echo "$metrics_json" | jq -r '.tokens_saved // 0')
        ratio=$(echo "$metrics_json" | jq -r '.compression_ratio // 0')
        input=$(echo "$metrics_json" | jq -r '.total_input_tokens // 0')
        output=$(echo "$metrics_json" | jq -r '.total_output_tokens // 0')
    else
        turns=$(echo "$metrics_json" | grep -o '"turns_compressed":[0-9]*' | sed 's/.*://')
        saved=$(echo "$metrics_json" | grep -o '"tokens_saved":[0-9]*' | sed 's/.*://')
        ratio=$(echo "$metrics_json" | grep -o '"compression_ratio":[0-9.]*' | sed 's/.*://')
        input=$(echo "$metrics_json" | grep -o '"total_input_tokens":[0-9]*' | sed 's/.*://')
        output=$(echo "$metrics_json" | grep -o '"total_output_tokens":[0-9]*' | sed 's/.*://')
    fi

    print_table_row "Turns Compressed" "$turns" "Total conversation turns processed"
    print_table_row "Tokens Saved" "$saved" "Input tokens not sent to GPU LLM"
    print_table_row "Compression Ratio" "${ratio}x" "Input / Output tokens"
    print_table_row "Total Input" "$input" "Tokens received for compression"
    print_table_row "Total Output" "$output" "Tokens in compressed summaries"
    echo ""
fi

# Config Table
echo "${BOLD}Nanobot Config (Key Parameters)${NC}"
print_table_header "Parameter" "Value" "Description"

if [[ -f ~/.nanobot/config.json ]]; then
    config=$(cat ~/.nanobot/config.json)

    if $HAS_JQ; then
        idle_compact=$(echo "$config" | jq -r '.agents.defaults.idleCompactAfterMinutes // "not set"')
        idle_interval=$(echo "$config" | jq -r '.agents.defaults.idleCompactCheckIntervalSeconds // "not set"')
        max_iterations=$(echo "$config" | jq -r '.agents.defaults.maxToolIterations // "not set"')
        max_messages=$(echo "$config" | jq -r '.tools.maxSessionMessagesPerMinute // "not set"')
        deny_count=$(echo "$config" | jq -r '.tools.exec.denyPatterns | length')
    else
        idle_compact=$(echo "$config" | tr -d '\n ' | grep -o '"idleCompactAfterMinutes":[0-9]*' | sed 's/.*://')
        idle_interval=$(echo "$config" | tr -d '\n ' | grep -o '"idleCompactCheckIntervalSeconds":[0-9]*' | sed 's/.*://')
        max_iterations=$(echo "$config" | tr -d '\n ' | grep -o '"maxToolIterations":[0-9]*' | sed 's/.*://')
        max_messages=$(echo "$config" | tr -d '\n ' | grep -o '"maxSessionMessagesPerMinute":[0-9]*' | sed 's/.*://')
        deny_count=$(echo "$config" | grep -o '"denyPatterns"' | wc -l | tr -d ' ')
    fi

    print_table_row "idleCompactAfterMinutes" "${idle_compact:-?}" "Trigger compaction after N min idle"
    print_table_row "idleCompactCheckIntervalSeconds" "${idle_interval:-?}" "Check interval for idle sessions"
    print_table_row "maxToolIterations" "${max_iterations:-?}" "Max tool calls per turn"
    print_table_row "maxSessionMessagesPerMinute" "${max_messages:-?}" "Rate limit"
    print_table_row "denyPatterns" "${deny_count:-0} rules" "Blocked command patterns"
else
    print_table_row "Config" "MISSING" "~/.nanobot/config.json not found"
fi

echo ""
echo "${BOLD}═══════════════════════════════════════════════════════════════════════════${NC}"

# Summary
all_ok=true
[[ "$gw_status" != "OK" ]] && all_ok=false
[[ "$ane_status" != "OK" ]] && all_ok=false
[[ "$gpu_status" != "OK" ]] && all_ok=false

if $all_ok; then
    echo -e "${GREEN}${BOLD}✓ All services healthy - ready for soak testing${NC}"
else
    echo -e "${YELLOW}${BOLD}⚠ Some services need attention${NC}"
fi
echo "${BOLD}═══════════════════════════════════════════════════════════════════════════${NC}"
echo ""
