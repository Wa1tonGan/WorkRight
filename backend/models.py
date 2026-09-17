"""SQLAlchemy models for the WorkRight database."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def enum_values(enum_cls):
    """Store enum VALUES ('employee'), not member NAMES ('EMPLOYEE').

    Without this, SQLAlchemy defaults to the uppercased attribute names and
    our snake_case design would silently become SCREAMING_CASE in the DB.
    """
    return [member.value for member in enum_cls]


class Role(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR = "hr"
    ADMIN = "admin"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"


class Jurisdiction(str, Enum):
    PENINSULAR_MALAYSIA = "peninsular_malaysia"
    LABUAN = "labuan"
    SABAH = "sabah"
    SARAWAK = "sarawak"


class EmploymentStatus(str, Enum):
    ACTIVE = "active"
    RESIGNED = "resigned"
    TERMINATED = "terminated"
    INACTIVE = "inactive"


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    employee_no: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)

    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="employee_role", native_enum=False, values_callable=enum_values),
        default=Role.EMPLOYEE,
        server_default="'employee'",   # ORM default alone is invisible to raw SQL
    )
    department: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))

    join_date: Mapped[date] = mapped_column(Date)
    employment_type: Mapped[EmploymentType] = mapped_column(
        SAEnum(EmploymentType, name="employment_type", native_enum=False, values_callable=enum_values)
    )
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        SAEnum(Jurisdiction, name="jurisdiction", native_enum=False, values_callable=enum_values)
    )

    employment_status: Mapped[EmploymentStatus] = mapped_column(
        SAEnum(EmploymentStatus, name="employment_status", native_enum=False, values_callable=enum_values),
        default=EmploymentStatus.ACTIVE,
        server_default="'active'",
    )
    employment_end_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    manager: Mapped["Employee | None"] = relationship(
        "Employee", remote_side=[id], back_populates="direct_reports"
    )
    direct_reports: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="manager"
    )

    __table_args__ = (
        CheckConstraint(
            "(employment_status IN ('resigned', 'terminated'))"
            " = (employment_end_date IS NOT NULL)",
            name="ck_employment_status_end_date",
        ),
    )


class PolicyDocument(Base):
    """Master of record for one source document.

    Chunks COPY these fields down (retrieval stays single-table); the loader
    is the only writer of the copies, so a drift audit can prove they match.
    """

    __tablename__ = "policy_documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)  # law | official_guidance | company_policy
    version: Mapped[str] = mapped_column(Text)
    authority: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)  # NULL = still in force
    source_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PolicyChunk(Base):
    """The atom of RAG: every field an answer needs travels with the chunk.

    Columns follow the user-approved 12-field metadata design (2026-09-14).
    text is the truth; embedding is a rebuildable index of it.
    'Active' == effective_to IS NULL — no separate is_active flag.
    """

    __tablename__ = "policy_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # ── the 12 approved metadata fields ──────────────────────────────
    chunk_id: Mapped[str] = mapped_column(Text, unique=True)          # 'LAW-003'
    document_id: Mapped[str] = mapped_column(ForeignKey("policy_documents.id"))
    source_type: Mapped[str | None] = mapped_column(Text)             # copied from doc
    topic: Mapped[str | None] = mapped_column(Text)                   # 'annual_leave'
    subtopic: Mapped[str | None] = mapped_column(Text)                # 'entitlement'
    section: Mapped[str | None] = mapped_column(Text)                 # '60E' / '4.2'
    jurisdiction: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    effective_from: Mapped[date | None] = mapped_column(Date)         # copied from doc
    effective_to: Mapped[date | None] = mapped_column(Date)           # copied from doc
    version: Mapped[str | None] = mapped_column(Text)                 # copied from doc
    authority: Mapped[str | None] = mapped_column(Text)               # chunk-specific
    source_url: Mapped[str | None] = mapped_column(Text)              # copied from doc

    # ── payload ──────────────────────────────────────────────────────
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LeaveRequest(Base):
    """The ledger of leave — rows here make balances real and put a request
    in the human-approval waiting room.

    Status is BACKEND-driven: the agent may INSERT (as pending_manager);
    only a human decision path may flip status afterwards. There is no
    way to be "born approved".
    """

    __tablename__ = "leave_requests"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    request_no: Mapped[str] = mapped_column(Text, unique=True)      # LV-2026-0001
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))

    # separate legal categories — mixing them would let a sick day eat
    # annual balance (s.60F tracks ordinary sick vs hospitalisation apart)
    leave_type: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    requested_days: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    # half-day support (HB §4.2): AM/PM, only on a single-day request
    day_portion: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)

    # sick/hospitalisation legal dependencies (LAW-006): certification +
    # 48h notification — recorded as data so the backend can check timing
    medical_certificate_provided: Mapped[bool | None] = mapped_column(Boolean)
    medical_certificate_reference: Mapped[str | None] = mapped_column(Text)
    employee_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    status: Mapped[str] = mapped_column(
        Text, server_default="'pending_manager'"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "leave_type IN ('annual', 'sick', 'hospitalisation')",
            name="ck_leave_request_type",
        ),
        CheckConstraint("end_date >= start_date", name="ck_leave_dates_ordered"),
        CheckConstraint("requested_days > 0", name="ck_leave_days_positive"),
        CheckConstraint(
            "day_portion IS NULL OR (day_portion IN ('am', 'pm') "
            "AND start_date = end_date)",
            name="ck_half_day_single_date",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_manager', 'pending_hr', 'approved', "
            "'rejected', 'cancelled', 'escalated')",
            name="ck_leave_request_status",
        ),
        # DUPLICATE PREVENTION at the database level (roadmap): the same
        # employee can't hold two live requests for the same dates+type —
        # but a rejected/cancelled attempt never blocks a corrected retry.
        Index(
            "uq_leave_no_active_duplicates",
            "employee_id",
            "leave_type",
            "start_date",
            "end_date",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('rejected', 'cancelled')"
            ),
        ),
        Index(
            "ix_leave_requests_employee_status",
            "employee_id",
            "status",
        ),
    )


class Approval(Base):
    """Audit trail of HUMAN decisions on leave requests.

    One decision row per request per level. The agent writes here ONLY on
    behalf of a caller whose authority the backend has verified
    (permissions.can_decide_leave) — the model itself never decides.
    """

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    leave_request_id: Mapped[str] = mapped_column(
        ForeignKey("leave_requests.id", ondelete="CASCADE")
    )
    approval_level: Mapped[str] = mapped_column(Text)      # manager | hr
    approver_employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"))
    decision: Mapped[str] = mapped_column(Text)            # approved | rejected
    reason: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "approval_level IN ('manager', 'hr')",
            name="ck_approval_level",
        ),
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_approval_decision",
        ),
        UniqueConstraint(
            "leave_request_id", "approval_level",
            name="uq_approval_per_request_level",
        ),
    )
