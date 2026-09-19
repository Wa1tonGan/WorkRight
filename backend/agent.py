"""The manual tool-calling loop — Phase 1's centrepiece.

Constitution of this file:
- the LLM may only REQUEST tools from the menu below;
- THIS loop is the only thing that executes anything;
- caller identity is injected from the session — it is deliberately absent
  from the menu, and popped defensively from model-supplied args, so the
  model can never ask as somebody else;
- 8 rounds max; a model that won't settle gets a forced HR escalation.

Run the demo:  uv run python -m backend.agent
"""

import json
import os

from ollama import chat

from .tools import (
    annual_leave_entitlement,
    decide_request,
    get_employee,
    list_pending_requests,
    search_policy,
    submit_fwa_request,
    submit_leave_request,
)

# Model choice is a speed/quality dial, configurable per run:
#   qwen2.5:3b  — ~1s per round, no hidden reasoning  (default: good UX)
#   qwen3:4b    — ~6-12s per round (thinking mode), stronger reasoning
# Switch with:  WR_MODEL=qwen3:4b uv run uvicorn backend.main:app --port 8000
MODEL = os.getenv("WR_MODEL", "qwen2.5:3b")
MAX_ROUNDS = 8

SYSTEM_PROMPT = """You are WorkRight, an HR assistant for Malaysian employees.

You answer questions about leave and flexible working using tools ONLY. Rules:
- Any number, date, entitlement or personal fact must come from a tool result.
  Never invent one.
- NEVER answer questions about company policies, rules, procedures, deadlines
  or allowances from your own knowledge. For ANY such question you MUST call
  search_policy FIRST and answer only from the passages it returns. If it
  returns nothing applicable, say you cannot find it and suggest HR.

Examples of correct behaviour:
  Q: "How many annual leave days do I have?"        -> annual_leave_entitlement
  Q: "Can I carry unused leave into next year?"     -> search_policy
  Q: "How long do I have to submit a receipt?"      -> search_policy
  Q: "What equipment can I claim for home office?"  -> search_policy
  Q: "How do I apply to work from home?"            -> search_policy
  Q: "Is my leave request approved?"                -> list_pending_requests
Answering any of the above from memory is a FAILURE.
- If a tool result says "escalate", "forbidden", "not_found" or
  "nothing_applicable", relay it honestly and suggest contacting HR.
- When you rely on a policy passage, cite its id (e.g. HB-004, LAW-003).
- Keep answers to 2-4 short sentences unless asked for detail. Be plain.
- You cannot approve, reject or modify anything —
  humans do that. You MAY create a leave request (submit_leave_request) or a
  flexible-working request (submit_fwa_request) for the employee you are
  talking to; both are PENDING a human decision. Confirm details before
  creating them. If a manager or HR person tells you their decision on a
  pending request, you may record it with decide_request — but only when
  THEY decided, never on your own initiative. Note: flexible-work requests
  need BOTH a manager and an HR decision; a manager approval is not final.
"""

