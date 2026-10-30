#!/usr/bin/env python3
"""
Test script for ANE compression service.

Tests:
1. Direct ANEInference for basic generation
2. ANEService for compression tasks
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanobot_ane import ANEInference, ANEService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_direct_inference():
    """Test direct ANEInference generation."""
    print("\n" + "="*60)
    print("TEST 1: Direct ANE Inference")
    print("="*60)

    model_path = Path("~/Build/Anemll/models/qwen3-1.7b-ctx2048").expanduser()

    if not model_path.exists():
        print(f"Model not found at {model_path}")
        print("Please download Qwen3-1.7B model first")
        return False

    print(f"\nLoading model from {model_path}...")
    inference = ANEInference(model_path)
    await inference.load()

    # Test simple generation
    prompt = "Extract the key fact: The user prefers Python over JavaScript for backend development."

    print(f"\nPrompt: {prompt}")
    print("\nGenerating (max 50 tokens)...")

    import time
    start = time.time()
    result = await inference.generate(prompt, max_tokens=50, temperature=0.3)
    elapsed = time.time() - start

    print(f"\nResult: {result}")
    print(f"Time: {elapsed:.2f}s")

    return True


async def test_compression_service():
    """Test ANEService compression."""
    print("\n" + "="*60)
    print("TEST 2: ANE Compression Service")
    print("="*60)

    model_path = Path("~/Build/Anemll/models/qwen3-1.7b-ctx2048").expanduser()

    if not model_path.exists():
        print(f"Model not found at {model_path}")
        return False

    print(f"\nStarting ANE service...")
    service = ANEService(model_path)
    await service.start()

    # Test turn compression
    test_turn = [
        {"role": "user", "content": "Can you help me set up a Python virtual environment for my ML project?"},
        {"role": "assistant", "content": "Of course! Here's how to set up a Python virtual environment:\n\n1. First, make sure you have Python 3.9+ installed\n2. Run: python -m venv ml-env\n3. Activate it: source ml-env/bin/activate\n4. Install your dependencies: pip install numpy pandas torch\n\nWould you like me to help with any specific ML libraries?"}
    ]

    print("\nQueueing turn for compression...")
    await service.queue_turn_compression("test_session", test_turn)

    # Wait for compression
    print("Waiting for compression worker...")
    await asyncio.sleep(3)

    # Check session context
    context = service.get_session_context("test_session")
    stats = service.get_session_stats("test_session")

    print(f"\nSession context: {context[:200]}..." if len(context) > 200 else f"\nSession context: {context}")
    print(f"\nSession stats: {stats}")

    # Test tool compression
    print("\n--- Tool Result Compression ---")
    large_tool_output = """
    File: /Users/test/project/main.py
    Lines: 1-500

    import os
    import sys
    from pathlib import Path
    import logging

    # Configuration
    CONFIG = {
        'debug': True,
        'log_level': 'INFO',
        'max_retries': 3,
        'timeout': 30,
    }

    def setup_logging():
        logging.basicConfig(
            level=getattr(logging, CONFIG['log_level']),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def main():
        logger = setup_logging()
        logger.info("Starting application...")
        # ... more code ...
    """ * 3  # Make it larger

    print(f"Original size: {len(large_tool_output)} chars")
    compressed = await service.compress_tool_result(large_tool_output)
    print(f"Compressed size: {len(compressed)} chars")
    print(f"Compression ratio: {len(compressed)/len(large_tool_output):.1%}")

    await service.stop()
    return True


async def main():
    """Run all tests."""
    print("\nNanobot ANE Integration Tests")
    print("="*60)

    results = {}

    try:
        results['direct_inference'] = await test_direct_inference()
    except Exception as e:
        logger.error(f"Direct inference test failed: {e}")
        results['direct_inference'] = False

    try:
        results['compression_service'] = await test_compression_service()
    except Exception as e:
        logger.error(f"Compression service test failed: {e}")
        results['compression_service'] = False

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
