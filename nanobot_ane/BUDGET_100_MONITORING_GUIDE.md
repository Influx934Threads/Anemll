# Budget 100 Post-Deployment Monitoring Guide

**Deployment Date**: 2026-11-06
**Configuration**: Qwen3-4B + Budget 100 per-turn extraction
**Expected Performance**: 100% recall, ~42% token savings, ~110 tokens per turn

---

## Quick Health Check Commands

### 1. Check Daemon Status
```bash
./anectl status
```

**Expected**:
- Status: Running
- Model: /Users/agundez/Build/Anemll/models/qwen3-4b-ctx2048
- Memory: ~400-600 MB (normal for 4B)

### 2. Check Budget 100 Metrics
```bash
curl -s http://127.0.0.1:8766/metrics | jq '{
  model,
  configuration,
  avg_extraction_tokens,
  budget_outliers,
  budget_outlier_rate,
  turns_compressed
}'
```

**Expected Values** (after compressions start):
- `avg_extraction_tokens`: 100-115 (target: ~110)
- `budget_outliers`: Low count (<5% of total)
- `budget_outlier_rate`: <0.05 (less than 5%)

### 3. Monitor Live Logs
```bash
tail -f ~/.nanobot/logs/ane_daemon.log
```

**Look for**:
- ✅ "Compressing turn" - normal operation
- ✅ "ANE model loaded successfully" - startup OK
- ⚠️ "Budget outlier: N tokens (>120)" - occasional is OK, frequent is concerning
- ❌ "ERROR" or "FAILED" - investigate immediately

### 4. Check Recent Compressions
```bash
tail -50 ~/.nanobot/logs/ane_daemon.log | grep "Compressing turn" -A 3
```

---

## Alert Thresholds

Monitor these metrics and investigate if exceeded:

| Metric | Target | Warning Threshold | Action Threshold |
|--------|--------|-------------------|------------------|
| `avg_extraction_tokens` | ~110 | >115 | >120 |
| `budget_outlier_rate` | <0.05 | >0.10 (10%) | >0.20 (20%) |
| Daemon crashes | 0 | 1 in 24h | 2 in 24h |
| User reports missing context | 0 | 1 | 2 |

**Actions if thresholds exceeded**:

1. **avg_extraction_tokens >120**:
   - Check if prompts were modified
   - Review recent conversation complexity
   - Consider if budget needs adjustment

2. **budget_outlier_rate >20%**:
   - Review prompt wording in NANOBOT_ANE_PROMPTS.md
   - Check if model is working correctly
   - Investigate outlier conversations in logs

3. **Daemon crashes**:
   - Check logs for error patterns
   - Verify memory availability
   - Consider rollback if persistent

4. **Missing context reports**:
   - **CRITICAL**: Check logs immediately
   - Compare with validation test results
   - Consider rollback if recall degraded

---

## Monitoring Schedule

**First 2 Hours** (Critical Window):
- Check metrics every 15 minutes
- Monitor logs actively
- Verify first 5-10 compressions look correct

**First 24 Hours**:
- Check metrics every 2-4 hours
- Review logs for errors
- Monitor for user complaints

**24-48 Hours**:
- Check metrics 2-3 times per day
- Verify stability (no crashes, consistent token counts)
- If stable, deployment successful ✅

---

## Example Monitoring Session

```bash
# 1. Quick status check
./anectl status

# 2. View metrics
curl -s http://127.0.0.1:8766/metrics | jq

# 3. Check recent activity
tail -30 ~/.nanobot/logs/ane_daemon.log

# 4. If issues, check for errors
grep -i error ~/.nanobot/logs/ane_daemon.log | tail -20

# 5. Check compression quality (state file)
cat ~/.nanobot/run/ane_state.json | jq '.sessions | to_entries | .[0].value | {turn_count, token_estimate, input_tokens}'
```

---

## Success Criteria

Deployment is successful if after 24-48 hours:

- ✅ Daemon running continuously (no crashes)
- ✅ avg_extraction_tokens: 100-115
- ✅ budget_outlier_rate: <5%
- ✅ No user reports of missing context
- ✅ No ERROR messages in logs
- ✅ Compression ratio maintained (>10x)

---

## Rollback Procedure

**If Budget 100 is failing**, rollback to 1.7B model:

```bash
# 1. Stop daemon
./anectl stop

# 2. Restore backups
cp service.py.backup-20261106-194217 service.py
cp ane_daemon.py.backup-20261106-194217 ane_daemon.py

# 3. Restart daemon
./anectl start

# 4. Verify rollback
curl http://127.0.0.1:8766/metrics | jq '.model'
# Should show: "qwen3-1.7b-ctx2048" (old model)
```

**Rollback triggers**:
- Multiple user reports of missing context
- avg_extraction_tokens consistently >125
- budget_outlier_rate >30%
- Daemon unstable (>3 crashes in 24h)

---

## Contact

For issues or questions about Budget 100 deployment:
- Review: `arms/arm_d/BUDGET_100_VALIDATION.md`
- Reference: `EXECUTIVE_SUMMARY.md`
- Tests: `arms/results/budget_variants_ane_seed*.json`

---

**Note**: This is the production monitoring guide. Budget 100 was validated across 3 seeds with 100% recall. Trust the validation, but monitor actively for the first 48 hours.
