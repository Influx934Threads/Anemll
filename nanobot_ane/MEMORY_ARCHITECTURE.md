# Nanobot + ANE Memory Architecture

## Overview

This document explains the complete memory lifecycle in the nanobot + ANE integration, including all storage layers, processing stages, and data flows.

---

## Storage Layers

### 1. **Nanobot SQLite Database** (Authoritative Source)

**Location:** `~/.nanobot/sessions/<workspace_hash>/sessions.sqlite3`

**Schema:**
```sql
CREATE TABLE messages (
    session_key TEXT NOT NULL,      -- "websocket:UUID"
    position INTEGER NOT NULL,       -- Monotonic message counter
    record TEXT NOT NULL,            -- JSON blob: {role, content, timestamp, ...}
    PRIMARY KEY (session_key, position)
);

CREATE TABLE sessions (
    session_key TEXT PRIMARY KEY,
    workspace_id TEXT,
    last_archived INTEGER,           -- Position boundary for archival
    created_at TEXT,
    updated_at TEXT
);
```

**Purpose:**
- Single source of truth for all conversation messages
- Written by nanobot gateway
- Read by ANE daemon (READ-ONLY)
- Persistent across restarts

**Key Fields:**
- `position`: Monotonic counter per session (never decreases)
- `last_archived`: Boundary separating archived vs live messages
- `record`: Full message with role, content, tool calls, etc.

---

### 2. **ANE Daemon In-Memory State**

**Location:** In-memory Python dict in `service.py`

```python
session_summaries: dict[str, SessionSummary] = {
    "b4fad3e3-e014-4035-...": SessionSummary(
        text="I will create documentation...",  # Current summary
        facts=[...],                            # Recent unmerged facts
        turn_count=67,                          # Total turns compressed
        token_estimate=327,                     # Estimated summary size
        input_tokens=18629,                     # Original tokens compressed
        last_updated=datetime.now()
    )
}
```

**Purpose:**
- Hot cache for pre-computed summaries
- Instant retrieval on nanobot compaction requests
- Lost on daemon restart (rebuilt from persisted state)

---

### 3. **ANE Persisted State File**

**Location:** `~/.nanobot/run/ane_state.json`

```json
{
  "sessions": {
    "b4fad3e3-e014-4035-...": {
      "text": "I will create documentation...",
      "facts": [...],
      "turn_count": 67,
      "token_estimate": 327,
      "input_tokens": 18629,
      "last_updated": "2024-10-31T20:16:00"
    }
  },
  "metrics": {
    "total_input_tokens": 30458,
    "total_output_tokens": 643,
    "total_turns_compressed": 101
  },
  "session_positions": {
    "b4fad3e3-e014-4035-...": 372
  }
}
```

**Purpose:**
- Survive daemon restarts
- Resume compression from last known position
- Preserve metrics across restarts

**Updated:**
- Every 5 turns (during re-consolidation)
- On daemon shutdown

---

### 4. **Nanobot WS Handler State** (ANE Daemon)

**Location:** In-memory in `ws_handler.py`

```python
_sessions: dict[str, SessionState] = {
    "b4fad3e3-e014-4035-...": SessionState(
        messages=[...],                    # Temporary message buffer
        turns=[...],                       # Detected user+assistant pairs
        last_compressed_index=120,         # Buffer position
    )
}
```

**Purpose:**
- Temporary buffer for turn detection
- Groups user+assistant messages into turns
- Ephemeral - recreated on daemon restart

---

### 5. **JSONL Files** (Deprecated)

**Location:** `~/.nanobot/sessions/<workspace_hash>/<session>.jsonl`

**Purpose:**
- Periodic snapshots/exports from SQLite
- NOT the live data source
- Used for debugging/auditing
- ANE daemon does NOT use these

---

## Memory Lifecycle

### Stage 1: User Message Arrives

```
User types message
    │
    ▼
Nanobot Gateway
    │
    ├─► SQLite: INSERT INTO messages (session_key, position, record)
    │       position = MAX(position) + 1
    │
    └─► WebSocket broadcast: {"type": "user_message", ...}
```

**Files Modified:** `sessions.sqlite3`

---

### Stage 2: GPU Model Generates Response

