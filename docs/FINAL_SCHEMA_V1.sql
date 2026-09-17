-- WorkRight V1 — FINAL PostgreSQL schema (supersedes earlier FINAL_SCHEMA_V1.sql)
-- Basis: user spec of 2026-09-14, merged with prior review conclusions.
-- STATUS: design deliverable; NOT applied to the live database yet.
-- Implementation remains phase-paced: `employees` (section 1) is the first
-- Alembic migration; later tables land with their phases (3, 4, 2).
--
-- Legal-verification notice (project rule: only verified sources):
--   The spec cites "sections 60P/60Q" and a "60-day" employer response window
--   for Flexible Working Arrangements. Online verification was blocked at
--   design time; best knowledge says FWA = Employment Act 1955 s.60FIII with
--   a 30-day written response. The schema therefore stores NO constant:
--   decision_due_at is computed by backend code from a policy row in
--   policy_documents (decision_basis_policy_id gives per-request provenance).
--   When knowledge/law/ verification completes, correcting the number is one
--   code constant — no migration.

CREATE EXTENSION IF NOT EXISTS vector;      -- used by Phase 2 chunk table, not here

-- ---------- 11. updated_at: real trigger, not a lying DEFAULT ----------
CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. EMPLOYEES
-- ============================================================
CREATE TABLE employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_no VARCHAR(30) UNIQUE NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,

    role VARCHAR(20) NOT NULL DEFAULT 'employee'
        CHECK (role IN ('employee', 'manager', 'hr', 'admin')),
    department VARCHAR(100) NOT NULL,
    manager_id UUID NULL REFERENCES employees(id),

    join_date DATE NOT NULL,                 -- service length: s.60E/60F tiers,
                                             -- s.60FIII 3-month FWA gate
    employment_type VARCHAR(30) NOT NULL
        CHECK (employment_type IN ('full_time', 'part_time', 'contract')),
    jurisdiction VARCHAR(50) NOT NULL
        CHECK (jurisdiction IN ('peninsular_malaysia', 'labuan', 'sabah', 'sarawak')),
        -- V1 scope: peninsular_malaysia, labuan.
        -- sabah/sarawak => agent must ESCALATE (different legal instruments).

    employment_status VARCHAR(30) NOT NULL DEFAULT 'active'
        CHECK (employment_status IN ('active', 'resigned', 'terminated', 'inactive')),
    employment_end_date DATE NULL,
    CHECK ((employment_status IN ('resigned', 'terminated'))
           = (employment_end_date IS NOT NULL)),
        -- resigned/terminated require an end date; active/inactive forbid one.

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER employees_touch BEFORE UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_employees_manager ON employees(manager_id);
CREATE INDEX idx_employees_status ON employees(employment_status);

-- ============================================================
-- 2. LEAVE GRANTS — explicit credits; the ledger side of a balance
--    NO leave_balances table: balances are DERIVED (see view below).
-- ============================================================
CREATE TABLE leave_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees(id),
    leave_year INT NOT NULL,                 -- calendar year attribution
    leave_type VARCHAR(40) NOT NULL
        CHECK (leave_type IN ('annual', 'sick', 'hospitalisation')),
    grant_type VARCHAR(30) NOT NULL
        CHECK (grant_type IN ('entitlement', 'carry_forward', 'adjustment', 'goodwill')),
    days NUMERIC(6,2) NOT NULL CHECK (days <> 0),
        -- negative rows allowed: adjustments may claw back days
    reason TEXT,
    granted_by UUID NULL REFERENCES employees(id),   -- the HR actor
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER leave_grants_touch BEFORE UPDATE ON leave_grants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- One natural key row per type/year; 'adjustment' may repeat freely.
CREATE UNIQUE INDEX uq_leave_grants_natural_key
    ON leave_grants(employee_id, leave_year, leave_type, grant_type)
    WHERE grant_type <> 'adjustment';
CREATE INDEX idx_leave_grants_employee_year ON leave_grants(employee_id, leave_year);