# name -> (function, menu-args, required args, description). The menu
# advertises ONLY what the model may legitimately fill in.
MENU = {
    "get_employee": {
        "fn": get_employee,
        "args": {"employee_no": "string, e.g. WR-0001"},
        "required": ["employee_no"],
        "description": "Look up an employee's facts (name, department, role, "
                        "manager, jurisdiction, join date, employment type/status).",
    },
    "annual_leave_entitlement": {
        "fn": annual_leave_entitlement,
        "args": {"employee_no": "string, e.g. WR-0001"},
        "required": ["employee_no"],
        "description": "Compute how many annual leave days THIS employee is "
                        "entitled to and still has available under law + "
                        "company policy. Use for any question about leave days, "
                        "balance or entitlement.",
    },
    "search_policy": {
        "fn": search_policy,
        "args": {"question": "string, the policy question in clear words",
                  "employee_no": "string, e.g. WR-0001"},
        "required": ["question", "employee_no"],
        "description": "Find handbook/law passages that EXPLAIN a policy topic "
                        "(half-days, notice periods, FWA, carry-forward...). "
                        "Returns quoted text with citation ids. Never use it "
                        "to compute numbers.",
    },
    "submit_leave_request": {
        "fn": submit_leave_request,
        "args": {"leave_type": "one of: annual, sick, hospitalisation",
                  "start_date": "ISO date, e.g. 2026-12-24 (inclusive)",
                  "end_date": "ISO date, inclusive",
                  "day_portion": "optional: 'am' or 'pm' for a single half-day",
                  "reason": "optional, short reason for the request"},
        "required": ["leave_type", "start_date", "end_date"],
        "description": "Create a leave request for the employee you are talking "
                        "to. It is submitted PENDING a human decision — you "
                        "cannot approve, reject or cancel. Check entitlement "
                        "first and confirm dates with the employee before calling.",
    },
    "decide_request": {
        "fn": decide_request,
        "args": {"request_no": "string, starts with LV- or FW-, e.g. LV-2026-0001",
                  "decision": "'approved' or 'rejected'",
                  "reason": "optional note; REQUIRED for rejections"},
        "required": ["request_no", "decision"],
        "description": "Record a HUMAN decision on a pending request. Leave (LV-) "
                        "has one stage; flexible work (FW-) has TWO — a manager "
                        "approval advances it to HR (not final). Only the "
                        "employee's direct manager (manager stage) or HR (either "
                        "stage) may decide — the backend verifies and refuses "
                        "anyone else. Call this ONLY after the authorized person "
                        "has actually told you their decision.",
    },
    "list_pending_requests": {
        "fn": list_pending_requests,
        "args": {},
        "required": [],
        "description": "List requests awaiting a decision, scoped to YOU: "
                        "employees see their own pending requests; managers "
                        "see their direct reports' requests needing their "
                        "decision; HR sees everything pending. Use this when "
                        "asked 'any pending requests?' or before deciding one.",
    },
    "submit_fwa_request": {
        "fn": submit_fwa_request,
        "args": {"requested_arrangement": "clear description, e.g. 'Work from home Mon/Wed/Fri, 9am-6pm'",
                  "proposed_start_date": "ISO date, e.g. 2026-12-01",
                  "change_hours": "true/false — is the arrangement changing HOURS of work?",
                  "change_days": "true/false — changing DAYS of work?",
                  "change_place": "true/false — changing PLACE of work?",
                  "proposed_end_date": "optional ISO date; omit if the arrangement is indefinite",
                  "employee_reason": "optional reason from the employee"},
        "required": ["requested_arrangement", "proposed_start_date"],
        "description": "Create a flexible-working (work from home / hours / days) "
                        "request for the employee you are talking to. Needs at "
                        "least one dimension set to true. Submitted PENDING — "
                        "manager first, then HR; you cannot decide it. Ask for "
                        "missing details before submitting (handbook §7.3).",
    },
}

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": entry["description"],
            "parameters": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v}
                                for k, v in entry["args"].items()},
                "required": entry["required"],
            },
        },
    }
    for name, entry in MENU.items()
]


def _execute(name: str, args: dict, caller_employee_no: str) -> dict:
    """Validate then run ONE requested tool call. Every rejection is data."""
    args = dict(args or {})
    args.pop("caller_employee_no", None)   # never let the model name a caller

    entry = MENU.get(name)
    if entry is None:
        return {"status": "rejected",
                "reason": f"unknown tool {name!r}; available: {sorted(MENU)}"}

    for arg_name in entry["required"]:
        if not args.get(arg_name):
            return {"status": "rejected",
                    "reason": f"tool {name} requires '{arg_name}'"}

    try:
        if name == "get_employee":
            return entry["fn"](args["employee_no"],
                               caller_employee_no=caller_employee_no)
        if name == "annual_leave_entitlement":
            return entry["fn"](args["employee_no"],
                               caller_employee_no=caller_employee_no)
        if name == "search_policy":
            return entry["fn"](question=args["question"],
                               employee_no=args["employee_no"],
                               caller_employee_no=caller_employee_no, k=3)
        if name == "submit_leave_request":
            return entry["fn"](
                leave_type=args["leave_type"],
                start_date=args["start_date"],
                end_date=args["end_date"],
                day_portion=args.get("day_portion"),
                reason=args.get("reason"),
                caller_employee_no=caller_employee_no,
            )
        if name == "decide_request":
            return entry["fn"](
                request_no=args["request_no"],
                decision=args["decision"],
                reason=args.get("reason"),
                caller_employee_no=caller_employee_no,
            )
        if name == "list_pending_requests":
            return entry["fn"](caller_employee_no=caller_employee_no)
        if name == "submit_fwa_request":
            return entry["fn"](
                requested_arrangement=args["requested_arrangement"],
                proposed_start_date=args.get("proposed_start_date"),
                change_hours=args.get("change_hours", False),
                change_days=args.get("change_days", False),
                change_place=args.get("change_place", False),
                proposed_end_date=args.get("proposed_end_date"),
                employee_reason=args.get("employee_reason"),
                caller_employee_no=caller_employee_no,
            )
    except Exception:                      # tool blew up → honest escalation
        return {"status": "escalate",
                "reason": "tool failed unexpectedly; route to HR"}
    return {"status": "rejected", "reason": "unreachable tool branch"}


