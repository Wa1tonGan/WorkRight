# WorkRight Labs Sdn. Bhd.
## Employee Leave & Flexible Work Policy Handbook — V1

**Policy version:** 1.0  
**Effective date:** 1 January 2026  
**Purpose:** Fictional company policy for the WorkRight AI-agent learning project

> This handbook is fictional, created for an educational AI-agent project, and is not legal advice.

# 1. Purpose
This policy sets WorkRight Labs Sdn. Bhd.'s internal rules for:
- annual leave;
- paid sick leave;
- hospitalisation leave;
- Flexible Working Arrangements (FWA);
- approvals and escalation.

# 2. Scope
The automated V1 policy process applies to active full-time employees in:
- Peninsular Malaysia; and
- Federal Territory of Labuan.

The agent must refer these cases to HR:
- Sabah;
- Sarawak;
- part-time employment;
- unsupported employment arrangements;
- unclear legal/contractual circumstances.

# 3. Relationship with Malaysian Law
- WorkRight Labs will not apply a company rule that reduces an applicable statutory minimum.
- Where this handbook gives a more favourable valid benefit, the WorkRight benefit applies.
- Ambiguous conflicts between law and company policy must be referred to HR.
- The AI agent may explain and route a case, but may not override statutory protections or invent company rules.

# 4. Annual Leave Policy

## 4.1 Entitlement
Active full-time employees receive **18 days of paid annual leave per calendar year**.

Any required pro-rating for joiners or leavers is calculated by deterministic backend rules.

## 4.2 Half-Day Leave
Annual leave may be requested as:
- full day;
- AM half-day;
- PM half-day.

Half-day type must be recorded explicitly.

## 4.3 Advance Notice
Employees should normally submit annual-leave requests at least **3 calendar days before** the requested leave starts.

Emergency or exceptional late requests may be submitted with a reason and are subject to manager review.

## 4.4 Approval
Annual leave requires direct-manager approval.

The AI agent may check eligibility, calculate requested days through tools, check available leave, create the request, and notify the manager.

The AI agent may **not approve the request on behalf of the manager**.

## 4.5 Insufficient Balance
If available paid annual leave is insufficient:
- do not create an approved paid-leave outcome;
- inform the employee of the shortfall;
- offer safe next steps such as reducing dates, changing dates, or requesting HR review.

The agent must not invent unpaid-leave approval.

## 4.6 Rest Days and Public Holidays
Rest days and paid public holidays that should not count as annual leave must not be incorrectly deducted.

The leave-day calculator, not the LLM, determines deductible leave days.

## 4.7 Sickness During Annual Leave
Where an employee becomes entitled to valid sick leave during annual leave, the affected dates should be handled under the applicable legal rule rather than remaining incorrectly deducted as annual leave.

## 4.8 Carry Forward
WorkRight allows up to **5 unused company annual-leave days** to be carried forward to the following year.

The normal company expiry date is **31 March of the following year**.

This company rule must not cause an employee to lose a statutory minimum entitlement earlier than permitted by law. If there is a conflict, statutory protection prevails and HR may review the case.

# 5. Sick Leave Policy

## 5.1 Entitlement
WorkRight follows the applicable statutory ordinary sick-leave entitlement used in V1:

| Continuous service | Ordinary paid sick leave |
|---|---:|
| Less than 2 years | 14 days |
| 2 years to less than 5 years | 18 days |
| 5 years or more | 22 days |

Ordinary sick leave is tracked separately from hospitalisation leave.

## 5.2 Medical Certification
Paid sick leave requires appropriate medical certification under the applicable legal/company process.

The system records:
- whether certification was provided;
- certificate/reference identifier;
- relevant sick-leave dates.

The AI agent must not determine document authenticity solely from model judgement. Authenticity disputes go to HR.

## 5.3 Notification
Employees must inform or attempt to inform WorkRight of sick leave within the applicable **48-hour statutory period from commencement**.

The backend calculates whether the notification timestamp falls within the required period.

Late, missing, or disputed notification cases are referred to HR rather than finally determined by the agent.

# 6. Hospitalisation Leave Policy

## 6.1 Separate Entitlement
Hospitalisation leave is tracked separately from ordinary sick leave.

The V1 legal corpus recognizes up to **60 paid days per calendar year** where hospitalisation is medically necessary.

## 6.2 Medical Necessity
Actual physical admission is not the sole criterion.

