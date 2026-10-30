# ANE Compression Service for Nanobot

Background context compression using Apple Neural Engine (ANE) for nanobot agent conversations.

## Architecture

```
┌─────────────────────────────────────┐     ┌─────────────────────────────────┐
│          GPU Model Daemon           │     │           ANE Daemon            │
│      Bonsai 9B @ 31 tok/s           │     │      Qwen3-1.7B @ 20 tok/s      │
│      http://localhost:8080/v1       │     │      Background compression     │
└───────────────┬─────────────────────┘     └──────────────┬──────────────────┘
                │                                          │
                │ OpenAI API                               │ Polls JSONL
                │                                          │ Injects context
                ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Nanobot Agent                                  │
│                        ws://127.0.0.1:8765 (WebSocket)                      │
│                        http://127.0.0.1:8900 (REST API)                     │
│                                                                             │
│   Sessions stored as JSONL: ~/.nanobot/sessions/<workspace>/<session>.jsonl │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Why ANE?

This is a textbook-perfect use case for Apple Neural Engine:

| ANE Characteristic | How We Use It |
|-------------------|---------------|
| **Power efficient** | Background task running continuously - battery matters |
| **Parallel to GPU** | Main model on GPU, compression on ANE - no contention |
| **Not latency-critical** | ~15 sec/turn is fine - user is typing during compression |
| **Small models** | Qwen3-1.7B fits perfectly on ANE's memory |
| **Predictable workload** | Same model, similar prompts - ANE loves consistency |

**The key insight:** ANE is weak for interactive chat (latency matters) but strong for background inference where throughput and power efficiency matter more than speed.

This creates an **inference co-processor** pattern:
- **GPU:** Fast, interactive (user-facing)
- **ANE:** Efficient, background (housekeeping)

This is the kind of heterogeneous compute Apple Silicon was designed for.

## Processing Pipeline

```
JSONL File → Parse Messages → Group into Turns → Queue → Compress on ANE
              ↑                    ↑                         ↑
           CPU work           CPU work                  ANE work
          (milliseconds)     (milliseconds)           (~15 sec/turn)
```

1. **Processing (CPU):** Parse JSONL, filter tool calls, group user+assistant into turns
2. **Compression (ANE):** Extract facts, consolidate into rolling summary
3. **Injection:** Provide compressed context to RuntimeContextProvider before inference

## Components

| File | Purpose |
|------|---------|
| `ane_daemon.py` | Main daemon - WebSocket client, HTTP server, session polling |
| `service.py` | ANE compression service - fact extraction, summarization |
| `ane_inference.py` | CoreML model loading and inference on ANE |
| `session_db.py` | JSONL session file reader (base64-encoded filenames) |
| `ws_handler.py` | WebSocket message parser and turn grouping |
| `anectl` | Control script (start/stop/status/logs) |
| `nanobot_ane_patch.py` | Gateway patch for context injection |

## Usage

### Start the daemon
```bash
./nanobot_ane/anectl start
```

### Check status
```bash
./nanobot_ane/anectl status
```

### View logs
```bash
./nanobot_ane/anectl logs
```

### Check metrics
```bash
curl http://127.0.0.1:8766/metrics
```

### Get session context
```bash
curl http://127.0.0.1:8766/context/<session-id>
```

## Running as a Launch Service (macOS)

To run the daemon automatically on boot, install the launchd plist:

```bash
# Stop current daemon first
./nanobot_ane/anectl stop

# Install the launch agent
cp ~/Build/Anemll/nanobot_ane/com.anemll.ane-daemon.plist ~/Library/LaunchAgents/

# Load it (starts immediately and on every boot)
launchctl load ~/Library/LaunchAgents/com.anemll.ane-daemon.plist
```

**Management commands:**
```bash
# Stop
launchctl stop com.anemll.ane-daemon

# Start
launchctl start com.anemll.ane-daemon

# Unload (disable from boot)
launchctl unload ~/Library/LaunchAgents/com.anemll.ane-daemon.plist

