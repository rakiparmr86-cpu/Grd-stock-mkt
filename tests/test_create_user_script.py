"""scripts/create_user.py rejects RFC 6761 special-use email domains before
they ever reach the DB (see tests/test_auth_api.py for why that matters)."""

from __future__ import annotations

import pytest

from scripts.create_user import main


@pytest.mark.parametrize(
    "email",
    ["a@b.local", "a@b.test", "a@b.invalid", "a@localhost"],
)
def test_rejects_special_use_domains(email):
    with pytest.raises(SystemExit):
        main([email, "somepassword123"])


def test_rejects_short_password():
    with pytest.raises(SystemExit):
        main(["a@b.dev", "short"])