-- ============================================================
-- 3. LEAVE REQUESTS — the usage side of the ledger
-- ============================================================
CREATE TABLE leave_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_no VARCHAR(40) UNIQUE NOT NULL,
    employee_id UUID NOT NULL REFERENCES employees(id),

    leave_type VARCHAR(40) NOT NULL
        CHECK (leave_type IN ('annual', 'sick', 'hospitalisation')),

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    CHECK (end_date >= start_date),
    requested_days NUMERIC(6,2) NOT NULL CHECK (requested_days > 0),

    -- Half-day support: portion only makes sense for a single-day request
    day_portion VARCHAR(8) NULL
        CHECK (day_portion IN ('am', 'pm')),
    CHECK (day_portion IS NULL OR start_date = end_date),

    reason TEXT,

    -- Employment Act sick-leave conditions: certification + notification
    medical_certificate_provided BOOLEAN,
    medical_certificate_reference VARCHAR(255),
    employee_notified_at TIMESTAMPTZ,

    status VARCHAR(40) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending_manager', 'pending_hr',
                          'approved', 'rejected', 'cancelled', 'withdrawn',
                          'escalated')),
        -- 'escalated' = refer-to-HR outcome (out-of-scope jurisdiction etc.)

    submitted_at TIMESTAMPTZ,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER leave_requests_touch BEFORE UPDATE ON leave_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_leave_requests_employee_status
    ON leave_requests(employee_id, status);

-- 5. DUPLICATE PREVENTION — database-enforced, retry-friendly:
CREATE UNIQUE INDEX uq_leave_requests_active_duplicates
    ON leave_requests(employee_id, leave_type, start_date, end_date)
    WHERE status NOT IN ('rejected', 'cancelled', 'withdrawn');

-- ============================================================
-- 4. FLEXIBLE WORK ARRANGEMENT REQUESTS
--    Legal basis: pending verification (see header note; s.60FIII per best
--    knowledge, NOT the spec's "60P/60Q").
-- ============================================================
CREATE TABLE flexible_work_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_no VARCHAR(40) UNIQUE NOT NULL,
    employee_id UUID NOT NULL REFERENCES employees(id),

    -- One request may change multiple dimensions (spec: no single enum)
    change_hours BOOLEAN NOT NULL DEFAULT FALSE,
    change_days BOOLEAN NOT NULL DEFAULT FALSE,
    change_place BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (change_hours OR change_days OR change_place),

    requested_arrangement TEXT NOT NULL,
    employee_reason TEXT,
    proposed_start_date DATE,
    proposed_end_date DATE,
    CHECK (proposed_end_date IS NULL OR proposed_start_date IS NULL
           OR proposed_end_date >= proposed_start_date),

    submitted_at TIMESTAMPTZ,

    -- Historical snapshot of the response deadline.
    -- NEVER set by the LLM; backend code computes submitted_at + N days where
    -- N comes from the governing policy row. Do not confuse with a live rule.
    decision_due_at TIMESTAMPTZ NULL,
    decision_basis_policy_id UUID NULL,   -- FK added below (policy_documents defined later)

    status VARCHAR(40) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending_manager', 'pending_hr',
                          'approved', 'rejected', 'withdrawn', 'escalated')),
    decision_reason TEXT,          -- written employer response
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (decision_due_at IS NULL OR submitted_at IS NULL
           OR decision_due_at >= submitted_at)   -- sanity, not the rule itself
);
CREATE TRIGGER fwa_requests_touch BEFORE UPDATE ON flexible_work_requests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_fwa_employee_status
    ON flexible_work_requests(employee_id, status);
CREATE INDEX idx_fwa_due_open
    ON flexible_work_requests(decision_due_at)
    WHERE status IN ('draft', 'pending_manager', 'pending_hr');

-- ============================================================
-- 7. APPROVALS — audit history for both request kinds
-- ============================================================
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leave_request_id UUID NULL REFERENCES leave_requests(id) ON DELETE CASCADE,
    fwa_request_id UUID NULL REFERENCES flexible_work_requests(id) ON DELETE CASCADE,
    CHECK ((leave_request_id IS NULL) <> (fwa_request_id IS NULL)),  -- exactly one

    approval_level VARCHAR(30) NOT NULL CHECK (approval_level IN ('manager', 'hr')),
    approver_employee_id UUID NOT NULL REFERENCES employees(id),
    decision VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (decision IN ('pending', 'approved', 'rejected')),
    reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (approval_level, leave_request_id),
    UNIQUE (approval_level, fwa_request_id)
);
CREATE TRIGGER approvals_touch BEFORE UPDATE ON approvals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_approvals_leave ON approvals(leave_request_id);
CREATE INDEX idx_approvals_fwa ON approvals(fwa_request_id);

