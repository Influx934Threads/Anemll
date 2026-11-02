# Python RTK Implementation Plan

## Executive Summary

Implement a Python version of RTK's rule-based tool output compression for nanobot_ane, using deterministic pattern-matching instead of LLM summarization.

**Goal**: 60-80% token reduction on common development commands
**Approach**: Pattern-based filtering, grouping, truncation, deduplication
**Integration**: Pre-storage hook in nanobot (already have hook skeleton)

---

## Architecture

### Core Components

```
nanobot_ane/
├── tool_compressor/
│   ├── __init__.py
│   ├── engine.py           # Main compression engine
│   ├── registry.py         # Command pattern registry
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py         # Base strategy interface
│   │   ├── git.py          # Git command compression
│   │   ├── files.py        # File listing compression
│   │   ├── tests.py        # Test output compression
│   │   ├── build.py        # Build output compression
│   │   └── generic.py      # Fallback compression
│   └── config.yaml         # Compression rules config
└── nanobot_patches/
    └── tool_compression_hook.py  # Updated to use tool_compressor
```

### Compression Engine Flow

```python
def compress(output: str, command_hint: str = None) -> str:
    """
    1. Detect command type (git, ls, pytest, etc.)
    2. Select appropriate strategy
    3. Apply compression rules:
       - Filter (remove boilerplate)
       - Group (aggregate similar items)
       - Truncate (intelligent limiting)
       - Deduplicate (collapse repeats)
    4. Return compressed output
    """
```

---

## Implementation Phases

### Phase 1: Core Engine (Week 1)
**Effort**: 12-16 hours

**Tasks**:
- [ ] Create compression engine skeleton
- [ ] Implement command detection (regex patterns)
- [ ] Build strategy registry system
- [ ] Add basic filtering utilities:
  - Remove blank lines (configurable)
  - Strip leading/trailing whitespace
  - Remove common boilerplate patterns
- [ ] Implement deduplication:
  - Detect repeated lines
  - Collapse to "... (repeated N times)"
- [ ] Write unit tests for engine

**Deliverable**: Working engine with generic fallback compression

### Phase 2: Git Commands (Week 1-2)
**Effort**: 8-12 hours

**Priority commands** (80% of git usage):
- `git status` - Most common, high token cost
- `git diff` - Very verbose
- `git log` - Repetitive format
- `git push/pull` - Lots of progress output
- `git branch` - Simple but can be long

**Compression strategies**:

#### git status
```python
# Before (150 lines, ~2000 tokens):
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)

        modified:   src/components/Header.tsx
        modified:   src/utils/api.ts
        ...

# After (~300 tokens, 85% reduction):
Branch: main (up to date)
Modified: src/components/Header.tsx, src/utils/api.ts (2 files)
Untracked: tests/ (1 dir)
```

**Rules**:
- Remove git help text (use "git add...")
- Group files by status (modified, untracked, staged)
- Count items per group
- Compact format: "Modified: file1, file2 (N files)"

#### git diff
```python
# Before (1000+ lines for large diffs):
diff --git a/file.py b/file.py
index abc123..def456 100644
--- a/file.py
+++ b/file.py
@@ -10,7 +10,7 @@ def function():
...

# After (summary + truncated):
Changed: file.py (+15 -3), file2.ts (+2 -1)
[First 50 lines of actual diff preserved]
... (500 more lines omitted)
```

**Rules**:
- Summarize changed files with line counts
- Truncate large diffs (keep first 50-100 lines)
- Preserve actual diff content for small changes

### Phase 3: File Operations (Week 2)
**Effort**: 6-8 hours

**Commands**:
- `ls -la` - Directory listings
- `find` - File search results
- `tree` - Directory trees
- `cat` large files

**Strategies**:
- Group by file type/extension
- Truncate very long listings (>100 items)
- "... and N more files"
- Preserve first/last items + metadata

### Phase 4: Test & Build Outputs (Week 2-3)
**Effort**: 8-10 hours

