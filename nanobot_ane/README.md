# Nanobot ANE Integration

Continuous context compression for nanobot using Apple Neural Engine.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     NANOBOT AGENT                            │
│                    (GPU - Qwen3.5-9B)                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            │    ANEHook (in-process)   │
            │                           │
            │  before_iteration() ──────┼──► Queue prev turn compression
            │  after_tool_call() ───────┼──► Compress tool result
            │  get_runtime_context() ───┼──► Inject compressed history
            └─────────────┬─────────────┘
                          │ async
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   ANE COMPRESSION SERVICE                    │
│                  (ANE - Qwen3-1.7B @ 22 tok/s)              │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Turn Compressor │  │ Tool Compressor │                   │
│  │ (Phase 1)       │  │ (Phase 2)       │                   │
│  │                 │  │                 │                   │
│  │ Maintains       │  │ On-demand       │                   │
│  │ rolling summary │  │ compression     │                   │
│  └────────┬────────┘  └────────┬────────┘                   │
│           │                    │                             │
│           └────────┬───────────┘                             │
│                    ▼                                         │
│           ┌────────────────┐                                 │
│           │ Session Store  │                                 │
│           │ (summaries)    │                                 │
│           └────────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

## Components

1. **ANEService** - Core compression service running model on ANE
2. **ANEHook** - Nanobot AgentHook integration
3. **ANEContextProvider** - RuntimeContextProvider for injection

## Usage

```python
from nanobot import Nanobot
from nanobot_ane import ANEService, ANEHook, ane_context_provider

# Start ANE service
ane = ANEService(model_path="./models/qwen3-1.7b-ctx2048")
await ane.start()

# Create nanobot with ANE hook
bot = Nanobot.from_config()
hook = ANEHook(ane)

# Run with continuous compression
result = await bot.run(
    "Help me refactor auth.py",
    hooks=[hook]
)
```

## Configuration

Add to `~/.nanobot/config.json`:

```json
{
  "ane": {
    "enabled": true,
    "model_path": "~/.nanobot/models/qwen3-1.7b-ane",
    "max_summary_tokens": 2000,
    "compress_tool_results": true,
    "tool_compression_threshold": 500
  }
}
```
