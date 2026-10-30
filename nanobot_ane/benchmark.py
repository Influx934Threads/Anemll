#!/usr/bin/env python3
"""
Benchmark ANE inference for compression tasks.

Measures:
- Token generation speed (tok/s)
- Latency for typical compression prompts
- Comparison with expected speeds
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nanobot_ane import ANEInference


async def benchmark_generation(inference: ANEInference, prompt: str, max_tokens: int, label: str):
    """Benchmark a single generation."""
    print(f"\n--- {label} ---")
    print(f"Prompt: {prompt[:80]}..." if len(prompt) > 80 else f"Prompt: {prompt}")
    print(f"Max tokens: {max_tokens}")

    start = time.perf_counter()
    result = await inference.generate(prompt, max_tokens=max_tokens, temperature=0.0)
    elapsed = time.perf_counter() - start

    # Estimate tokens generated (rough)
    result_tokens = len(result.split()) * 1.3  # rough estimate
    tok_per_sec = result_tokens / elapsed if elapsed > 0 else 0

    print(f"Result: {result[:100]}..." if len(result) > 100 else f"Result: {result}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Est. tokens: ~{result_tokens:.0f}")
    print(f"Speed: ~{tok_per_sec:.1f} tok/s")

    return elapsed, result_tokens


async def main():
    print("="*70)
    print("ANE Compression Benchmark - Qwen3-1.7B")
    print("="*70)

    model_path = Path("~/Build/Anemll/models/qwen3-1.7b-ctx2048").expanduser()

    if not model_path.exists():
        print(f"ERROR: Model not found at {model_path}")
        return

    print(f"\nLoading model from {model_path}...")
    load_start = time.perf_counter()
    inference = ANEInference(model_path)
    await inference.load()
    load_time = time.perf_counter() - load_start
    print(f"Model loaded in {load_time:.2f}s")

    # Warmup
    print("\n--- Warmup ---")
    await inference.generate("Hello", max_tokens=5, temperature=0.0)
    print("Warmup complete")

    # Benchmark scenarios
    results = []

    # 1. Short fact extraction (typical Phase 1)
    prompt1 = """Extract key facts from this conversation turn.
Output as JSON array of facts, each with "type" and "content".

Turn:
user: Can you help me set up a Python virtual environment?
assistant: Sure! Run: python -m venv myenv && source myenv/bin/activate

Facts (JSON array):"""

    results.append(await benchmark_generation(
        inference, prompt1, max_tokens=100,
        label="Fact Extraction (Phase 1 - Turn Compression)"
    ))

    # 2. Tool result compression (Phase 2)
    prompt2 = """Compress this tool output to its essential information.
Keep key data, remove redundancy. Be concise but complete.

Tool output:
File: /Users/test/project/main.py (lines 1-50)
import os
import sys
from pathlib import Path
import logging
import json

CONFIG = {
    'debug': True,
    'log_level': 'INFO',
    'max_retries': 3,
    'timeout': 30,
}

def setup_logging():
    logging.basicConfig(level=getattr(logging, CONFIG['log_level']))
    return logging.getLogger(__name__)

def main():
    logger = setup_logging()
    logger.info("Starting...")

Compressed:"""

    results.append(await benchmark_generation(
        inference, prompt2, max_tokens=150,
        label="Tool Result Compression (Phase 2)"
    ))

    # 3. Summary consolidation
    prompt3 = """Consolidate these facts into a brief summary paragraph.
Keep only the most important information. Be concise.

Facts:
- [preference] User prefers Python for backend
- [context] Working on ML project with PyTorch
- [decision] Using virtual environment for isolation
- [task] Need to install numpy, pandas, torch
- [result] Successfully created venv

Summary:"""

    results.append(await benchmark_generation(
        inference, prompt3, max_tokens=100,
        label="Summary Consolidation (Phase 1 - Merge)"
    ))

    # 4. Longer generation test
    prompt4 = "Explain the key benefits of using Apple Neural Engine for ML inference in 3 bullet points:"

    results.append(await benchmark_generation(
        inference, prompt4, max_tokens=200,
        label="Longer Generation Test"
    ))

    # Summary
    print("\n" + "="*70)
    print("BENCHMARK SUMMARY")
    print("="*70)

    total_time = sum(r[0] for r in results)
    total_tokens = sum(r[1] for r in results)
    avg_speed = total_tokens / total_time if total_time > 0 else 0

    print(f"Total time: {total_time:.2f}s")
    print(f"Total tokens (est): ~{total_tokens:.0f}")
    print(f"Average speed: ~{avg_speed:.1f} tok/s")
    print(f"\nExpected Qwen3-1.7B speed: ~22 tok/s")
    print(f"Model load time: {load_time:.2f}s")

    # Context for nanobot integration
    print("\n" + "="*70)
    print("NANOBOT INTEGRATION CONTEXT")
    print("="*70)
    print("""
Typical GPU agent (Qwen3.5-9B Bonsai): ~31 tok/s
ANE compression (Qwen3-1.7B): ~22 tok/s

For a 10-second GPU generation (~310 tokens):
- ANE can process ~220 tokens of compression work
- Typical turn compression: <100 tokens output
- This allows 2-3 turns to be compressed while GPU thinks

Key insight: ANE compression runs IN PARALLEL with GPU inference,
so the effective cost to the user is near-zero latency.
""")


if __name__ == "__main__":
    asyncio.run(main())