```
Nanobot calls GPU model (Ternary-Bonsai-2-9B @ 31 tok/s)
    │
    ▼
Assistant response generated
    │
    ▼
Nanobot Gateway
    │
    ├─► SQLite: INSERT INTO messages (session_key, position, record)
    │       position = MAX(position) + 1
    │
    └─► WebSocket broadcast: {"type": "assistant_message", ...}
```

**Files Modified:** `sessions.sqlite3`

---

### Stage 3: ANE Daemon Detects New Turn

```
ANE Daemon (every 10s polling loop)
    │
    ▼
SessionDBReader.get_all_sessions()
    │
    ▼
Check curr_max_pos > prev_max_pos?
    │
    ├─► YES: New messages detected
    │   │
    │   ▼
    │   Fetch messages from SQLite (position > prev_max_pos)
    │   │
    │   ▼
    │   ws_handler.py detects user+assistant pair
    │   │
    │   ▼
    │   Queue turn for compression
    │
    └─► NO: Skip (already processed)
```

**Files Read:** `sessions.sqlite3` (READ-ONLY)

---

### Stage 4: ANE Compression (Background)

```
Compression Worker (async)
    │
    ▼
Dequeue turn from priority queue
    │
    ▼
_extract_facts(turn)  ──► ANE inference (~5s)
    │                     Extract JSON facts
    │
    ▼
Get session summary (with lock)
    │
    ▼
Merge new facts into summary.facts[]
summary.turn_count += 1
    │
    ▼
Re-consolidation needed?
    ├─► YES (turn_count % 5 == 0 OR facts > 10)
    │   │
    │   ▼
    │   _consolidate_facts(facts, previous_summary)
    │   │   ──► ANE inference (~10s)
    │   │       "Remove duplicates and merge similar information"
    │   │
    │   ▼
    │   Prune facts: keep only last 5
    │   │
    │   └─► Persist to ane_state.json
    │
    └─► NO: Just add facts to rolling list
    │
    ▼
Update in-memory session_summaries{}
```

**Triggers Re-consolidation:**
- Every 5 turns (60, 65, 70, 75...)
- When facts > 10 (prevents unbounded growth)

**Files Modified:**
- `ane_state.json` (every 5 turns)
- In-memory only (between saves)

**Model Used:** Qwen3-1.7B on ANE @ ~20 tok/s

---

### Stage 5: Idle Compaction Trigger (Nanobot)

```
Nanobot idle timer (1 minute)
    │
    ▼
MemoryArchiver.archive() called
    │
    ▼
Try ANE compression first
    │
    ▼
POST http://127.0.0.1:8766/compress
    {
        "session_key": "websocket:UUID",
        "messages": [...],         # For reference only
        "previous_summary": "..."  # Fallback if ANE has nothing
    }
    │
    ▼
ANE Daemon receives request
    │
    ▼
Normalize key: "websocket:UUID" → "UUID"
    │
    ▼
Return pre-computed summary (instant, no reprocessing!)
    │
    ▼
Nanobot receives summary
    │
    ▼
UPDATE sessions SET last_archived = <position>
    │
    ▼
Future get_history() queries skip messages WHERE position <= last_archived
```

**Key Insight:** ANE returns ALREADY COMPUTED summary. No re-compression happens here!

**Files Modified:** `sessions.sqlite3` (updates `last_archived`)

---

## Memory Boundaries

### What Gets Archived?

```
Session timeline:
┌──────────────────────────────────────────────────────────────┐
│ Position:  1    50    100   150   200   250   300   350     │
│            │     │     │     │     │     │     │     │       │
│            [──────ARCHIVED──────][────LIVE CONTEXT────]      │
│                                  ▲                            │
│                          last_archived = 200                 │
└──────────────────────────────────────────────────────────────┘

Archived messages (position <= 200):
  - Replaced by ANE summary in prompts
  - Still in SQLite (not deleted)
  - Not sent to GPU model

Live messages (position > 200):
  - Full messages sent to GPU
  - Recent conversation context
  - Typically last ~10-20 turns depending on token count
```

### How Many Turns Stay "Live"?

**Nanobot's Logic:**
1. Start from most recent message (highest position)
2. Count backwards until context limit reached (32K tokens by default)
3. Everything before that position = archived
4. `last_archived` = boundary position

**Typical Behavior:**
- Context window: 32K tokens
- Average turn: ~300-500 tokens
- **Live turns: ~15-25 recent turns** (depending on message length)
- Older turns: compressed into ANE summary