# Check status
launchctl list | grep anemll
```

The service has `KeepAlive` enabled so it auto-restarts if it crashes.

**Note:** Edit the plist if your paths differ from the defaults.

## Configuration

The daemon uses these defaults (configurable via command line):

| Setting | Default | Description |
|---------|---------|-------------|
| `--model` | `~/Build/Anemll/models/qwen3-1.7b-ctx2048` | ANE model path |
| `--ws-url` | `ws://127.0.0.1:8765` | Nanobot WebSocket URL |
| `--context-port` | `8766` | HTTP server port for context injection |

## Metrics Example

```json
{
    "total_input_tokens": 10340,
    "total_output_tokens": 529,
    "compression_ratio": 19.55,
    "tokens_saved": 9811,
    "turns_compressed": 38,
    "avg_compression_time_ms": 15374.4,
    "active_sessions": 3
}
```

## Integration with Nanobot

The daemon integrates with nanobot via a patched `RuntimeContextProvider`:

1. Daemon polls `~/.nanobot/sessions/<workspace>/*.jsonl` for new messages
2. Compresses turns in background using ANE
3. Serves compressed context via HTTP at `http://127.0.0.1:8766/context/<session-id>`
4. Nanobot's gateway fetches context before each inference

### Applying the Nanobot Patch

The context injection requires patching `gateway_runtime.py` in the nanobot package.

```bash
# Check current status
python nanobot_ane/nanobot_ane_patch.py --status

# Apply the patch (creates backup automatically)
python nanobot_ane/nanobot_ane_patch.py --apply

# Revert if needed
python nanobot_ane/nanobot_ane_patch.py --revert

# Preview changes without applying
python nanobot_ane/nanobot_ane_patch.py --apply --dry-run
```

**What the patch does:**
- Adds `_ane_context_provider()` function to `gateway_runtime.py`
- Registers it to fetch compressed context from `http://127.0.0.1:8766/context/{session_id}`
- Injects compressed history into the prompt before each inference

### After Nanobot Upgrades

The patch modifies the installed nanobot package, so it will be **lost on upgrade**.

After upgrading nanobot (`pip install --upgrade nanobot`):
```bash
# Re-apply the patch
python nanobot_ane/nanobot_ane_patch.py --apply

# Restart gateway
launchctl kickstart -k gui/$(id -u)/com.nanobot.gateway
```

A backup is created at `gateway_runtime.py.bak` when applying.

### Log Verbosity (Optional)

To reduce nanobot gateway log verbosity, set `LOGURU_LEVEL` environment variable:

| Level | What you'll see |
|-------|-----------------|
| `CRITICAL` | Only critical errors |
| `ERROR` | Errors and critical |
| `WARNING` | Warnings and above (recommended for quieter logs) |
| `INFO` | Default - tool calls, turn completions |
| `DEBUG` | Maximum verbosity |

**In shell:**
```bash
export LOGURU_LEVEL=WARNING
```

**In launchd plist** (`~/Library/LaunchAgents/com.nanobot.gateway.plist`):
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>LOGURU_LEVEL</key>
    <string>WARNING</string>
</dict>
```

## Session Storage

Nanobot stores sessions in SQLite at:
```
~/.nanobot/sessions/<workspace_hash>/sessions.sqlite3
```

The `messages` table contains conversation history:
```sql
CREATE TABLE messages (
    session_key TEXT NOT NULL,  -- e.g., "websocket:b4fad3e3-..."
    position INTEGER NOT NULL,
    record TEXT NOT NULL,       -- JSON blob with role, content, etc.
    PRIMARY KEY (session_key, position)
);
```

**Note:** JSONL files in the same directory are periodic exports/snapshots, not the live storage.

## Requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Python 3.11+ with `websockets`, `aiohttp`, `coremltools`
- Converted Qwen3-1.7B model for ANE (see main ANEMLL docs)
- Running nanobot instance

## State Persistence

The daemon persists state to `~/.nanobot/run/ane_state.json`:
- Session summaries and facts
- Compression metrics
- Session positions (for incremental polling)

This allows the daemon to restart without losing compression history.

## License

Part of the ANEMLL project - Apache 2.0 License