**Commands**:
- `pytest` / `python -m pytest`
- `npm test` / `npm run test`
- `cargo test`
- `npm run build` / `cargo build`
- `make`

**Strategies**:
- Collapse passing tests to counts
- Preserve failures with full detail
- Remove build progress bars/spinners
- Group warnings by type
- Summarize compilation stats

### Phase 5: Integration & Polish (Week 3)
**Effort**: 6-8 hours

**Tasks**:
- [ ] Update tool_compression_hook.py to use new engine
- [ ] Add configuration file (yaml)
- [ ] Performance optimization (<50ms overhead target)
- [ ] Comprehensive test suite
- [ ] Documentation
- [ ] Benchmarking vs original outputs

---

## Cost Estimate

### Development Time
| Phase | Hours | Complexity |
|-------|-------|------------|
| Core Engine | 12-16 | Medium |
| Git Commands | 8-12 | Medium-High |
| File Ops | 6-8 | Low-Medium |
| Test/Build | 8-10 | Medium |
| Integration | 6-8 | Low |
| **Total** | **40-54 hours** | **5-7 days full-time** |

### Ongoing Costs
- **Maintenance**: 2-4 hours/month (add new commands, fix edge cases)
- **Performance overhead**: ~20-50ms per tool call (vs <10ms for Rust RTK)
- **Code complexity**: ~2000-3000 lines of Python + tests

### Alternative: Use RTK Binary
- **Setup time**: 2-4 hours (install, configure hook, test)
- **Maintenance**: ~0 hours (upstream maintains it)
- **Performance**: <10ms overhead
- **Limitation**: External dependency, binary installation required

---

## Gain Estimate

### Token Savings by Command Type

| Command Type | Avg Original | Compressed | Reduction | Frequency |
|--------------|-------------|------------|-----------|-----------|
| `git status` | 3,000 tokens | 600 tokens | 80% | Very High |
| `git diff` | 10,000 tokens | 2,500 tokens | 75% | High |
| `git log` | 5,000 tokens | 1,000 tokens | 80% | Medium |
| `ls -la` | 2,000 tokens | 400 tokens | 80% | High |
| `find` results | 4,000 tokens | 800 tokens | 80% | Medium |
| `pytest` | 8,000 tokens | 1,500 tokens | 81% | High |
| `npm test` | 6,000 tokens | 1,200 tokens | 80% | Medium |
| Build outputs | 15,000 tokens | 3,000 tokens | 80% | Low |

### Projected Context Budget Impact

**Current situation** (from your session):
- Context usage: 15k/45k tokens (33%)
- Live messages: ~14,700 tokens
- Summary: ~300 tokens

**Assumptions**:
- Average 30 tool calls per session
- Average 2,000 tokens per uncompressed tool output
- 80% compression ratio achieved

**Calculation**:
```
Current tool output tokens: 30 calls × 2,000 tokens = 60,000 tokens
With compression: 60,000 × 0.20 = 12,000 tokens
Savings per session: 48,000 tokens

But nanobot already has maxToolResultChars: 16,000 truncation
Real current: ~8,000 tokens for tool outputs (estimated)
With compression: 8,000 × 0.20 = 1,600 tokens
Real savings: 6,400 tokens per session
```

**Impact on your 45k context window**:
- Current: 15k/45k (33% used)
- With tool compression: ~9k/45k (20% used)
- **Gain: 6k tokens freed up = 40% reduction in context usage**

### Quality of Life Improvements

1. **Longer conversations**: 40% more messages fit in context
2. **Cleaner tool outputs**: Easier for model to parse
3. **Faster context processing**: Less tokens to read
4. **Better compaction**: Archived messages compress better with less noise

---

## Comparison: Python RTK vs Alternatives

### Option A: Python RTK (This Plan)
**Pros**:
- ✅ Native integration with nanobot_ane
- ✅ Customizable for specific needs
- ✅ No external binary dependencies
- ✅ Full control over compression logic

