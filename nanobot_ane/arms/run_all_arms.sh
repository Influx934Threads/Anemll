#!/bin/bash
# Run all NPU investigation arms sequentially

set -e  # Exit on error

MODEL_PATH="${MODEL_PATH:-$HOME/.nanobot/models/qwen3-1.7b/qwen3-ane-instruct.mlmodelc}"
MODE="${1:-quick}"  # quick or full

echo "========================================"
echo "NPU Best-Fit Envelope Investigation"
echo "========================================"
echo ""
echo "Model: $MODEL_PATH"
echo "Mode: $MODE"
echo ""

# Check if model exists
if [ ! -e "$MODEL_PATH" ]; then
    echo "Error: Model not found at $MODEL_PATH"
    echo ""
    echo "Set MODEL_PATH environment variable or place model at default location"
    exit 1
fi

# Determine quick flag
QUICK_FLAG=""
if [ "$MODE" = "quick" ]; then
    QUICK_FLAG="--quick"
fi

cd "$(dirname "$0")/.."  # Go to nanobot_ane directory

# ARM A: Profiling
echo "=== ARM A: ANE Profiling ==="
python arms/arm_a/test_ane_profile.py --model "$MODEL_PATH" $QUICK_FLAG
python arms/arm_a/analyze_results.py
echo ""

# ARM B: Generative Selection
echo "=== ARM B: Generative Selection ==="
python arms/arm_b/test_generative_selection.py --model "$MODEL_PATH" $QUICK_FLAG
echo ""

# ARM C: Map-Mechanical-Merge
echo "=== ARM C: Map-Mechanical-Merge ==="
python arms/arm_c/test_map_merge.py --model "$MODEL_PATH" $QUICK_FLAG
echo ""

# ARM D: Token Budgeting
echo "=== ARM D: Token Budgeting ==="
python arms/arm_d/test_token_budget.py --model "$MODEL_PATH" $QUICK_FLAG
echo ""

# ARM E: Generative Retrieval
echo "=== ARM E: Generative Retrieval ==="
python arms/arm_e/test_generative_retrieval.py --model "$MODEL_PATH" $QUICK_FLAG
echo ""

echo "========================================"
echo "All arms complete!"
echo "========================================"
echo ""
echo "Results saved to:"
echo "  arms/results/arm_a_profile_results.json"
echo "  arms/results/arm_a_analysis.md"
echo "  arms/results/arm_b_selection_results.json"
echo "  arms/results/arm_c_merge_results.json"
echo "  arms/results/arm_d_budget_results.json"
echo "  arms/results/arm_e_retrieval_results.json"
echo ""
echo "Next steps:"
echo "  1. Review results in arms/results/"
echo "  2. Read analysis reports (*.md files)"
echo "  3. Decide which optimizations to integrate"
echo ""
