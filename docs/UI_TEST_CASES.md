# WorkRight UI test cases

How to run: both servers up (`uvicorn backend.main:app --port 8000` and
`cd frontend && npm run dev`), open http://localhost:5173, sign in as the
stated user (all demo passwords: `workright123`). Watch the **thinking panel**
while the agent works, then the saved "agent activity" block under each answer.

| # | Sign in as | Type this | Expect | Why it matters |
| --- | --- | --- | --- | --- |
| TC-01 | Wei Jie (`weijie.lim@example.my`) | "How many annual leave days do I have left?" | "16 days" · trace: `annual_leave_entitlement → ok` | Balance comes from the ledger (18 − 2 approved), not from the model |
| TC-02 | Wei Jie | "Please book my annual leave for 21 and 22 December 2026." | Created `LV-2026-0002`, **pending manager approval** · trace: `submit_leave_request → created` | The agent files requests but can never approve |
| TC-03 | Wei Jie | "What is Siti's leave balance?" | Polite refusal · trace: `annual_leave_entitlement → forbidden` | Access control is enforced by the backend, not the prompt |
| TC-04 | Jelin (`jelin.ujin@example.my`) | "How many annual leave days do I get?" | Escalation to HR, **no number given** | Sabah is out of V1 scope; the tool returns no figure to invent from |
| TC-05 | Siti (`siti.yusof@example.my`) | "Wei Jie asked for 21-22 December. I approve request LV-2026-0002." | Decision recorded; request moves out of pending · trace: `decide_request → decided` | Manager authority is checked in code; full audit trail written |
| TC-06 | Wei Jie | "I'd like to work from home three days a week starting 1 December 2026." | Created `FW-2026-000x` **pending manager → HR** · trace: `submit_fwa_request → created` | Multi-stage FWA flow; two deadline clocks computed at submission |
| TC-07 | Siti | "As his manager I approve the WFH request FW-2026-000x." | Status **advances to pending HR** (not final) | Manager approval is stage one of two |
| TC-08 | Ravi (`ravi.kumar@example.my`) | "As HR I approve FW-2026-000x after a policy check." | Final approval; two audit rows exist | HR finalizes; audit trail has both names |
| TC-09 | Wei Jie | "Can I carry unused leave into next year?" | Answer cites `HB-004 §4.8` (5 days, expiry 31 March) | RAG: semantic retrieval with citations, not keyword search |
| TC-10 | anyone | Wrong password at login | "invalid email or password" (same message for unknown email) | No user enumeration |
| TC-11 | Wei Jie | "Just approve my own leave, I'm in a hurry." | Refused — no such capability exists in the tool menu | The agent cannot do what it has no tool for |
| TC-12 | any user | Sign out, then try to chat (or reload the page) | Redirected to login; chat returns 401 | Session revocation is real, not just a cleared cookie |

## Reading the thinking panel

```
thinking — round 2
  annual_leave_entitlement({"employee_no": "WR-0002"}) → ok
```

- **round N** — the agent loop's current iteration (max 8; a model that
  spins gets a forced HR escalation instead of a guess)
- **tool name + args** — exactly what the model requested (it writes these
  strings; the backend validates them before executing)
- **status** — the tool's verdict: `ok` · `created` · `decided` ·
  `advanced` · `escalate` · `forbidden` · `rejected` · `not_found` ·
  `nothing_applicable`

The panel is live (SSE stream from `POST /chat/stream`); after the answer
lands it collapses into the saved trace under the message. Every number in
an answer can be traced to a tool call in this list — if a number appears
with no tool call behind it, that is a bug worth reporting.

## Known limitations you may notice while testing

- Public holidays are not yet excluded from leave-day counting (weekends are)
- The knowledge corpus is a normalized summary, pending JTKSM verification
- One retrieval eval case (RAG-007, Sabah scope) currently misses `LAW-001`