Where appropriate medical certification states that the employee is ill enough to require hospitalisation, the case must be assessed under the applicable hospitalisation-leave rule.

The AI agent must not reject such a case only because no physical hospital admission occurred.

## 6.3 HR Review
Hospitalisation-leave requests require HR verification of relevant supporting documents before finalization.

# 7. Flexible Working Arrangement (FWA) Policy

## 7.1 Meaning
An FWA may involve one or more changes to:
- hours of work;
- days of work;
- place of work.

## 7.2 Eligibility to Apply
All active full-time employees within the supported V1 jurisdiction may submit an FWA application.

Eligibility to apply does **not** mean the requested arrangement is automatically approved.

## 7.3 Required Information
A written FWA request should include:
- requested arrangement;
- changed dimension(s): hours, days, and/or place;
- proposed start date;
- proposed end date if temporary;
- employee reason.

The agent asks for missing required information before submission.

## 7.4 Approval Workflow
1. Employee submits the written request.
2. Direct manager reviews operational feasibility.
3. HR reviews policy/compliance.
4. WorkRight issues the written approval or refusal.

The AI agent may create, route, track, and explain the request, but may not make the authorized human decision.

## 7.5 Response Target
WorkRight aims to complete FWA decisions within **30 days** of receipt where practicable.

This is an internal service target.

It does not replace the statutory V1 requirement to approve or refuse the application within **60 days from receipt**.

The backend should track:
- company target date;
- statutory decision due date.

## 7.6 Written Decision
The final decision must be communicated in writing.

If refused, the written decision must include the reason for refusal.

A rejected FWA case cannot be marked complete without a recorded rejection reason.

## 7.7 Temporary Arrangements
An FWA may be approved for a defined period. Where an end date exists, the arrangement ends on that date unless extended or replaced by another approved decision.

# 8. Approval and Escalation Policy

## 8.1 Annual Leave
Normal path:
**Employee → Direct Manager → Final decision**

HR review is required for ambiguous, unsupported, disputed, or exceptional cases.

## 8.2 Sick Leave
Normal path:
**Employee notification + medical certification → deterministic checks → record**

HR reviews missing/disputed documents, late notification, unusual circumstances, and contradictory requests.

## 8.3 Hospitalisation Leave
Normal path:
**Employee → medical evidence → HR verification → record**

## 8.4 FWA
Normal path:
**Employee → Direct Manager → HR → written final decision**

## 8.5 Mandatory Escalation
The agent must request HR review when:
- jurisdiction is Sabah or Sarawak;
- employment type is outside automated V1 scope;
- legal and company policy cannot be safely reconciled;
- required facts remain missing;
- medical-document authenticity needs human assessment;
- a user asks the agent to bypass approval/compliance;
- the system detects an abnormal or contradictory state.

# 9. AI-Agent Authorization Rules
The agent may:
- interpret requests;
- retrieve law/company policy;
- query authorized employee records;
- invoke deterministic calculations;
- create requests;
- route approvals;
- track state;
- notify employees;
- escalate.

The agent may not:
- grant itself manager/HR authority;
- approve requests itself;
- fabricate employee data or leave balances;
- invent medical certification;
- alter statutory rules;
- bypass required approvals;
- silently resolve unsupported jurisdictions;
- expose another employee's private HR data.

Privileged actions must be enforced by backend authorization, not only by LLM instructions.

# 10. Policy-Resolution Order
1. Check jurisdiction and V1 scope.
2. Retrieve applicable statutory law/guidance when legal entitlement matters.
3. Retrieve WorkRight company policy.
4. Compare statutory minimum and company benefit where needed.
5. Retrieve authoritative employee/request facts from the database.
6. Use deterministic backend functions for dates, balances, service length, deadlines, and hard validation.
7. Request the correct human approval.
8. Escalate instead of guessing when the case cannot be safely resolved.

# 11. Company RAG Chunk Plan
- `COMPANY-001 annual_leave_policy` → section 4
- `COMPANY-002 sick_and_hospitalisation_policy` → sections 5–6
- `COMPANY-003 fwa_policy` → section 7
- `COMPANY-004 approval_and_escalation_policy` → sections 8–10

Recommended metadata:
- `source_type = company_policy`
- `company = WorkRight Labs Sdn. Bhd.`
- `policy_version = 1.0`
- `effective_from = 2026-01-01`
- topic
- section
- source file
