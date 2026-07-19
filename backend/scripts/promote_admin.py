"""One-time CLI to grant a user the ADMIN role.

There is no UI for this (a non-admin can't grant themselves admin), so the
very first admin has to be promoted directly against the DB.

Run from backend/:
    PYTHONPATH="..;src" ../.venv/Scripts/python.exe scripts/promote_admin.py user@example.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from thesisguard_backend import models as orm
from thesisguard_backend.db import session_factory


async def main(email: str) -> None:
    async with session_factory() as db:
        user = await db.scalar(select(orm.User).where(orm.User.email == email))
        if user is None:
            print(f"No user found with email={email!r}")
            raise SystemExit(1)
        if user.role == orm.UserRole.ADMIN:
            print(f"{email} is already an admin.")
            return
        user.role = orm.UserRole.ADMIN
        await db.commit()
        print(f"Promoted {email} to admin.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/promote_admin.py <email>")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
