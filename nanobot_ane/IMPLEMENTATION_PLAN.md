# Implementation Plan: Budget 100 Production Deployment

**Date**: 2026-11-06
**Status**: Ready for Implementation
**Target**: Deploy validated Budget 100 configuration on Qwen3-4B
**Timeline**: 1-2 days

---

## Executive Summary

Deploy the validated **Budget 100 per-turn extraction on Qwen3-4B** configuration to production, replacing the current 1.7B model and removing chunk-size optimization code.

**Validated Performance**:
- ✅ 100% recall (3/3 seeds)
- ✅ ~42% token savings vs unconstrained
- ✅ Production ready

---

## Phase 1: Pre-Deployment Validation (30 minutes)

### 1.1 Verify Model Availability

```bash
# Check 4B model exists
MODEL_PATH="/Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048"
test -d "$MODEL_PATH" && echo "✓ 4B model found" || echo "✗ 4B model MISSING"

# Check model files
ls -lh "$MODEL_PATH"/*.mlmodelc 2>/dev/null || echo "✗ No .mlmodelc files"
ls -lh "$MODEL_PATH"/tokenizer* 2>/dev/null || echo "✗ No tokenizer"
```

**If model missing**: Download/convert Qwen3-4B before proceeding.

### 1.2 Verify Test Results Exist

```bash
# Verify multi-seed validation results
cd ~/Build/Anemll/nanobot_ane/arms/results
ls -lh budget_variants_ane_seed*.json chunk_size_ane_seed*.json

# Expected files:
# - budget_variants_ane_seed202.json
# - budget_variants_ane_seed303.json
# - chunk_size_ane_seed101.json (contains Budget 100 = chunk1)
```

### 1.3 Backup Current Configuration

```bash
# Backup current service.py
cd ~/Build/Anemll/nanobot_ane
cp service.py service.py.backup-$(date +%Y%m%d-%H%M%S)

# Backup current daemon config
cp ane_daemon.py ane_daemon.py.backup-$(date +%Y%m%d-%H%M%S)

# Document current model
echo "Previous model: $(grep -A 2 'model_path' ane_daemon.py | head -3)" > migration.log
```

---

## Phase 2: Code Implementation (1 hour)

### 2.1 Update Extraction Prompt (service.py)

**File**: `service.py`

**Find** the current extraction method (likely `extract_facts()` or similar):

```python
# OLD (varies by current implementation)
def extract_facts(self, turn_text: str) -> str:
    # Current implementation with possible chunk-size logic
    ...
```

**Replace with**:

```python
def extract_facts(self, turn_text: str) -> str:
    """
    Extract facts from conversation turn using Budget 100.

    Validated configuration:
    - 100% recall (seeds 101, 202, 303)
    - ~42% token savings vs unconstrained
    - Production ready (2026-11-06)

    See: BUDGET_100_VALIDATION.md for validation details
    """
    prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤100 tokens):"""

    return self.inference.generate(
        prompt=prompt,
        max_tokens=120,      # 20% buffer for safety
        temperature=0.0       # Deterministic extraction
    )
```

**Key changes**:
- ✅ Exact "Target ≤100 tokens" wording (validated)
- ✅ max_tokens=120 (20% buffer)
- ✅ temperature=0.0 (deterministic)
- ✅ Per-turn extraction (no chunking)

### 2.2 Remove Chunk-Size Logic (if present)

**Search for chunk-size code**:

```bash
cd ~/Build/Anemll/nanobot_ane
grep -n "chunk" service.py
grep -n "window" service.py
```

**If found**, remove:
- Chunk window logic
- Variable budget scaling (100 × N)
- Multi-turn concatenation
- Any chunk-related parameters

**Keep it simple**: One extraction call per turn.

### 2.3 Update Model Configuration (ane_daemon.py or config)

**File**: `ane_daemon.py` (or wherever model path is configured)

**Find**:
```python
# OLD
model_path = "/Users/agundez/Build/Anemll/models/qwen3-1.7b-ctx2048"
# or similar
```

**Replace with**:
```python
# UPDATED - Budget 100 validated configuration (2026-11-06)
model_path = "/Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048"
```

**Also update any**:
- Model loading parameters
- Port configurations (ensure 8765 or consistent)
- Memory allocation (4B needs more than 1.7B)

### 2.4 Update Configuration Constants

