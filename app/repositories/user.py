from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def by_email(self, email: str) -> User | None:
        return self.db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    def by_username(self, username: str) -> User | None:
        return self.db.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()

    def by_login_identifier(self, identifier: str) -> User | None:
        """``identifier`` may be an email or a username — whichever matches."""
        return self.db.execute(
            select(User).where((User.email == identifier) | (User.username == identifier))
        ).scalar_one_or_none()
