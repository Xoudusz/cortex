---
name: cortex-index
description: >
  Trigger cortex reindex and track progress.
  Use when: search results are stale, user pushed new code, user updated notes,
  or starting a session after a long gap.
---

# cortex reindex

## When to reindex

- Search returns stale or missing results
- User says they pushed new code or updated notes
- Starting after a long gap (index may be outdated)
- User explicitly asks to reindex

## Tools

| Tool | Use for |
|------|---------|
| `reindex` | Trigger async reindex (returns immediately) |
| `reindex_status` | Check progress and output log |

## Parameters

```python
reindex()                          # reindex everything
reindex(notes=False)               # code only
reindex(code=False)                # notes only
reindex(repo="my-repo")            # one repo only
reindex(code=True, repo="cortex")  # one repo, code only
```

## Workflow

1. Call `reindex(...)` — starts async job, returns queue position
2. Wait ~10-30s (depending on repo size)
3. Call `reindex_status()` — check if done, see output log
4. Repeat step 3 until status shows "done"
5. Search again to verify results are fresh
