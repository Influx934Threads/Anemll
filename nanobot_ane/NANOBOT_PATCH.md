# Nanobot ANE Context Provider Patch

This patch adds automatic ANE compressed context injection to nanobot.

## File to Modify

```
/Users/agundez/Build/benchmarking-setup/mlx-vlm/venv/lib/python3.11/site-packages/nanobot/cli/gateway_runtime.py
```

Or find it with:
```bash
python -c "import nanobot; print(nanobot.__file__.replace('__init__.py', 'cli/gateway_runtime.py'))"
```

## Changes

### 1. Add Import (after line ~44, after existing imports)

Add after `from nanobot.webui.dev import WebUIDevError, WebUIDevServer`:

```python
# ANE Context Provider
import aiohttp
from nanobot.runtime_context import RuntimeContextBlock
```

### 2. Add Provider Function (before `async def _run_gateway`, around line 50)

Add this function:

```python
# ANE Context Provider - fetches compressed history from ANE daemon
async def _ane_context_provider(request_context):
    """Fetch compressed context from ANE daemon."""
    session_key = getattr(request_context, 'session_key', None)
    if not session_key:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://127.0.0.1:8766/context/{session_key}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                context = data.get("context", "")
                if not context:
                    return None
                return RuntimeContextBlock(source="ane_compression", content=context)
    except Exception:
        return None
```

### 3. Register Provider (after `agent = AgentLoop.from_config(...)`, around line 499)

After the AgentLoop.from_config() call ends (after line with `recovery_admission=recovery,`), add:

```python
    # Register ANE context provider
    agent.register_runtime_context_provider(_ane_context_provider)
    logger.info("ANE context provider registered (http://127.0.0.1:8766)")
```

## After Patching

1. Restart nanobot gateway:
   ```bash
   nanobot gateway restart
   ```

2. Start ANE daemon (if not running):
   ```bash
   cd ~/Build/Anemll/nanobot_ane && ./anectl start
   ```

3. Verify in nanobot logs - you should see:
   ```
   ANE context provider registered (http://127.0.0.1:8766)
   ```

## How It Works

1. Before each LLM inference, nanobot calls all registered RuntimeContextProviders
2. Our `_ane_context_provider` fetches compressed context from `http://127.0.0.1:8766/context/{session_key}`
3. The compressed history is injected into the prompt automatically
4. The model sees: `[Conversation History Summary]\n<compressed summary>`

## Reverting

Keep a backup before patching:
```bash
cp gateway_runtime.py gateway_runtime.py.bak
```

To revert:
```bash
cp gateway_runtime.py.bak gateway_runtime.py
nanobot gateway restart
```