**Search for any configuration constants**:

```bash
grep -n "EXTRACTION_" service.py
grep -n "BUDGET" service.py
grep -n "MAX_TOKENS" service.py
```

**Ensure**:
```python
# Budget 100 configuration
EXTRACTION_BUDGET = 100        # Target tokens per turn
EXTRACTION_MAX_TOKENS = 120    # Hard limit (20% buffer)
EXTRACTION_TEMPERATURE = 0.0   # Deterministic
```

---

## Phase 3: Testing (1 hour)

### 3.1 Unit Test - Single Turn Extraction

```bash
# Create test script
cat > ~/Build/Anemll/nanobot_ane/test_budget100_deployment.py << 'EOF'
#!/usr/bin/env python3
"""Test Budget 100 deployment on 4B model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from ane_inference import ANEInference
from service import CompressionService  # Or your service class

# Test single turn
test_turn = """User: Can you help me debug this Python script?
Assistant: Sure! Let me take a look. The issue appears to be in the file path '/usr/local/bin/test_v2.3.py' where you're using the wrong import for the qwen3-8b model."""

# Initialize service
service = CompressionService(model_path="/Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048")

# Extract facts
facts = service.extract_facts(test_turn)

print("=" * 70)
print("BUDGET 100 DEPLOYMENT TEST")
print("=" * 70)
print(f"\nInput turn:\n{test_turn}\n")
print(f"Extracted facts:\n{facts}\n")
print(f"Token count: {len(facts.split())}")  # Rough estimate
print("=" * 70)

# Validation
assert "test_v2.3.py" in facts or "/usr/local/bin" in facts, "FAIL: Missing file path"
assert "qwen3-8b" in facts, "FAIL: Missing model name"
print("\n✓ Test PASSED - Budget 100 working correctly")
EOF

python3 ~/Build/Anemll/nanobot_ane/test_budget100_deployment.py
```

**Expected**:
- Output contains planted facts (file path, model name)
- Token count ~80-110 tokens
- No errors/warnings

### 3.2 Load Test - Model Startup

```bash
# Stop any running daemon
./anectl stop

# Start with new configuration
./anectl start

# Monitor startup (26-min cold start expected for 4B)
./anectl logs -f

# Expected in logs:
# - "Loading model: qwen3-4b-ctx2048"
# - "Model loaded successfully"
# - "ANE daemon ready on port 8765"
```

**Cold start time**: ~26 minutes (one-time cost)
**Subsequent restarts**: Faster if model stays warm

### 3.3 Integration Test - Real Session

```bash
# Test on real nanobot session
curl http://127.0.0.1:8766/context/<recent-session-id>

# Verify:
# - Context is generated
# - Facts extracted
# - No errors in compression
```

### 3.4 Recall Validation - Spot Check

Manually verify a recent conversation:
1. Pick a session with known facts
2. Check extracted context
3. Verify all critical facts present

**Red flags**:
- Missing obvious facts (file paths, versions, decisions)
- Excessive tokens (>130 per turn average)
- Hallucinations (facts not in conversation)

---

## Phase 4: Monitoring Setup (30 minutes)

### 4.1 Add Token Tracking

**Update metrics endpoint** (`ane_daemon.py` or metrics handler):

```python
# Track Budget 100 metrics
metrics = {
    'extractions_total': 0,
    'tokens_total': 0,
    'tokens_avg': 0,
    'outliers_count': 0,  # Extractions >120 tokens
    'recalls_failed': 0    # User-reported missing context
}

def track_extraction(tokens: int):
    metrics['extractions_total'] += 1
    metrics['tokens_total'] += tokens
    metrics['tokens_avg'] = metrics['tokens_total'] / metrics['extractions_total']

    if tokens > 120:
        metrics['outliers_count'] += 1
        logger.warning(f"Budget 100 outlier: {tokens} tokens")
```

### 4.2 Setup Alerting

**Create alert thresholds**:

```python
# Alert if metrics degrade
ALERT_THRESHOLDS = {
    'tokens_avg_max': 115,      # Alert if avg >115 tokens
    'outliers_rate_max': 0.05,  # Alert if >5% outliers
}

def check_alerts():
    outlier_rate = metrics['outliers_count'] / metrics['extractions_total']

    if metrics['tokens_avg'] > ALERT_THRESHOLDS['tokens_avg_max']:
        logger.error(f"ALERT: Average tokens {metrics['tokens_avg']:.1f} exceeds threshold")

    if outlier_rate > ALERT_THRESHOLDS['outliers_rate_max']:
        logger.error(f"ALERT: Outlier rate {outlier_rate:.1%} exceeds threshold")
```