**Example:**
```
Turn 67 (current)
Turn 66
Turn 65
...
Turn 50 ← last_archived boundary (17 turns kept live)
─────────────────────────────────────────
Turns 1-49: Compressed into summary
```

---

## Compression Timing

### Continuous Background Compression (ANE)

| Event | When | What Happens |
|-------|------|--------------|
| **New turn detected** | Every 10s polling | Facts extracted, added to summary.facts[] |
| **Re-consolidation** | Every 5 turns (65, 70, 75...) | Merge facts into coherent summary, deduplicate |
| **Fact pruning** | After each re-consolidation | Keep only last 5 facts (rest merged into text) |
| **State persistence** | Every 5 turns | Save to `ane_state.json` |

### On-Demand Retrieval (Nanobot)

| Event | When | What Happens |
|-------|------|--------------|
| **Idle compaction** | After 1 min idle | Request pre-computed summary from ANE |
| **Context pressure** | When context > 32K | Request summary, advance last_archived |
| **Manual compaction** | User triggers | Same as idle compaction |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER TYPES MESSAGE                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Nanobot Gateway     │
                  │  (Port 18790)        │
                  └──────────┬───────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
                ▼            ▼            ▼
         ┌──────────┐  ┌─────────┐  ┌─────────┐
         │  SQLite  │  │   GPU   │  │   WS    │
         │  INSERT  │  │  Infer  │  │ Notify  │
         └──────────┘  └─────────┘  └─────────┘
                │            │
                │            │
                ▼            ▼
         ┌──────────────────────────┐
         │  sessions.sqlite3        │
         │  position += 1           │
         │  (authoritative)         │
         └──────────┬───────────────┘
                    │
                    │ READ-ONLY (every 10s)
                    │
                    ▼
         ┌──────────────────────────┐
         │   ANE Daemon Polling     │
         │   Detect new messages    │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  ws_handler.py           │
         │  Group into turns        │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Compression Queue       │
         │  (in-memory)             │
         └──────────┬───────────────┘
                    │
                    ▼
         ┌──────────────────────────────────┐
         │  ANE Compression Worker          │
         │  1. Extract facts (ANE ~5s)      │
         │  2. Merge into summary           │
         │  3. Re-consolidate every 5 turns │
         │     (ANE ~10s, deduplicate)      │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  session_summaries{}     │
         │  (in-memory cache)       │
         └──────────┬───────────────┘
                    │
                    │ Persist every 5 turns
                    │
                    ▼
         ┌──────────────────────────┐
         │  ane_state.json          │
         │  (survive restarts)      │
         └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              NANOBOT IDLE (1 MIN) → COMPACTION                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  MemoryArchiver      │
                  │  .archive()          │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  POST /compress      │
                  │  → ANE Daemon        │
                  └──────────┬───────────┘
                             │
                             ▼
         ┌──────────────────────────────────┐
         │  Return pre-computed summary     │
         │  (instant, no reprocessing)      │
         └──────────┬───────────────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Update last_archived    │
         │  in sessions.sqlite3     │
         └──────────────────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Future get_history()    │
         │  skips archived messages │
         └──────────────────────────┘
