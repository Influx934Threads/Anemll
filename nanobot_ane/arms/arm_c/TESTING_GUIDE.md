# Testing Mechanical Merge in Real Nanobot Conversations

This guide shows how to verify that the mechanical merge implementation is working correctly in production.

## Quick Test (5-10 turns)

### Step 1: Check ANE daemon is running

```bash
# Check if ANE daemon is running
ps aux | grep ane_daemon

# Check logs
tail -f ~/.nanobot/logs/ane_daemon.log
```

If not running, start it according to nanobot documentation.

### Step 2: Start the monitor (in Terminal 1)

```bash
cd /Users/agundez/Build/Anemll/nanobot_ane/arms/arm_c

# Watch mode - shows consolidation events in real-time
python3 monitor_ane_consolidation.py --watch

# Or check current state snapshot
python3 monitor_ane_consolidation.py
```

### Step 3: Have a conversation with nanobot (in Terminal 2)

Start a nanobot conversation and have at least **5-10 turns** (user + assistant pairs).

Example conversation topics to generate diverse facts:
```
User: Set the API rate limit to 100 requests per minute
User: Configure timeout to 30 seconds
User: Set log level to debug
User: Connect to PostgreSQL on port 5432
User: Set cache size to 1024 MB
User: Create a daily backup at 6 PM
User: Set CPU threshold to 85%
```

### Step 4: Watch for consolidation events

The monitor will show:
- **Turn 5**: First consolidation event (or when >10 facts accumulated)
- **Turn 10**: Second consolidation event
- Facts being extracted each turn
- Consolidated text output

**Expected output at consolidation:**
```
[12:34:56] 🔄 CONSOLIDATION EVENT #1
Session: a1b2c3d4e5f6...
Turn: 4 → 5

Consolidation Analysis:
  Chars: 245
  Lines: 12
  Markdown sections: ✓
  Type headers: ✓
  Bullet lists: ✓

  ✅ Looks like MECHANICAL MERGE output

Consolidated text:
----------------------------------------------------------------------
**Configuration:**
- API rate limit set to 100 requests per minute
- timeout configuration set to 30 seconds
- log level set to debug mode
- database connection to PostgreSQL on port 5432
- cache size set to 1024 MB

**Result:**
- Changes applied immediately
- Connected to database
----------------------------------------------------------------------
```

### Step 5: Verify mechanical merge characteristics

The output should show:

✅ **Mechanical merge indicators:**
- Structured markdown with `**Type:**` headers
- Bullet lists under each type
- Grouped by fact type (Configuration, Result, Context, etc.)
- No repeated information (duplicates removed)
- Compact, organized format

❌ **LLM consolidation indicators (should NOT see):**
- Prose paragraphs ("The configuration has been applied...")
- Repeated information with slight variations
- Narrative style instead of structured lists
- Missing type organization

## Detailed Testing

### Check ANE state file directly

```bash
# View current state
cat ~/.nanobot/run/ane_state.json | jq .

# View specific session
cat ~/.nanobot/run/ane_state.json | jq '.sessions | to_entries | .[0]'

# View consolidated text
cat ~/.nanobot/run/ane_state.json | jq -r '.sessions | to_entries | .[0].value.text'

# Count facts
cat ~/.nanobot/run/ane_state.json | jq '.sessions | to_entries | .[0].value.facts | length'
```

### Monitor specific session

```bash
# Get session key from snapshot
python3 monitor_ane_consolidation.py

# Monitor that specific session
python3 monitor_ane_consolidation.py --watch --session <session-key>
```

### Check daemon logs

```bash
# Watch for consolidation log messages
tail -f ~/.nanobot/logs/ane_daemon.log | grep -i "consolidat"

# Should see messages like:
# "Re-consolidating at turn 5 (12 facts) using mechanical merge"
```

## Validation Checklist

After 10 turns, verify:

- [ ] Consolidation happened at turn 5 (or when facts > 10)
- [ ] Consolidated text has markdown structure with type headers
- [ ] Facts are grouped by type (Configuration, Result, etc.)
- [ ] No duplicates (same fact not repeated)
- [ ] Compact bullet-point format (not prose)
- [ ] Daemon log shows "using mechanical merge"
- [ ] No errors in daemon log
- [ ] Token estimate stayed reasonable (< 2000)

## Performance Verification

The mechanical merge should be **instant** (< 5ms). Check daemon logs:

```bash
# Look for timing info in logs
grep "consolidat" ~/.nanobot/logs/ane_daemon.log
```

You should NOT see:
- Long delays between fact extraction and consolidation
- LLM-related errors
- "Consolidation failed" messages

## Troubleshooting

### No consolidation happening

**Check:**
1. Is ANE daemon running? `ps aux | grep ane_daemon`
2. Is the conversation being tracked? Check `ane_state.json`
3. Have you had at least 5 turns? Consolidation happens at turn 5

### Consolidation looks like LLM output (prose style)

**Problem:** The old LLM consolidation is still being used.

**Fix:**
1. Restart ANE daemon to load new code
2. Check `service.py` has the mechanical merge implementation
3. Verify daemon logs show "using mechanical merge"

### Facts not being extracted

**Check:**
1. Daemon logs for extraction errors
2. Model path is correct
3. ANE model is loaded successfully

### State file not updating

**Check:**
1. Permissions on `~/.nanobot/run/ane_state.json`
2. Daemon has write access
3. Check daemon logs for save errors

## Compare with Quality Check

After the conversation, you can run the quality checker on the actual nanobot conversation:

```bash
# Find the session file
ls -lh ~/.nanobot/sessions/*/

# Convert and test
python3 convert_nanobot_conversation.py \
    ~/.nanobot/sessions/<user>/<session>.jsonl \
    --output /tmp/test.json \
    --stats

python3 test_consolidation_quality.py --conversation /tmp/test.json
```

This will show:
- Fact retention (should be >90%)
- Which facts were preserved
- Compression ratio
- Quality assessment

## Expected Results

After 10 turns with diverse facts:

| Metric | Expected Value |
|--------|---------------|
| Consolidation time | < 5ms (instant) |
| Fact retention | > 90% |
| Duplicates removed | 20-40% of facts |
| Output format | Markdown with type sections |
| Token estimate | < 500 tokens for 20 facts |
| Consolidation frequency | Every 5 turns |

## Success Criteria

✅ **Test passes if:**
1. Consolidation happens automatically at turn 5
2. Output has structured markdown format
3. Facts are grouped by type with no duplicates
4. Daemon logs show "using mechanical merge"
5. No errors in daemon logs
6. Quality check shows >90% retention

❌ **Test fails if:**
1. Consolidation doesn't happen
2. Output is prose/narrative style (LLM)
3. Facts are duplicated or lost
4. Daemon logs show errors
5. Quality check shows <60% retention
