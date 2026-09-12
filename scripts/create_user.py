"""Create (or update) a user from the command line.

    python scripts/create_user.py EMAIL PASSWORD [--name "Full Name"] [--superuser]
    python scripts/create_user.py EMAIL PASSWORD --username demo

If the email already exists, its password (and flags) are updated. Use this to
bootstrap the first account, or when self-registration is turned off.

``--username`` sets a second, simpler login handle that isn't validated as an
email — useful when typing a full address is inconvenient (e.g. on mobile).
Login accepts either the email or the username.
"""

from __future__ import annotations

import argparse
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from app.core.database import session_scope
from app.core.security import hash_password
from app.models.user import User


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create or update a user")
    ap.add_argument("email")
    ap.add_argument("password")
    ap.add_argument("--name", default=None, help="full name")
    ap.add_argument("--username", default=None, help="a simpler alternative login (not an email)")
    ap.add_argument("--superuser", action="store_true", help="mark as superuser")
    ap.add_argument("--inactive", action="store_true", help="create disabled")
    args = ap.parse_args(argv)

    if len(args.password) < 8:
        ap.error("password must be at least 8 characters")
    try:
        # check_deliverability=False: syntax only, no DNS lookup — but this
        # still catches RFC 6761 special-use domains (.local/.test/.invalid/
        # .localhost), which would otherwise insert fine here and then 500 on
        # any endpoint returning UserOut (email: EmailStr) for this user.
        validate_email(args.email, check_deliverability=False)
    except EmailNotValidError as exc:
        ap.error(f"invalid email {args.email!r}: {exc}")

    with session_scope() as db:
        if args.username:
            existing_username = db.execute(
                select(User).where(User.username == args.username, User.email != args.email)
            ).scalar_one_or_none()
            if existing_username is not None:
                ap.error(
                    f"username {args.username!r} is already taken by {existing_username.email}"
                )

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
        if args.username is not None:
            user.username = args.username
        user.is_superuser = args.superuser
        user.is_active = not args.inactive
        db.flush()
        uid = user.id

    login_desc = f"{args.email} (or {args.username})" if args.username else args.email
    print(f"{action} user #{uid}: {login_desc} "
          f"(superuser={args.superuser}, active={not args.inactive})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
