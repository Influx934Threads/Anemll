# ANE Compression Integration with Nanobot

## Overview

This integration replaces nanobot's native LLM-based summarization with ANE (Apple Neural Engine) compression. The key benefit is that summaries now **REPLACE** old messages instead of being additive, resulting in real token savings.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTINUOUS (Background)                      │
│                                                                  │
│  ANE Daemon polls SQLite ──► Detects new turns ──► Compresses   │
│       (every 10s)                                on ANE          │
│                                                                  │
│  Summaries stored in memory, ready for instant retrieval        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ON-DEMAND (Compaction Trigger)                 │
│                                                                  │
│  Nanobot idle timeout ──► MemoryArchiver.archive() ──► POST     │
│  or context pressure          tries ANE first          /compress │
│                                                                  │
│  ANE returns pre-computed summary instantly (no reprocessing)   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BOUNDARY ADVANCEMENT                        │
│                                                                  │
│  Nanobot sets last_archived ──► Old messages skipped ──► REAL   │
│  boundary in session              in get_history()      SAVINGS │
└─────────────────────────────────────────────────────────────────┘
```

## Data Access: READ-ONLY from Nanobot's Database

The ANE daemon has **no separate storage**. It reads directly from nanobot's SQLite database:

```
~/.nanobot/sessions/<workspace_hash>/sessions.sqlite3
```

### Why No Separate Storage?

1. **Single Source of Truth**: Nanobot owns the conversation data. Duplicating it would create sync issues and stale data problems.

2. **Stateless Compression**: ANE daemon is a pure function: `messages → summary`. It doesn't need to persist summaries because:
   - Summaries are held in memory (`session_summaries` dict) for instant retrieval
   - When nanobot requests a summary via `POST /compress`, it gets returned and nanobot persists it
   - If ANE daemon restarts, it simply re-reads nanobot's DB and rebuilds summaries on next poll

3. **No Write Conflicts**: By being read-only, ANE daemon can never corrupt nanobot's data. The integration is safely additive.

4. **Simpler Recovery**: If anything goes wrong, just restart ANE daemon. It has no state to recover - it rebuilds from nanobot's authoritative data.

### How It Works

**`session_db.py`** provides `SessionDBReader`:

```python
# Finds nanobot's SQLite database
db_path = ~/.nanobot/sessions/<workspace_hash>/sessions.sqlite3

# Reads messages for a session (READ-ONLY)
messages = reader.get_session_messages(session_key)

# Polls for new turns every 10 seconds
new_turns = reader.get_turns_since(last_seen_id)
```

### Data Flow

```
┌─────────────────┐     READ-ONLY      ┌─────────────────┐
│                 │ ◄───────────────── │                 │
│  Nanobot SQLite │                    │   ANE Daemon    │
│  (sessions.db)  │                    │  (in-memory)    │
│                 │ ───────────────►   │                 │
└─────────────────┘   POST /compress   └─────────────────┘
        │              returns summary         │
        │                                      │
        ▼                                      ▼
   Authoritative                         Ephemeral
   Persistent                            Rebuilt on restart
   Owned by nanobot                      No persistence needed
