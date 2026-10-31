# ANE Compression Prompts

This file contains all prompts used by the ANE compression service. If this file exists, these prompts override the internal defaults in `service.py`.

**Edit this file to tune compression behavior without modifying code.**

---

## Fact Extraction Prompt

Extracts structured facts from conversation turns for incremental compression.

**Supported Fact Types:**
- `requirement`: User specifications, thresholds, limits, constraints
- `configuration`: Settings, parameters, options configured
- `schedule`: Timing details, frequencies, time windows, cron patterns
- `threshold`: Numeric limits, percentages, boundaries
- `decision`: Choices made, directions taken
- `preference`: User likes/dislikes, preferred approaches
- `context`: Background information, project details
- `task`: Work to be done, actions planned
- `result`: Outcomes, files created, commands executed
- `tool`: Specific tools/commands with parameters
- `location`: File paths, directories, URLs

```
Extract key facts from this conversation turn. Focus on preserving SPECIFIC DETAILS like:
- Numeric thresholds (percentages, counts, sizes)
- Timing/schedule details (times, frequencies, durations)
- Tool names and their specific parameters
- File paths and locations
- Requirements and constraints

Output as JSON array of facts, each with "type" and "content".
Types: requirement, configuration, schedule, threshold, decision, preference, context, task, result, tool, location

Turn:
{turn_text}

Facts (JSON array):
```

---

## Consolidation Prompt (With Previous Summary)

Merges new facts into existing summary while aggressively deduplicating.

```
Consolidate this summary with new facts. AGGRESSIVELY REMOVE DUPLICATES and merge similar information.
CRITICAL: Keep summary under 75 words. Be extremely concise.

Rules:
- Each fact should appear ONLY ONCE (no repetition)
- Preserve SPECIFIC NUMBERS (percentages, times, counts) but use compact phrasing
- Preserve SPECIFIC NAMES (tools, files, paths) but omit explanations
- Merge similar statements into single concise bullets
- Remove vague generalizations in favor of specifics
- Use abbreviations where clear (e.g., "CPU 85% threshold" not "CPU usage exceeds 85%")

Previous summary (MAY CONTAIN DUPLICATES - ELIMINATE THEM):
{previous_summary}

New facts:
{facts_text}

Consolidated summary (max 75 words, no duplicates, preserve specifics):
```

---

## Consolidation Prompt (Initial, No Previous Summary)

Creates initial summary from first set of facts.

```
Consolidate these facts into a brief summary paragraph.
CRITICAL: Keep under 50 words. Be extremely concise.

Rules:
- Merge similar information into single statements
- Each fact should appear only once
- Preserve specific numbers, times, and tool names but use compact phrasing
- Use abbreviations where clear

Facts:
{facts_text}

Summary (max 50 words, no duplicates, preserve specifics):
```

---

## Prompt Customization Guide

### To Improve Fact Preservation

**Problem:** Facts get too generalized (e.g., "85%" becomes "high CPU")

**Solution:** Add to fact extraction prompt:
```
CRITICAL: Preserve exact numbers, percentages, and measurements.
- "CPU exceeds 85%" → Extract "85%" as threshold
- "run every 30 minutes" → Extract "30 minutes" as schedule
- "alert after 2 minutes" → Extract "2 minutes" as duration
```

### To Reduce Summary Length

**Problem:** Summaries grow too large

**Solution:** Add to consolidation prompt:
```
Maximum length: 200 words. Prioritize recent facts over old ones.
```

### To Preserve More Context

**Problem:** Important background information gets lost

**Solution:** Add to consolidation prompt:
```
Preserve all context facts (project names, file paths, user roles).
```

### To Improve Deduplication

**Problem:** Similar facts repeat with slight variations

**Solution:** Add to consolidation prompt:
```
When you see multiple statements about the same topic, merge them:
- "never kill Firefox" + "ask before killing Firefox" → "never kill Firefox without permission"
- "create report at 6 PM" + "daily report" → "create daily report at 6 PM"
```

---

## Testing Prompts

After editing this file (`NANOBOT_ANE_PROMPTS.md`), restart the daemon to load new prompts:
```bash
./nanobot_ane/anectl restart
# Check logs for "Loaded fact extraction prompt from NANOBOT_ANE_PROMPTS.md"
tail -20 ~/.nanobot/logs/ane_daemon.log | grep "Loaded.*prompt"
```

Monitor fact extraction quality:
```bash
cat ~/.nanobot/run/ane_state.json | jq '.sessions[].facts'
```

Monitor consolidation quality:
```bash
cat ~/.nanobot/run/ane_state.json | jq -r '.sessions[].text'
```

---

## Version History

- **v1.0 (2024-10-31)**: Initial externalizable prompts with improved fact types
  - Added: requirement, configuration, schedule, threshold, tool, location types
  - Emphasis on preserving specific numbers and timing details
  - Aggressive deduplication in consolidation

---

**Note:** If this file is deleted, the service falls back to internal default prompts in `service.py`.