**Cons**:
- ❌ 40-54 hours development time
- ❌ Ongoing maintenance burden
- ❌ 20-50ms overhead (vs <10ms for Rust)
- ❌ Need to implement each command type

**Best for**: Full control, deep integration, learning experience

### Option B: Use RTK Binary
**Pros**:
- ✅ 2-4 hours setup time
- ✅ Zero maintenance (upstream handles it)
- ✅ <10ms overhead (Rust performance)
- ✅ 125+ commands already supported
- ✅ Battle-tested in production

**Cons**:
- ❌ External dependency (Rust binary)
- ❌ Less customization flexibility
- ❌ Installation complexity for users

**Best for**: Quick win, production stability, minimal maintenance

### Option C: Hybrid Approach
**Pros**:
- ✅ Use RTK binary for most commands
- ✅ Python compression for nanobot-specific needs
- ✅ Quick 80% solution, custom 20%

**Cons**:
- ❌ Two systems to maintain
- ❌ More complex architecture

**Best for**: Pragmatic balance of speed and control

---

## Recommendation

### Short-term (Next 1-2 days): **Option B + Minimal Python Layer**
1. Install RTK binary: 2 hours
2. Create Python wrapper in tool_compression_hook.py: 2 hours
3. Test integration with nanobot: 2 hours
4. **Total: 6 hours for 60-80% compression gains**

```python
# Updated tool_compression_hook.py
import subprocess

async def compress_tool_output(tool_result: str, command: str = None) -> str:
    """Use RTK binary for compression, fallback to original"""
    try:
        # Detect command from tool_result if not provided
        result = subprocess.run(
            ["rtk", "compress", "--stdin"],
            input=tool_result,
            capture_output=True,
            text=True,
            timeout=1.0
        )
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        logger.debug(f"RTK compression failed: {e}")

    return tool_result  # Fallback
```

### Medium-term (Next 1-2 weeks): **Python RTK for Top 5 Commands**
If RTK binary proves problematic or you want more control:
1. Implement just the top 5 commands: 20 hours
   - git status
   - git diff
   - ls -la
   - pytest
   - find
2. Cover 80% of use cases with 50% of the effort
3. Use generic truncation for everything else

### Long-term: **Evaluate based on usage patterns**
- Monitor which commands consume most tokens
- Implement Python versions only for high-value targets
- Let RTK handle the long tail

---

## Success Metrics

Track after implementation:
- [ ] Average tokens per tool call (before/after)
- [ ] Context budget usage (before/after)
- [ ] Compression overhead time (target <50ms)
- [ ] False positives (compression loses critical info)
- [ ] Messages per session before compaction

**Target**: 60-80% token reduction on tool outputs, <50ms overhead

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Over-compression loses info | High | Medium | Preserve error messages, add verbose mode |
| Performance overhead | Medium | Low | Profile and optimize hot paths |
| Maintenance burden | High | High | Limit to top 10 commands, good tests |
| Command edge cases | Low | High | Fallback to original on parse failures |
| User expects full output | Medium | Low | Add --no-compress flag, log originals |

---

## Next Steps

1. **Decision point**: Choose Option A, B, or C
2. **If Option B**: Install RTK, create wrapper (6 hours)
3. **If Option A**: Start Phase 1 (core engine)
4. **Measure baseline**: Track current token usage per command type
5. **Set success criteria**: Define acceptable compression quality

---

## Appendix: RTK References

- GitHub: https://github.com/rtk-ai/rtk
- Article: https://dev.to/arshtechpro/how-rtk-reduces-llm-token-usage-for-ai-coding-agents-2kfd
- Overview: https://www.dsebastien.net/rtk/

**Key learnings**:
- Deterministic > LLM-based for tool outputs
- Command-specific rules > generic summarization
- Fast execution critical (<10ms target)
- 125+ commands = long tail of use cases
