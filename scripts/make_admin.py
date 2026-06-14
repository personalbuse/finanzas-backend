#!/usr/bin/env python3
"""Promote a user to admin.

Usage:
    python scripts/make_admin.py <username>

Requires DATABASE_URL in environment or .env file.
Run from the backend/ directory.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.base import User


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


async def main(username: str) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        eprint("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            eprint(f"ERROR: User '{username}' not found")
            sys.exit(1)

        if user.rol == "admin":
            eprint(f"User '{username}' is already admin")
            return

        user.rol = "admin"
        await session.commit()
        eprint(f"User '{username}' promoted to admin successfully")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        eprint("Usage: python scripts/make_admin.py <username>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
