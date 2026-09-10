"""Create (or update) a user from the command line.

    python scripts/create_user.py EMAIL PASSWORD [--name "Full Name"] [--superuser]

If the email already exists, its password (and flags) are updated. Use this to
bootstrap the first account, or when self-registration is turned off.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.database import session_scope
from app.core.security import hash_password
from app.models.user import User


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create or update a user")
    ap.add_argument("email")
    ap.add_argument("password")
    ap.add_argument("--name", default=None, help="full name")
    ap.add_argument("--superuser", action="store_true", help="mark as superuser")
    ap.add_argument("--inactive", action="store_true", help="create disabled")
    args = ap.parse_args(argv)

    if len(args.password) < 8:
        ap.error("password must be at least 8 characters")

    with session_scope() as db:
        user = db.execute(
            select(User).where(User.email == args.email)
        ).scalar_one_or_none()
        if user is None:
            user = User(email=args.email)
            db.add(user)
            action = "created"
        else:
            action = "updated"
        user.hashed_password = hash_password(args.password)
        if args.name is not None:
            user.full_name = args.name
        user.is_superuser = args.superuser
        user.is_active = not args.inactive
        db.flush()
        uid = user.id

    print(f"{action} user #{uid}: {args.email} "
          f"(superuser={args.superuser}, active={not args.inactive})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
