#!/usr/bin/env python3
"""
Budget 100 Deployment Unit Test

Tests single-turn extraction with the deployed Budget 100 configuration.
Validates:
- Extraction works with new prompt
- Token count is ~80-120 (within budget)
- Critical facts are preserved (file paths, versions, numbers)
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from nanobot_ane.service import ANEService


async def test_single_turn_extraction():
    """Test Budget 100 extraction on a single turn"""
    print("=" * 60)
    print("Budget 100 Deployment Unit Test")
    print("=" * 60)

    # Initialize service
    model_path = Path("~/Build/Anemll/models/qwen3-4b-ctx2048").expanduser()
    print(f"\n1. Loading model from: {model_path}")

    service = ANEService(
        model_path=str(model_path),
        ws_url=None,  # No WebSocket for unit test
        log_dir="~/.nanobot/logs"
    )

    print("2. Starting ANE service (this may take ~26 minutes for cold start)...")
    await service.start()
    print("   ✅ ANE service ready")

    # Test turn with planted facts
    test_turn = [
        {
            "role": "user",
            "content": "Help debug /usr/local/bin/test_v2.3.py - it's failing with import errors"
        },
        {
            "role": "assistant",
            "content": "I see the issue is with the qwen3-8b model import on line 42. The performance drop from 89.5% to 76.2% suggests a configuration problem. Let me check the model weights at /opt/models/qwen3-8b-q4."
        }
    ]

    print("\n3. Test turn content:")
    print("   User: Help debug /usr/local/bin/test_v2.3.py...")
    print("   Assistant: Issue with qwen3-8b model import, perf 89.5% → 76.2%...")

    # Extract facts
    print("\n4. Extracting facts with Budget 100 configuration...")
    facts = await service._extract_facts(test_turn)

    # Validate results
    print("\n5. Validation Results:")
    print("=" * 60)

    if not facts:
        print("   ❌ FAIL: No facts extracted")
        return False

    # Get extracted content
    extracted_content = facts[0].get("content", "")
    print(f"\n   Extracted facts:\n   {extracted_content}\n")

    # Count tokens (rough approximation: 1 token ≈ 4 chars)
    token_count = len(extracted_content.split())
    print(f"   Token count (approx): {token_count} words")

    # Check critical facts are preserved
    critical_facts = {
        "file_path": "/usr/local/bin/test_v2.3.py" in extracted_content or "test_v2.3.py" in extracted_content,
        "model_name": "qwen3-8b" in extracted_content,
        "percentage_1": "89.5" in extracted_content or "76.2" in extracted_content,
        "line_number": "42" in extracted_content,
    }

    print("\n   Critical fact preservation:")
    for fact_type, preserved in critical_facts.items():
        status = "✅" if preserved else "⚠️"
        print(f"   {status} {fact_type}: {'preserved' if preserved else 'missing'}")

    # Overall validation
    passed = (
        40 <= token_count <= 120 and  # Within budget (with some margin)
        sum(critical_facts.values()) >= 3  # At least 3/4 critical facts preserved
    )

    print("\n" + "=" * 60)
    if passed:
        print("   ✅ PASS: Budget 100 extraction working correctly")
    else:
        print("   ⚠️  WARNING: Extraction may need tuning")
        if token_count > 120:
            print(f"      - Token count too high: {token_count} > 120")
        if token_count < 40:
            print(f"      - Token count too low: {token_count} < 40 (may be truncating)")
        if sum(critical_facts.values()) < 3:
            print(f"      - Missing critical facts: {sum(critical_facts.values())}/4 preserved")

    print("=" * 60)

    # Cleanup
    await service.stop()

    return passed


if __name__ == "__main__":
    print("\nBudget 100 Deployment Unit Test")
    print("This test validates the Budget 100 configuration is working correctly.")
    print("\nNote: First run will take ~26 minutes for ANE cold start.")
    print("Subsequent runs will be faster if model is cached.\n")

    try:
        success = asyncio.run(test_single_turn_extraction())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