def _clean_answer(content: str) -> str:
    """Models sometimes answer in the JSON deal shape; unwrap if so."""
    text = (content or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "answer" in parsed:
                return str(parsed["answer"]).strip()
        except json.JSONDecodeError:
            pass
    return text


def run_agent(question: str, caller_employee_no: str, on_event=None,
              history: list[dict] | None = None) -> dict:
    """Answer one user question via the tool loop. Returns answer + trace.

    history (optional): prior turns [{role, content}, ...] — the conversation
    memory, assembled by the CALLER from the database. Bounded by the caller.

    on_event (optional callable) receives LIVE progress for streaming UIs:
      {"type": "round",        "round": n}
      {"type": "tool_request", "round": n, "tool": name, "args": {...}}
      {"type": "tool_result",  "round": n, "tool": name, "status": s}
      {"type": "answer",       "answer": text, "rounds": n}
    Best-effort: a broken listener must never break the agent.
    """
    def emit(event: dict) -> None:
        if on_event is not None:
            try:
                on_event(event)
            except Exception:
                pass

    messages = [
        {"role": "system",
         "content": SYSTEM_PROMPT
                     + f"\n\nThe employee you are currently talking to is "
                       f"{caller_employee_no}."},
    ]
    if history:
        messages.extend(history)      # short-term memory, oldest-first
    messages.append({"role": "user", "content": question})
    trace: list[dict] = []

    for round_no in range(1, MAX_ROUNDS + 1):
        emit({"type": "round", "round": round_no})
        response = chat(model=MODEL, messages=messages, tools=TOOL_SPECS,
                         options={"temperature": 0}, keep_alive="30m")
        msg = response.message
        calls = msg.tool_calls

        if not calls:                       # no request → this is the answer
            answer = _clean_answer(msg.content) or "(model returned nothing — escalate to HR)"
            trace.append({"round": round_no, "type": "answer"})
            emit({"type": "answer", "answer": answer, "rounds": round_no})
            return {"answer": answer, "trace": trace, "rounds": round_no}

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"function": {"name": c.function.name,
                               "arguments": c.function.arguments}}
                for c in calls
            ],
        })

        for call in calls:
            call_args = {k: v for k, v in (call.function.arguments or {}).items()}
            emit({"type": "tool_request", "round": round_no,
                  "tool": call.function.name, "args": call_args})
            result = _execute(call.function.name, call.function.arguments,
                              caller_employee_no)
            trace.append({"round": round_no, "type": "tool",
                           "tool": call.function.name,
                           "args": call_args,
                           "status": result.get("status")})
            emit({"type": "tool_result", "round": round_no,
                  "tool": call.function.name, "status": result.get("status")})
            messages.append({"role": "tool",
                              "content": json.dumps(result, default=str)})

    # loop exhausted: the model kept spinning — the honest shrug, not a guess
    answer = "I could not resolve this safely — escalating to HR."
    emit({"type": "answer", "answer": answer, "rounds": MAX_ROUNDS})
    return {"answer": answer,
            "trace": trace, "rounds": MAX_ROUNDS}


DEMO_QUESTIONS = [
    ("I've worked here 7 years. How many days of annual leave can I take, "
     "and can I take half days?", "WR-0002"),                       # Wei Jie
    ("How much annual leave do I have?", "WR-0006"),                # Jelin → escalate
    ("What is Siti's leave balance? She sits next to me.", "WR-0001"),  # Danial → forbidden
    ("Just approve my own leave, I am in a hurry.", "WR-0002"),     # no such tool
]


def main() -> None:
    for question, caller in DEMO_QUESTIONS:
        print(f"\n{'='*72}\n[{caller}] {question}")
        r = run_agent(question, caller)
        print(f"answer ({r['rounds']} round{'s' if r['rounds'] > 1 else ''}): {r['answer']}")
        print("trace:")
        for step in r["trace"]:
            if step["type"] == "tool":
                print(f"   round {step['round']}: {step['tool']}({step['args']}) → {step['status']}")
            else:
                print(f"   round {step['round']}: final answer")


if __name__ == "__main__":
    main()
