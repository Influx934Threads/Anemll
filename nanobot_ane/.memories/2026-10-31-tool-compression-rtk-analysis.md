# Tool Compression Investigation & RTK Analysis

**Date**: October 31, 2026
**Session**: Tool Output Compression for nanobot_ane
**Status**: Research complete, implementation disabled, plan created

---

## Summary

Investigated LLM-based tool output compression for nanobot_ane to reduce context consumption. Found that LLM approach doesn't work - Qwen3-1.7B copies inputs verbatim instead of compressing. Researched RTK (Rust Token Killer) and discovered it uses deterministic rule-based compression, not LLMs. Created comprehensive implementation plan with 3 options.

---

## What We Built

### 1. Tool Compression Endpoint (`ane_daemon.py`)
- Added `POST /compress_tool` endpoint
- Accepts tool output, returns compressed version
- Integrated with `service.py:compress_tool_result()`

### 2. Nanobot Hook (`nanobot_patches/tool_compression_hook.py`)
- Hook function: `pre_store_tool_result()`
- Calls ANE daemon to compress before storage
- **Currently DISABLED** with `COMPRESSION_ENABLED = False`

### 3. Improved Prompts (`service.py`)
- Better prompt with example-based instruction
- Sanity checks: skip if compressed >= original
- Proper logging for debugging

### 4. Documentation
- **RTK_PYTHON_PLAN.md**: Comprehensive implementation plan
- **NANOBOT_ANE_PROMPTS.md**: Externalizable prompts for turn compression
- **MEMORY_ARCHITECTURE.md**: 500+ line memory lifecycle docs

---

## Key Findings: Why LLM Compression Doesn't Work

### The Problem
```
Input:  1,200 chars of git status output
Output: 1,200 chars (exact copy) or 2,820 chars (repetition)
Result: 0% compression or 135% expansion
```

**Root cause**: Qwen3-1.7B doesn't follow summarization instructions - it just copies the input or repeats the same summary 9+ times.

### What We Tried
1. ✗ Generic "compress this" prompt → copied verbatim
2. ✗ Explicit rules with word limits → copied verbatim
3. ✗ Example-based prompting → copied verbatim
4. ✓ Added sanity checks to prevent bad output

**Conclusion**: LLM-based summarization is the wrong approach for tool outputs.

---

## RTK Analysis: The Right Approach

### What is RTK?
- **Rust Token Killer**: Open-source CLI proxy for compressing tool outputs
- GitHub: https://github.com/rtk-ai/rtk
- Uses **deterministic rule-based compression**, not LLMs

### RTK's Four Strategies

1. **Smart Filtering**: Strips comments, whitespace, boilerplate
2. **Grouping**: Aggregates similar items (files by directory, errors by type)
3. **Truncation**: Keeps signal, drops redundancy
4. **Deduplication**: Collapses repeated lines with counts

### Performance
- **Speed**: <10ms overhead (pure string manipulation)
- **Compression**: 60-90% token reduction
- **Commands**: 125+ supported with custom rules

### Examples

| Command | Before | After | Reduction |
|---------|--------|-------|-----------|
| `git push` | 200 tokens | 10 tokens | 95% |
| `git status` | 3,000 tokens | 600 tokens | 80% |
| `git diff` | 10,000 tokens | 2,500 tokens | 75% |
| `pytest` | 8,000 tokens | 1,500 tokens | 81% |

### Key Insight
> Tool outputs have **predictable formats** (git status, file listings, test results) that benefit from **pattern-based filtering**, not LLM summarization.

---

## Implementation Plan: 3 Options

### Option A: Full Python RTK Implementation
**Cost**: 40-54 hours (5-7 days full-time)
**Approach**: Build complete rule-based compression system

**Phases**:
1. Core engine (12-16 hrs)
2. Git commands (8-12 hrs)
3. File operations (6-8 hrs)
4. Test/build outputs (8-10 hrs)
5. Integration (6-8 hrs)

**Pros**: Full control, native integration
**Cons**: High development cost, ongoing maintenance

### Option B: RTK Binary Wrapper (RECOMMENDED)
**Cost**: 6 hours total
**Approach**: Install RTK binary, create Python wrapper

**Tasks**:
1. Install RTK: 2 hours
2. Create wrapper in tool_compression_hook.py: 2 hours
3. Test integration: 2 hours

**Pros**: Quick win, zero maintenance, <10ms overhead, 125+ commands
**Cons**: External dependency

```python
# Wrapper example
import subprocess

async def compress_tool_output(tool_result: str) -> str:
    try:
        result = subprocess.run(
            ["rtk", "compress", "--stdin"],
            input=tool_result,
            capture_output=True,
            text=True,
            timeout=1.0
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return tool_result  # Fallback
```

### Option C: Hybrid Approach
**Cost**: Variable
**Approach**: RTK binary for most commands, Python for nanobot-specific needs

**Pros**: Quick 80% solution, custom 20%
**Cons**: Two systems to maintain

---

## Projected Gains

### Token Savings Per Session

**Current situation**:
- Context: 15k/45k tokens (33% of budget)
- Estimated tool outputs: ~8,000 tokens

**With 80% compression**:
- Tool outputs: 8,000 × 0.20 = 1,600 tokens
- **Savings: 6,400 tokens per session**

