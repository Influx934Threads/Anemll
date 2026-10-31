# Draft PR: ANE Compression Integration with Nanobot

**Target:** `Anemll/Anemll` (upstream)
**Source:** `Influx934Threads/Anemll` (fork)

When ready:
```bash
gh pr create --repo Anemll/Anemll --draft -F nanobot_ane/PR_DRAFT.md
```

---

## Summary

Integrates ANE (Apple Neural Engine) compression with nanobot's native compaction system. Summaries now **REPLACE** old messages via `last_archived` boundary, achieving real token savings instead of additive context bloat.

- ANE daemon polls nanobot's SQLite (READ-ONLY) and compresses turns continuously
- When nanobot's compaction triggers, it calls `POST /compress` to get pre-computed summary
- Tested: 54 turns → ~308 tokens (45.6x compression ratio)

## Changes

- `ane_daemon.py`: Add `POST /compress` endpoint
- `service.py`: Add `generate_summary_for_nanobot()`, fix metrics, add thread safety
- `session_db.py`: READ-ONLY access to nanobot's SQLite
- `nanobot_patches/`: Installer for nanobot-side integration (ane_client.py + memory.py patch)
- `INTEGRATION.md`: Architecture documentation

## Status

🧪 **Soak testing in progress** - not ready for review yet.

## Test plan

- [ ] Run for 1+ week with daily nanobot usage
- [ ] Verify compression metrics remain accurate
- [ ] Confirm no data corruption in nanobot sessions
- [ ] Test ANE daemon restart recovery

🤖 Generated with [Claude Code](https://claude.ai/code)
