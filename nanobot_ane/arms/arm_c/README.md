# ARM C: Map-Mechanical-Merge Pattern

Tests and validates mechanical merge consolidation as replacement for LLM consolidation.

## Results Summary

**Mechanical merge WINS decisively:**
- **Speed**: 2ms vs 7,451ms (3,725x faster)
- **Quality**: 92.86% recall vs 50% (better preservation)
- **Cost**: 0 tokens vs 161 tokens (zero output cost)

## Files

### Core Implementation

- **`mechanical_merger.py`** - CPU-side fact consolidation using fuzzy deduplication (85% similarity threshold)
- **`structured_extractor.py`** - Extract structured facts from conversation turns
- **`test_map_merge.py`** - Main ARM C test comparing LLM vs mechanical merge

### Quality Checking Tools

- **`test_consolidation_quality.py`** - Full quality checker with model-based fact extraction
- **`demo_consolidation_quality.py`** - Lightweight demo with pre-extracted facts
- **`convert_nanobot_conversation.py`** - Convert nanobot JSONL conversations to test format
- **`test_with_nanobot_conversation.sh`** - Helper script to test with real nanobot conversations

### Production Testing Tools

- **`monitor_ane_consolidation.py`** - Real-time monitor for ANE consolidation events
- **`TESTING_GUIDE.md`** - Step-by-step guide to test mechanical merge in production

## Testing Mechanical Merge in Production

### Real-time Monitoring (During Live Conversation)

Monitor consolidation as it happens during a nanobot conversation:

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane/arms/arm_c

# Watch for consolidation events in real-time
python3 monitor_ane_consolidation.py --watch

# Or check current state snapshot
python3 monitor_ane_consolidation.py
```

Then have a conversation with nanobot (5-10 turns). The monitor will show:
- When consolidation happens (turn 5, or when >10 facts)
- Whether it's mechanical merge (structured markdown) or LLM (prose)
- Facts extracted and deduplicated
- Real-time consolidation output

**See `TESTING_GUIDE.md` for complete testing instructions.**

## Testing with Past Nanobot Conversations

### Quick Start

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane/arms/arm_c

# List available conversations
bash test_with_nanobot_conversation.sh

# Test a specific conversation (e.g., #3)
bash test_with_nanobot_conversation.sh 3
```

### Manual Testing

```bash
# 1. Convert nanobot conversation to JSON
python3 convert_nanobot_conversation.py \
    ~/.nanobot/sessions/*/your-conversation.jsonl \
    --output /tmp/conversation.json \
    --stats

# 2. Run quality check
python3 test_consolidation_quality.py \
    --conversation /tmp/conversation.json \
    --model /Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048
```

### Demo Mode (No Model Required)

```bash
# Run demo with pre-extracted sample facts
python3 demo_consolidation_quality.py
```

## Nanobot Conversation Locations

Nanobot stores conversations in:
- **Sessions**: `~/.nanobot/sessions/<user_id>/<session_id>.jsonl`
- **Memory**: `~/.nanobot/workspace/memory/history.jsonl`
- **ANE State**: `~/.nanobot/run/ane_state.json`

The helper script automatically finds and lists all available conversations with:
- Message count
- File size
- Last modified date

## Quality Metrics

The quality checker evaluates:

1. **Overall Recall**: Percentage of facts preserved after consolidation
2. **By-Type Analysis**: Retention rates for each fact type:
   - `configuration` - Settings, parameters
   - `result` - Outcomes, confirmations
   - `threshold` - Numeric limits, percentages
   - `schedule` - Timing details, frequencies
   - `tool` - Commands with parameters
   - `location` - File paths, URLs
   - `task`, `decision`, `preference`, `context`

3. **Compression Stats**:
   - Duplicates removed
   - Compression ratio
   - Output length

4. **Detailed Reports**:
   - Preserved facts (with matched keywords)
   - Lost facts (with keywords that should have matched)
   - Assessment rating: Excellent (>90%) / Good (>75%) / Acceptable (>60%) / Poor (<60%)

## Output

Quality check results are saved to:
```
arms/results/consolidation_quality_check.json
```

Contains:
- Input facts
- Consolidated output text
- Quality metrics (recall, by-type analysis)
- Detailed preservation/loss information

## Integration Status

✅ **Implemented in service.py** (commit 575db5c)

The mechanical merge has been integrated into `service.py`, replacing the `_consolidate_facts()` method. The service now:
1. Extracts facts from conversation turns (still uses LLM)
2. Consolidates facts using mechanical merge (CPU-only, instant)
3. Eliminates the expensive LLM consolidation call every 5 turns

## Usage Example

```python
from mechanical_merger import MechanicalMerger

# Initialize merger
merger = MechanicalMerger(similarity_threshold=0.85)

# Your facts from conversation
facts = [
    {"type": "configuration", "content": "API rate limit set to 100 requests per minute"},
    {"type": "result", "content": "Changes applied immediately"},
    # ... more facts
]

# Consolidate
result = merger.merge(facts)

print(result['text'])  # Formatted markdown output
print(f"Removed {result['duplicate_count']} duplicates")
print(f"Compression: {result['compression_ratio']:.2f}x")
```

## Next Steps

1. Monitor mechanical merge quality in production using the ANE state file
2. Consider running ARM D (token budgeting) to further optimize fact extraction
3. Consider running ARM E (generative retrieval analysis)

## References

- ARM C Test Results: `arms/results/arm_c_merge_results.json`
- Implementation: `nanobot_ane/service.py` (lines 9, 107, 447-467)
- Documentation: `INVESTIGATION_SUMMARY.md` (ARM C section)