### 4.3 Dashboard Updates

**Add to metrics endpoint** (`/metrics`):

```json
{
  "model": "qwen3-4b-ctx2048",
  "configuration": "budget_100",
  "extractions_total": 1234,
  "tokens_avg": 108.3,
  "tokens_min": 45,
  "tokens_max": 119,
  "outliers_count": 12,
  "outliers_rate": 0.01,
  "recall_target": 1.0,
  "validated_seeds": [101, 202, 303]
}
```

---

## Phase 5: Deployment (15 minutes)

### 5.1 Stop Current Daemon

```bash
./anectl stop

# Verify stopped
./anectl status
# Expected: "ANE daemon is not running"
```

### 5.2 Deploy New Configuration

```bash
# Changes already made in Phase 2
# Just restart with new code

./anectl start

# Monitor startup
tail -f ~/.nanobot/logs/ane_daemon.log

# Wait for "Model loaded successfully" (26 minutes)
```

### 5.3 Verify Deployment

```bash
# Check status
./anectl status
# Expected: "ANE daemon is running (PID: XXXXX)"

# Check metrics
curl http://127.0.0.1:8766/metrics | jq

# Verify model
curl http://127.0.0.1:8766/metrics | jq '.model'
# Expected: "qwen3-4b-ctx2048"
```

### 5.4 Smoke Test

```bash
# Test extraction on live session
# (User should interact with nanobot to generate new turns)

# After a few turns, check context
curl http://127.0.0.1:8766/context/<session-id> | jq

# Verify:
# - Facts extracted
# - Token counts reasonable (~100-110 per turn)
# - No errors
```

---

## Phase 6: Post-Deployment Monitoring (24-48 hours)

### 6.1 Day 1 Monitoring Checklist

**Hour 1**:
- [ ] Daemon running stable
- [ ] No error spikes in logs
- [ ] First extractions completing
- [ ] Token averages in range (90-115)

**Hour 4**:
- [ ] Multiple sessions processed
- [ ] No user-reported missing context
- [ ] Metrics within thresholds
- [ ] Memory usage stable

**Hour 24**:
- [ ] Token average: 105-110 ✓
- [ ] Outlier rate: <5% ✓
- [ ] No recall failures ✓
- [ ] Performance stable ✓

### 6.2 Metrics to Watch

| Metric | Target | Red Flag |
|--------|--------|----------|
| Avg tokens/turn | 105-110 | >115 or <90 |
| Outlier rate (>120 tokens) | <5% | >10% |
| Recall failures | 0 | Any |
| Daemon uptime | 100% | Crashes |
| Memory usage | Stable | Growing |

### 6.3 User Feedback Collection

**Ask users**:
- "Any missing context in conversations?"
- "Does nanobot remember key details?"
- "Any hallucinations or incorrect facts?"

**Log feedback**:
```bash
# Create feedback log
echo "$(date): User feedback - <summary>" >> ~/Build/Anemll/nanobot_ane/deployment_feedback.log
```

---

## Phase 7: Cleanup (30 minutes)

### 7.1 Remove Deprecated Code

**After 48 hours of stable operation**:

```bash
cd ~/Build/Anemll/nanobot_ane

# Remove chunk-size test scripts (keep for reference/archive)
mkdir -p archive/chunk_size_investigation
mv arms/arm_d/test_chunk*.py archive/chunk_size_investigation/

# Remove old model references
# (Keep 1.7B model around for comparison/debugging for now)

# Update documentation
# Mark chunk-size findings as "historical"
```

### 7.2 Update Production Documentation

**Files to update**:

```bash
# Mark as PRODUCTION in headers
sed -i '' 's/Status: Validated/Status: PRODUCTION DEPLOYED/' PRODUCTION_CONFIG.md

# Add deployment date
echo "\n**Deployed**: $(date +%Y-%m-%d)\n" >> PRODUCTION_CONFIG.md
```

### 7.3 Archive Investigation Materials

