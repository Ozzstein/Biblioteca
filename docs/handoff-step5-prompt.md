# Step 5 handoff prompt

Paste this into the first message of the new Conductor workspace (the one that will own Step 5).

---

```
Branch off `main` as `Ozzstein/lab-knowledge-step5`.

Read `docs/handoff-step5.md` and `docs/review-step4.md`, in that order.

Execute Step 5 of the V2 lab-knowledge plan:
1. Expand `docs/api/v1.md` per `docs/handoff-step5.md` §5.4 + `docs/review-step4.md` F1 (citation payload format, streaming, idempotency, versioning policy, error model).
2. Build the three reference clients in `examples/writing-app/` (Claude Desktop config, Cursor config, custom Python agent).
3. Address the four follow-ups from `docs/review-step4.md`:
   - F2: dashboard CORS using `Settings.gateway_cors_origins`
   - F3: dashboard `/api/query` switching from `QueryAgent` to `QueryPlanner` (or document why not)
   - F4: gateway using `PROJECT_ROOT / "config/mcp-sources.yaml"` instead of relative path
4. Tests per the handoff brief §5.6.

Locked decisions you cannot revisit are listed at the top of `docs/handoff-step5.md`. Most important: NO bearer middleware (auth is Cloudflare Access end-to-end per CX16A), and no reporting templates / cite_pack tools (CX1B — assembly is the writing app's job, not the gateway's).

PR back to `main` when the acceptance criteria in `docs/handoff-step5.md` are met. The CTO-mode workspace will run an eng review on the PR before merge.
```

---

That's the whole prompt. The Step 5 agent doesn't need any other context from this conversation; the handoff brief and review verdict carry it.
