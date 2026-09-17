"""Database connection details shared by the app and by Alembic.

Kept in its own module so the migration tool can reuse the exact same
engine configuration as the running app — one source of truth for the URL.
"""

import getpass
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

# Homebrew Postgres uses trust auth on localhost: no password, and the
# default user is the macOS short username. DATABASE_URL overrides anywhere else.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{getpass.getuser()}@localhost:5432/workright",
)

engine = create_engine(DATABASE_URL)


class Base(DeclarativeBase):
    """Registry of all ORM models; Alembic autogenerate reads its metadata."""