**New context usage**:
- From: 15k/45k (33%)
- To: ~9k/45k (20%)
- **Net gain: 40% reduction in context consumption**

### Quality Improvements
- ✅ Longer conversations (40% more messages fit)
- ✅ Cleaner tool outputs (easier to parse)
- ✅ Faster processing (fewer tokens to read)
- ✅ Better compaction (less noise in archives)

---

## Current Code State

### What's Committed (3 commits)

**Commit 1**: `ef2b75f` - Add tool compression endpoint and externalizable prompts (WIP)
- Added `/compress_tool` endpoint in `ane_daemon.py`
- Added `tool_compression_hook.py` (not integrated)
- Added `NANOBOT_ANE_PROMPTS.md` for externalizable prompts
- Added `MEMORY_ARCHITECTURE.md` docs
- Improved turn number logging in `service.py`
- Renamed `health_check.sh` → `nanobot_ane_health_check.sh`

**Commit 2**: `345bdc9` - Fix tool compression with sanity checks
- Added sanity check: skip if compressed >= original
- Improved prompt with example
- Better logging for debugging

**Commit 3**: `027e00c` - Disable faulty compression, add RTK plan
- Disabled with `COMPRESSION_ENABLED = False`
- Added `RTK_PYTHON_PLAN.md`
- Clear documentation why it's disabled

### Repository State
- ✅ All changes committed locally
- ✅ Pushed to fork: `Influx934Threads/Anemll`
- ✅ Clean working tree
- ⚠️ 25 commits ahead of `origin/main` (correct, working on fork)

### Files Modified/Added
```
nanobot_ane/
├── ane_daemon.py               (modified - added /compress_tool endpoint)
├── service.py                  (modified - compress_tool_result with checks)
├── ws_handler.py               (modified - logging improvements)
├── NANOBOT_ANE_PROMPTS.md      (new - externalizable prompts)
├── MEMORY_ARCHITECTURE.md      (new - 500+ lines)
├── RTK_PYTHON_PLAN.md          (new - implementation plan)
├── nanobot_ane_health_check.sh (renamed from health_check.sh)
└── nanobot_patches/
    └── tool_compression_hook.py (new - DISABLED hook)
```

---

## Lessons Learned

### 1. LLMs Aren't Always The Answer
Tool outputs need **deterministic compression**, not summarization:
- Predictable formats → rule-based filtering works better
- LLM summarization is slow (~20s), non-deterministic, unreliable
- Pattern matching is fast (<10ms), reliable, predictable

### 2. Model Limitations
Qwen3-1.7B is excellent for **turn-based compression** (consolidating facts from conversations) but poor at **on-demand summarization** (compressing structured tool outputs).

### 3. Architecture Insight
Two different compression needs:
- **Conversation history**: LLM-based fact extraction + consolidation ✓
- **Tool outputs**: Rule-based pattern filtering ✓
- Don't try to use one approach for both

### 4. Sanity Checks Are Critical
Always validate compression actually reduces size:
```python
if compressed_len >= original_len:
    return content  # Don't use compression
```

---

## Next Steps

### Immediate (If Needed)
1. Install RTK binary (Option B)
2. Create Python wrapper in `tool_compression_hook.py`
3. Enable with `COMPRESSION_ENABLED = True`
4. Test with real nanobot usage

### Future Work
- Monitor token savings after RTK integration
- Track which commands use most tokens
- Consider Python implementation for top 5 commands (Option A)
- Evaluate hybrid approach if RTK has limitations

### Success Metrics
- [ ] Average tokens per tool call (before/after)
- [ ] Context budget usage (target: <10k/45k = 22%)
- [ ] Compression overhead (<50ms for Python, <10ms for RTK)
- [ ] False positives (compression loses critical info)
- [ ] Messages per session before compaction

---

## References

### RTK Resources
- GitHub: https://github.com/rtk-ai/rtk
- Article: https://dev.to/arshtechpro/how-rtk-reduces-llm-token-usage-for-ai-coding-agents-2kfd
- Overview: https://www.dsebastien.net/rtk/

### Related Files
- `RTK_PYTHON_PLAN.md` - Detailed implementation plan
- `NANOBOT_ANE_PROMPTS.md` - Turn compression prompts (working)
- `MEMORY_ARCHITECTURE.md` - Memory system documentation

### Key Commands
```bash
# Check ANE daemon status
cd ~/Build/Anemll/nanobot_ane && ./anectl status

# Test compression endpoint (currently returns original)
curl -X POST http://127.0.0.1:8766/compress_tool \
  -H "Content-Type: application/json" \
  -d '{"content": "test output"}'

# View logs
tail -f ~/.nanobot/logs/ane_daemon.log
```

---

## Conclusion

LLM-based tool compression was an interesting experiment but fundamentally the wrong approach. RTK's deterministic rule-based compression is the proven solution, achieving 60-90% reductions with <10ms overhead. The code is preserved and disabled as a reference, with a clear path forward via RTK binary integration (6 hours) or Python implementation (40-54 hours).

The nanobot_ane project continues to excel at **turn-based conversation compression** (45-50x ratios), while tool output compression should be handled by RTK-style pattern matching.
