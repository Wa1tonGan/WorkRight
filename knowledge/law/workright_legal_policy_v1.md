# WorkRight Legal Policy Corpus V1
## RAG-ready normalized legal knowledge

> Educational RAG corpus for WorkRight. V1 scope: private-sector full-time employee scenarios in Peninsular Malaysia and the Federal Territory of Labuan. This is a normalized summary for software retrieval and testing, not a substitute for official legislation or legal advice.

## LAW-001 — Jurisdiction and V1 Scope
**Topic:** `scope`  
**Source type:** `law_and_official_guidance`  
**Authority:** JTKSM / Employment Act 1955

- WorkRight V1 uses the Employment Act 1955 as its primary legal source for supported HR topics.
- The automated V1 legal corpus applies only to supported cases in Peninsular Malaysia and the Federal Territory of Labuan.
- Sabah and Sarawak cases must be escalated to HR instead of being decided automatically with this corpus.
- Unsupported employment arrangements must also be escalated rather than guessed.

## LAW-002 — Statutory Minimum vs More-Favourable Company Terms
**Topic:** `policy_precedence`  
**Source type:** `law`  
**Authority:** Employment Act 1955, sections 7 and 7A

- A contract, agreement, or company policy term that is less favourable than a statutory minimum is ineffective to that extent; the more favourable statutory protection applies.
- A more favourable employment term may be agreed unless the Act expressly prohibits it.
- Agent rule: identify the statutory minimum, compare the company benefit, apply the more favourable valid term, and escalate if the comparison is legally ambiguous.

Example:
- statutory annual-leave minimum = 12 days
- WorkRight company entitlement = 18 days
- result = 18 days, subject to valid company procedure

## LAW-003 — Annual Leave Entitlement
**Topic:** `annual_leave_entitlement`  
**Source type:** `law`  
**Authority:** Employment Act 1955, section 60E

| Continuous service | Minimum paid annual leave |
|---|---:|
| Less than 2 years | 8 days |
| 2 years to less than 5 years | 8 days |
| 5 years to less than 10 years | 12 days |
| 10 years and above | 16 days |

> Correction 2026-09-14: earlier draft of this corpus wrongly stated 12/16 days with a
> 5-year boundary; s.60E bands are 8/8/12/16 with the top-tier boundary at 10 years.
> Pending final verification against the official JTKSM text (see Official Sources).

Where employment ends before completion of the relevant 12 months, statutory entitlement is proportionate to completed months of service and subject to the Act's rounding rule.

Deterministic code should calculate service length, the applicable band, pro-rating, requested days, and actual available balance.

## LAW-004 — Annual Leave Conditions
**Topic:** `annual_leave_conditions`  
**Source type:** `law`  
**Authority:** Employment Act 1955, section 60E

- Paid annual leave is additional to rest days and paid public holidays.
- If an employee on annual leave becomes entitled to sick leave or maternity leave for some of those days, the affected days are treated as sick/maternity leave rather than annual leave.
- Statutory annual leave must be granted and taken within the period specified by section 60E.
- Payment in lieu is permitted where the employer requests the employee not to take some/all of the leave and the employee agrees in writing.
- On termination, qualifying accrued annual leave is handled under section 60E, including payment for eligible untaken leave, subject to the section's statutory exception.
- If unpaid leave exceeds 30 days in aggregate within the relevant 12-month period, that period is disregarded when calculating service length for section 60E.
- Unauthorized absence without reasonable excuse for more than 10% of the working days in the relevant 12-month accrual period results in loss of the statutory annual-leave entitlement for that period.

## LAW-005 — Sick Leave and Hospitalisation Entitlement
**Topic:** `sick_leave_entitlement`  
**Source type:** `law_and_official_guidance`  
**Authority:** Employment Act 1955, section 60F; JTKSM guidance

| Length of service | Ordinary paid sick leave | Hospitalisation leave | Potential total |
|---|---:|---:|---:|
| Less than 2 years | 14 days | 60 days | 74 days |
| 2 years to less than 5 years | 18 days | 60 days | 78 days |
| 5 years or more | 22 days | 60 days | 82 days |

- Ordinary sick leave and hospitalisation leave are separate entitlements under the post-1 January 2023 rules explained by JTKSM.
- If the relevant medical practitioner/officer certifies that the employee is ill enough to require hospitalisation, the employee is treated as hospitalised for section 60F even if actual admission does not occur.
- Ordinary sick leave and hospitalisation leave must be tracked separately in the database.

## LAW-006 — Sick Leave Certification and Notification
**Topic:** `sick_leave_certification_and_notification`  
**Source type:** `law`  
**Authority:** Employment Act 1955, section 60F

- Paid sick leave depends on examination/certification under section 60F.
- The section provides for the employer's appointed registered medical practitioner, or another registered practitioner/medical officer where the appointed practitioner is unavailable within a reasonable time or distance given the circumstances.
- Dental certification may also qualify within the same statutory limits.
- The employee must inform or attempt to inform the employer of sick leave within 48 hours from commencement.
- Lack of appropriate certification, or failure to notify/attempt notification within 48 hours, may cause those days to be treated as absence without permission and reasonable excuse.

Deterministic code should calculate the notification interval and remaining entitlements.

## LAW-007 — FWA: What May Be Requested
**Topic:** `fwa_types`  
**Source type:** `law`  
**Authority:** Employment Act 1955, section 60P

An employee may apply for a Flexible Working Arrangement to vary one or more of:
- hours of work;
- days of work;
- place of work.

The application remains subject to Part XII and the contract of service. Where a collective agreement applies, the application must be consistent with it.

The employee has a right to apply, not an automatic right to approval.

## LAW-008 — FWA Application and Decision Process
**Topic:** `fwa_application_and_response`  
**Source type:** `law`  
**Authority:** Employment Act 1955, section 60Q

- The FWA application must be made in writing and in the applicable form and manner.
- The employer must approve or refuse the application within **60 days from receipt**.
- The decision must be communicated in writing.
- If refused, the employer must state the ground for refusal in writing.
- The backend, not the LLM, calculates and stores the statutory decision due date.

# Official Sources
1. Employment Act 1955 (Act 265), updated text as at 1 January 2023 — JTKSM  
   https://jtksm.mohr.gov.my/en/borang/employment-act-1955  
   https://jtksm.mohr.gov.my/sites/default/files/2023-11/Akta%20Kerja%201955%20%28Akta%20265%29.pdf
2. JTKSM Employment Act 1955 (Amendment) 2022 FAQ  
   https://jtksm.mohr.gov.my/ms/soalan-lazim/akta-kerja-1955-pindaan-2022
3. JTKSM Guidelines Library  
   https://jtksm.mohr.gov.my/ms/penerbitan/garis-panduan

# Intended RAG Chunk Boundaries
1. `scope`
2. `policy_precedence`
3. `annual_leave_entitlement`
4. `annual_leave_conditions`
5. `sick_leave_entitlement`
6. `sick_leave_certification_and_notification`
7. `fwa_types`
8. `fwa_application_and_response`

Each chunk should retain source, authority, statutory section, topic, jurisdiction, effective date, and original source URL.