```

## Integration Touchpoints

### 1. Nanobot Side (2 files modified)

**`/opt/homebrew/lib/python3.11/site-packages/nanobot/agent/ane_client.py`** (NEW)
- Lightweight HTTP client for calling ANE daemon
- `is_available()` - checks if ANE service is running
- `compress_session()` - requests pre-computed summary

**`/opt/homebrew/lib/python3.11/site-packages/nanobot/agent/memory.py`** (MODIFIED)
- Added ANE client import
- Modified `MemoryArchiver.archive()` to try ANE first
- Falls back to native LLM summarization if ANE unavailable

### 2. ANE Daemon Side (2 files modified)

**`service.py`**
- Added `generate_summary_for_nanobot()` - returns pre-computed summary
- Added `_state_lock` for thread-safe access
- Fixed metrics calculation (delta tracking instead of sum)
- Added session key normalization (`websocket:UUID` → `UUID`)

**`ane_daemon.py`**
- Added `POST /compress` endpoint
- Returns pre-computed summary instantly (no reprocessing)

## Session Key Normalization

Nanobot sends session keys with channel prefix: `websocket:b4fad3e3-e014-4035-...`
ANE daemon stores summaries by UUID only: `b4fad3e3-e014-4035-...`

The `generate_summary_for_nanobot()` method normalizes keys:
```python
normalized_key = session_key.split(":")[-1] if ":" in session_key else session_key
```

## Configuration

In `~/.nanobot/config.json`:
```json
{
  "agents": {
    "defaults": {
      "idleCompactAfterMinutes": 1,      // Trigger compaction after 1 min idle
      "idleCompactCheckIntervalSeconds": 30  // Check every 30s
    }
  }
}
```

## Metrics

The compression metrics are now accurate (fixed from inflated ratios):

```bash
curl -s http://127.0.0.1:8766/metrics | jq
```

Example output:
```json
{
  "total_input_tokens": 29348,
  "total_output_tokens": 643,
  "compression_ratio": 45.6,
  "tokens_saved": 28705,
  "turns_compressed": 95
}
```

## Deprecated: RuntimeContextBlock Injection

The old approach in `context_provider.py.bak` used `RuntimeContextBlock` to inject summaries. This was **ADDITIVE** - the summary sat beside the full history, actually **increasing** context size.

The new approach integrates with nanobot's native compaction, so summaries **REPLACE** old messages via the `last_archived` boundary.

## Testing

1. Start ANE daemon: `anectl start` or `anectl restart`
2. Start nanobot gateway (ensure it loads modified memory.py)
3. Chat in TUI
4. Wait for idle compaction (~1-2 min)
5. Check logs: `tail -f ~/.nanobot/logs/ane_daemon.log`
6. Look for: `"Returning pre-computed summary: X turns, Y chars"`

## Health Check

Run the health check script to verify all services are running:

```bash
./nanobot_ane_health_check.sh          # Human-readable table output
./nanobot_ane_health_check.sh --json   # JSON output for automation
```

Example output:
```
═══════════════════════════════════════════════════════════════════════════
                    NANOBOT + ANE HEALTH CHECK
═══════════════════════════════════════════════════════════════════════════
Service                          │ Status   │ Details
─────────────────────────────────┼──────────┼──────────────────────────────
Nanobot Gateway (:18790)         │ OK       │ v0.4.0, ready=true
ANE Daemon (:8766)               │ OK       │ 3 sessions, 7 pending
GPU LLM Server (:8080)           │ OK       │ Ternary-Bonsai-2-9B-PQ2_0

ANE Compression Metrics
Metric                           │ Value    │ Description
─────────────────────────────────┼──────────┼──────────────────────────────
Turns Compressed                 │ 98       │ Total conversation turns
Tokens Saved                     │ 29426    │ Input tokens not sent to GPU
Compression Ratio                │ 46.76x   │ Input / Output tokens

Nanobot Config (Key Parameters)
Parameter                        │ Value    │ Description
─────────────────────────────────┼──────────┼──────────────────────────────
idleCompactAfterMinutes          │ 1        │ Trigger compaction after idle
idleCompactCheckIntervalSeconds  │ 30       │ Check interval for idle
maxToolIterations                │ 20       │ Max tool calls per turn
maxSessionMessagesPerMinute      │ 3        │ Rate limit
denyPatterns                     │ 6 rules  │ Blocked command patterns
═══════════════════════════════════════════════════════════════════════════
✓ All services healthy - ready for soak testing
═══════════════════════════════════════════════════════════════════════════
```

## Troubleshooting

**"No ANE summary yet"**
- ANE daemon hasn't processed turns yet (wait for polling)
- Session key mismatch (check normalization)

**POST /compress not called**
- Nanobot not restarted after memory.py changes
- Idle compaction not triggered (check `idleCompactAfterMinutes`)

**ANE daemon not available**
- Check: `curl http://127.0.0.1:8766/status`
- Restart: `anectl restart`