```

---

## Key Metrics

### Compression Performance (Current Production)

| Metric | Value | Description |
|--------|-------|-------------|
| **Compression Ratio** | 45-50x | Input tokens / Output tokens |
| **Tokens Saved** | ~29,000 | After 101 turns |
| **Average Compression Time** | ~15 sec/turn | Background, non-blocking |
| **ANE Inference Speed** | ~20 tok/s | Qwen3-1.7B model |
| **GPU Inference Speed** | ~31 tok/s | Ternary-Bonsai-2-9B (user-facing) |

### Memory Distribution (Typical Session at 67 Turns)

| Layer | Content | Size |
|-------|---------|------|
| **SQLite** | All 67 turns (full messages) | ~18,600 tokens |
| **ANE Summary** | Compressed history | ~327 tokens |
| **Live Context** | Last ~15-20 turns | ~8,000 tokens |
| **To GPU Model** | Summary + Live Context | ~8,327 tokens |

**Savings:** From 18,600 → 8,327 tokens sent to GPU (55% reduction)

---

## Critical Design Decisions

### 1. **Read-Only Database Access**
- ANE daemon NEVER writes to `sessions.sqlite3`
- Prevents data corruption
- Simple recovery: restart daemon

### 2. **Pre-computed Summaries**
- Background compression runs continuously
- Compaction requests return instantly (no reprocessing)
- ANE works in parallel with GPU

### 3. **Boundary-Based Archival**
- `last_archived` position separates old vs new
- Old messages replaced by summary in prompts
- Old messages STILL in database (not deleted)

### 4. **Rolling Re-consolidation**
- Every 5 turns: merge facts, deduplicate
- Keeps summary concise and coherent
- New prompts emphasize deduplication

---

## Dream Mode (Separate Feature)

**Note:** Dream mode is a DIFFERENT feature in nanobot (not related to ANE compression).

**Purpose:** Generate reflections/insights from conversation history

**Timing:** Configurable, typically after longer idle periods

**Integration:** Can use ANE-compressed summaries as input for dreaming

**Files:** Separate from compression pipeline

---

## Troubleshooting Guide

### Issue: Nanobot can't remember recent details

**Diagnosis:**
1. Check if details are in archived portion (position <= last_archived)
2. Check ANE summary quality (is information preserved?)
3. Check re-consolidation frequency (every 5 turns)

**Solution:**
- Increase context window to keep more live turns
- Improve compression prompts for better fact retention
- Check if re-consolidation is deduplicating too aggressively

### Issue: Summary is repetitive

**Diagnosis:**
- Check compression prompts in `service.py`
- Check when last re-consolidation happened
- Inspect `ane_state.json` summary text

**Solution:**
- Update prompts to emphasize deduplication
- Restart daemon to load new prompts
- Wait for next re-consolidation (turn_count % 5 == 0)

### Issue: Compression not happening

**Diagnosis:**
1. Check daemon status: `./nanobot_ane/anectl status`
2. Check logs: `tail -f ~/.nanobot/logs/ane_daemon.log`
3. Check polling: Look for "Polling: new messages" logs

**Solution:**
- Restart daemon: `./nanobot_ane/anectl restart`
- Check SQLite permissions
- Verify WebSocket connection

---

## Files Reference

| File | Type | Purpose | Updated By | Persisted |
|------|------|---------|------------|-----------|
| `sessions.sqlite3` | SQLite | Authoritative message store | Nanobot | Yes |
| `ane_state.json` | JSON | ANE persisted state | ANE Daemon | Yes |
| `session_summaries{}` | In-Memory | Hot summary cache | ANE Daemon | No |
| `_sessions{}` | In-Memory | Turn detection buffer | ANE Daemon | No |
| `*.jsonl` | JSONL | Snapshots (deprecated) | Nanobot | Yes |

---

## Configuration Reference

### Nanobot (`~/.nanobot/config.json`)

```json
{
  "agents": {
    "defaults": {
      "idleCompactAfterMinutes": 1,
      "idleCompactCheckIntervalSeconds": 30,
      "contextWindowTokens": 32000
    }
  }
}
```

### ANE Daemon (command-line args)

```bash
python ane_daemon.py \
  --model ~/Build/Anemll/models/qwen3-1.7b-ctx2048 \
  --ws-url ws://127.0.0.1:8765 \
  --context-port 8766
```

---

## Recommended Tuning

### For Better Recall (Less Aggressive Compression)

- Increase live context: `contextWindowTokens: 64000`
- Less frequent compaction: `idleCompactAfterMinutes: 5`
- More frequent re-consolidation: Change from `% 5` to `% 3`

### For More Savings (Aggressive Compression)

- Smaller context: `contextWindowTokens: 16000`
- More frequent compaction: `idleCompactAfterMinutes: 0.5`
- Less frequent re-consolidation: Change from `% 5` to `% 10`

### Production Recommendation

Keep current settings (balanced):
- 32K context window
- 1 min idle compaction
- Re-consolidate every 5 turns
- Keep last 5 facts between consolidations

---

## Future Improvements

1. **Adaptive re-consolidation frequency** based on compression quality
2. **Importance scoring** for facts (keep important details longer)
3. **Multi-model compression** (use different models for different content types)
4. **Semantic deduplication** (detect paraphrased repetitions)
5. **User feedback loop** (learn what details matter most)

---

**Version:** 1.0 (2024-10-31)
**Last Updated:** After fixing repetitive compression prompts