```bash
# Create archive of investigation
mkdir -p archive/investigation_2026-11
cp -r arms/arm_d/*.md archive/investigation_2026-11/
cp arms/README.md archive/investigation_2026-11/

# Document deployment
cat > archive/investigation_2026-11/DEPLOYMENT_SUMMARY.md << 'EOF'
# Budget 100 Deployment Summary

**Deployed**: 2026-11-06
**Configuration**: Qwen3-4B + Budget 100
**Performance**: 100% recall, ~42% savings
**Status**: Production stable

See parent directory for complete investigation materials.
EOF
```

---

## Rollback Plan

**If Budget 100 deployment fails**:

### Rollback Steps (15 minutes)

```bash
# 1. Stop current daemon
./anectl stop

# 2. Restore backup configuration
cp service.py.backup-YYYYMMDD-HHMMSS service.py
cp ane_daemon.py.backup-YYYYMMDD-HHMMSS ane_daemon.py

# 3. Restart with old configuration
./anectl start

# 4. Verify rollback
./anectl status
curl http://127.0.0.1:8766/metrics | jq '.model'
# Should show old model (1.7B)

# 5. Investigate failure
# - Check logs: ./anectl logs
# - Review metrics before failure
# - Document issue in rollback_YYYYMMDD.md
```

### Rollback Triggers

Rollback if any:
- Recall failures reported by users
- Token average >120 sustained
- Daemon crashes repeatedly
- Memory issues
- >10% outlier rate

---

## Success Criteria

Deployment is successful when:

- ✅ 4B model loaded and running stable
- ✅ Budget 100 extraction working (token avg 105-110)
- ✅ No user-reported missing context
- ✅ Outlier rate <5%
- ✅ 48 hours stable operation
- ✅ Metrics within targets

**Then**: Mark as production, remove deprecated code, update docs.

---

## Timeline Summary

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| **Phase 1**: Pre-deployment validation | 30 min | 4B model available |
| **Phase 2**: Code implementation | 1 hour | Backups complete |
| **Phase 3**: Testing | 1 hour | Code changes done |
| **Phase 4**: Monitoring setup | 30 min | Testing passed |
| **Phase 5**: Deployment | 15 min + 26 min cold start | All tests passed |
| **Phase 6**: Post-deployment monitoring | 24-48 hours | Deployment stable |
| **Phase 7**: Cleanup | 30 min | Monitoring confirms success |

**Total active work**: ~3.5 hours
**Total elapsed**: 2-3 days (including monitoring period)

---

## Contact & Support

**Issues during deployment?**
- Check logs: `./anectl logs`
- Review metrics: `curl http://127.0.0.1:8766/metrics`
- Compare to validation results: `arms/arm_d/BUDGET_100_VALIDATION.md`
- Test against known-good seed: Run `test_budget_variants_ane.py --seed 101`

**Questions?**
- See `PRODUCTION_CONFIG.md` for configuration details
- See `BUDGET_100_VALIDATION.md` for validation methodology
- See `EXECUTIVE_SUMMARY.md` for quick reference

---

## Appendix: Configuration Reference

### Budget 100 Production Prompt (Exact Validated Wording)

```python
prompt = f"""Extract facts from this conversation turn. Target ≤100 tokens.
Be concise but clear. Abbreviate where unambiguous.
Preserve: numbers, percentages, file paths, specific names, measurements.

Turn:
{turn_text}

Facts (≤100 tokens):"""
```

**Critical**:
- ✅ "Target ≤100 tokens" (exact wording)
- ✅ max_tokens=120 (20% buffer)
- ✅ temperature=0.0 (deterministic)

**Do NOT**:
- ❌ Change wording ("limit to", "maximum", etc.)
- ❌ Use structured formats (JSON, XML)
- ❌ Increase max_tokens beyond 120
- ❌ Use temperature >0

### Model Configuration

```python
model_path = "/Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048"
port = 8765
cold_start_time = ~26  # minutes (one-time)
```

### Expected Performance

```python
performance_targets = {
    'recall': 1.0,              # 100% perfect recall
    'tokens_avg': 108,          # Average tokens per turn
    'tokens_min': 45,           # Minimum seen
    'tokens_max': 120,          # Hard limit
    'outliers_rate': 0.02,      # <5% target
    'savings': 0.42,            # ~42% vs unconstrained
}
```
