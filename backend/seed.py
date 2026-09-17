"""Synthetic employee data for WorkRight.

Each row exists to exercise a specific branch the leave/balance tools will
face in Phase 1:

    WR-0001  full_time, 10 months service   -> below the s.60E 2-year floor
    WR-0002  full_time, 7 years             -> 12-day annual tier (5-10 yrs)
    WR-0003  manager, 12 years              -> 16-day tier (>=10 yrs) + FK target
    WR-0004  part_time                      -> pro-rata regulations path
    WR-0005  contract                       -> statutory entitlements during term
    WR-0006  sabah                          -> must escalate, NOT Employment Act 1955

Run:  uv run python -m backend.seed
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import engine
from .models import Employee, EmploymentType, Jurisdiction, Role


def seed() -> None:
    with Session(engine) as session:
        if session.scalar(select(Employee).limit(1)) is not None:
            print("employees already contains data — skipping seed")
            return

        manager = Employee(
            employee_no="WR-0003",
            full_name="Siti Nurhaliza binti Yusof",
            email="siti.yusof@example.my",
            role=Role.MANAGER,
            department="Engineering",
            join_date=date(2014, 2, 17),          # ~12.6 years: 16-day tier
            employment_type=EmploymentType.FULL_TIME,
            jurisdiction=Jurisdiction.PENINSULAR_MALAYSIA,
        )
        session.add(manager)
        session.flush()  # assigns manager.id so others can reference it

        session.add_all(
            [
                Employee(
                    employee_no="WR-0001",
                    full_name="Ahmad Danial bin Rahim",
                    email="danial.rahim@example.my",
                    department="Engineering",
                    manager_id=manager.id,
                    join_date=date(2025, 11, 3),  # <2 years: no statutory tier yet
                    employment_type=EmploymentType.FULL_TIME,
                    jurisdiction=Jurisdiction.PENINSULAR_MALAYSIA,
                ),
                Employee(
                    employee_no="WR-0002",
                    full_name="Lim Wei Jie",
                    email="weijie.lim@example.my",
                    department="Finance",
                    manager_id=manager.id,
                    join_date=date(2019, 6, 10),  # 7.3 years: 12-day tier
                    employment_type=EmploymentType.FULL_TIME,
                    jurisdiction=Jurisdiction.PENINSULAR_MALAYSIA,
                ),
                Employee(
                    employee_no="WR-0004",
                    full_name="Priya a/p Raman",
                    email="priya.raman@example.my",
                    department="Support",
                    manager_id=manager.id,
                    join_date=date(2022, 1, 10),
                    employment_type=EmploymentType.PART_TIME,
                    jurisdiction=Jurisdiction.LABUAN,
                ),
                Employee(
                    employee_no="WR-0005",
                    full_name="Muhammad Hakimi bin Zainol",
                    email="hakimi.z@example.my",
                    department="Operations",
                    manager_id=manager.id,
                    join_date=date(2024, 8, 1),
                    employment_type=EmploymentType.CONTRACT,
                    jurisdiction=Jurisdiction.PENINSULAR_MALAYSIA,
                ),
                Employee(
                    employee_no="WR-0006",
                    full_name="Jelin anak Ujin",
                    email="jelin.ujin@example.my",
                    department="Engineering",
                    manager_id=manager.id,
                    join_date=date(2021, 3, 15),
                    employment_type=EmploymentType.FULL_TIME,
                    jurisdiction=Jurisdiction.SABAH,  # out of V1 scope -> escalate
                ),
                Employee(
                    employee_no="WR-0007",
                    full_name="Ravi Kumar a/l Suresh",
                    email="ravi.kumar@example.my",
                    role=Role.HR,                       # sees everything (§9)
                    department="People",
                    join_date=date(2018, 5, 2),
                    employment_type=EmploymentType.FULL_TIME,
                    jurisdiction=Jurisdiction.PENINSULAR_MALAYSIA,
                ),
            ]
        )
        session.commit()

        print(f"{'no':9} {'name':30} {'role':9} {'type':10} {'jurisdiction':20} {'status':9} joined")
        for e in session.scalars(select(Employee).order_by(Employee.employee_no)):
            print(
                f"{e.employee_no:9} {e.full_name:30} {e.role.value:9} "
                f"{e.employment_type.value:10} {e.jurisdiction.value:20} "
                f"{e.employment_status.value:9} {e.join_date}"
            )


if __name__ == "__main__":
    seed()


def set_demo_passwords(password: str | None = None) -> None:
    """Give every employee the demo password (idempotent).

    Fictional people, local demo — one shared password keeps the login page
    usable. A real deployment would force per-user secrets on first login.
    """
    from .auth import DEMO_PASSWORD, hash_password

    pw_hash = hash_password(password or DEMO_PASSWORD)
    with Session(engine) as session:
        changed = 0
        for emp in session.scalars(select(Employee)):
            if emp.password_hash != pw_hash:
                emp.password_hash = pw_hash
                changed += 1
        session.commit()
        print(f"demo password set for {changed} employees "
              f"(password: {password or DEMO_PASSWORD})")