-- ============================================================
-- 8. AGENT CASES — AI workflow progress, NOT HR business truth
-- ============================================================
CREATE TABLE agent_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_no VARCHAR(40) UNIQUE NOT NULL,
    employee_id UUID NOT NULL REFERENCES employees(id),
    case_type VARCHAR(40) NOT NULL
        CHECK (case_type IN ('annual_leave', 'sick_leave',
                             'hospitalisation_leave', 'flexible_work')),

    related_leave_request_id UUID NULL REFERENCES leave_requests(id),
    related_fwa_request_id UUID NULL REFERENCES flexible_work_requests(id),
    -- a case may exist BEFORE its request does; links fill in later

    status VARCHAR(40) NOT NULL
        CHECK (status IN ('running', 'waiting_for_employee', 'waiting_for_manager',
                          'waiting_for_hr', 'completed', 'rejected',
                          'escalated', 'failed')),
    state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- agent scratch only: {"policy_checked":true,"next_step":"wait_for_hr"}
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE TRIGGER agent_cases_touch BEFORE UPDATE ON agent_cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE INDEX idx_agent_cases_employee_status ON agent_cases(employee_id, status);
CREATE INDEX idx_agent_cases_open ON agent_cases(status)
    WHERE status IN ('running', 'waiting_for_employee', 'waiting_for_manager',
                     'waiting_for_hr');

-- ============================================================
-- 9. AGENT CASE EVENTS — auditable trace, never chain-of-thought
-- ============================================================
CREATE TABLE agent_case_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES agent_cases(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,     -- tool_called, tool_result,
                                         -- state_changed, approval_requested,
                                         -- approval_received, escalated, completed
    tool_name VARCHAR(100),
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_case_events_case
    ON agent_case_events(case_id, created_at);

-- ============================================================
-- 10. POLICY DOCUMENTS — RAG metadata + the legal-constant source
-- ============================================================
CREATE TABLE policy_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    source_type VARCHAR(40) NOT NULL
        CHECK (source_type IN ('law', 'jtksm_guidance', 'company_policy')),
    authority VARCHAR(150),              -- e.g. 'Employment Act 1955, s.60E'
    topic VARCHAR(80) NOT NULL,          -- annual_leave | sick_leave | fwa | ...
    version VARCHAR(50),
    effective_from DATE,
    effective_to DATE,
    source_url TEXT,
    local_path TEXT,                     -- file under knowledge/law|company
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_policy_documents_topic
    ON policy_documents(topic, source_type, is_active);

-- ============================================================
-- Derived-balance convenience view (the §3 formula, materialized nowhere)
-- Agent tools may query this; it is 100% rebuildable, stores nothing mutable.
-- ============================================================
CREATE OR REPLACE VIEW leave_balances AS
WITH keys AS (
    SELECT employee_id, leave_year, leave_type FROM leave_grants
  UNION
    SELECT employee_id, EXTRACT(YEAR FROM start_date)::int, leave_type
    FROM leave_requests
),
gr AS (SELECT employee_id, leave_year, leave_type, SUM(days) AS granted_days
       FROM leave_grants GROUP BY 1, 2, 3),
ap AS (SELECT employee_id, EXTRACT(YEAR FROM start_date)::int AS leave_year,
              leave_type, SUM(requested_days) AS approved_days
       FROM leave_requests WHERE status = 'approved' GROUP BY 1, 2, 3),
pe AS (SELECT employee_id, EXTRACT(YEAR FROM start_date)::int AS leave_year,
              leave_type, SUM(requested_days) AS pending_days
       FROM leave_requests
       WHERE status IN ('draft', 'pending_manager', 'pending_hr') GROUP BY 1, 2, 3)
SELECT k.employee_id, k.leave_year, k.leave_type,
       COALESCE(gr.granted_days, 0) AS granted_days,
       COALESCE(ap.approved_days, 0) AS approved_days,
       COALESCE(pe.pending_days, 0) AS pending_days,
       COALESCE(gr.granted_days, 0) - COALESCE(ap.approved_days, 0) AS remaining_days,
       COALESCE(gr.granted_days, 0) - COALESCE(ap.approved_days, 0)
         - COALESCE(pe.pending_days, 0) AS available_days
FROM keys k
LEFT JOIN gr USING (employee_id, leave_year, leave_type)
LEFT JOIN ap USING (employee_id, leave_year, leave_type)
LEFT JOIN pe USING (employee_id, leave_year, leave_type);

-- Phase 2 preview (NOT part of V1 apply-set):
-- policy_chunks(id, document_id FK -> policy_documents, chunk_text,
--   embedding vector(1024) /* BGE-M3 */, jurisdiction, effective_from,
--   effective_to, token_count, ...)
