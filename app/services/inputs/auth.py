"""Auth strategies for HTTP-based connectors (web crawler, http_api).

Credentials are **never** stored in code or in the connector config. The config
names an environment variable; the value is read at run time:

    {"type": "none"}
    {"type": "bearer", "token_env": "GRDWORLD_TOKEN"}
    {"type": "header", "headers": {"X-API-Key": {"env": "GRD_API_KEY"}}}
    {"type": "cookie", "cookie_env": "GRDWORLD_COOKIE"}   # raw Cookie header value
    {"type": "form_login",
     "login_url": "https://console.grdworld.com/Account/Login",
     "user_field": "Email", "password_field": "Password",
     "user_env": "GRDWORLD_USER", "password_env": "GRDWORLD_PASS",
     "extra_fields": {"RememberMe": "true"},
     "success_status": 200}
"""

from __future__ import annotations

import abc
import os
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"auth: environment variable {name!r} is not set")
    return val


class AuthStrategy(abc.ABC):
    @abc.abstractmethod
    def prepare(self, client: httpx.Client) -> None:
        """Mutate the client (headers / cookies) so subsequent requests are authed."""


class NoAuth(AuthStrategy):
    def prepare(self, client: httpx.Client) -> None:  # noqa: D401
        return


class BearerAuth(AuthStrategy):
    def __init__(self, token_env: str) -> None:
        self.token_env = token_env

    def prepare(self, client: httpx.Client) -> None:
        client.headers["Authorization"] = f"Bearer {_env(self.token_env)}"


class HeaderAuth(AuthStrategy):
    def __init__(self, headers: dict[str, Any]) -> None:
        self.headers = headers

    def prepare(self, client: httpx.Client) -> None:
        for key, val in self.headers.items():
            client.headers[key] = _env(val["env"]) if isinstance(val, dict) else str(val)


class CookieAuth(AuthStrategy):
    def __init__(self, cookie_env: str) -> None:
        self.cookie_env = cookie_env

    def prepare(self, client: httpx.Client) -> None:
        client.headers["Cookie"] = _env(self.cookie_env)


class FormLoginAuth(AuthStrategy):
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.login_url = cfg["login_url"]
        self.user_field = cfg.get("user_field", "username")
        self.password_field = cfg.get("password_field", "password")
        self.user_env = cfg["user_env"]
        self.password_env = cfg["password_env"]
        self.extra_fields = cfg.get("extra_fields", {})
        self.success_status = int(cfg.get("success_status", 200))

    def prepare(self, client: httpx.Client) -> None:
        data = {
            self.user_field: _env(self.user_env),
            self.password_field: _env(self.password_env),
            **self.extra_fields,
        }
        resp = client.post(self.login_url, data=data, follow_redirects=True)
        if resp.status_code >= 400 or (
            self.success_status and resp.status_code not in (self.success_status, 302)
        ):
            raise RuntimeError(
                f"form_login to {self.login_url} failed: HTTP {resp.status_code}"
            )
        # session cookies are now on the client's cookie jar
        log.info("form_login ok (%s), %d cookie(s)", self.login_url, len(client.cookies))


_BUILDERS = {
    "none": lambda c: NoAuth(),
    "bearer": lambda c: BearerAuth(c["token_env"]),
    "header": lambda c: HeaderAuth(c["headers"]),
    "cookie": lambda c: CookieAuth(c["cookie_env"]),
    "form_login": lambda c: FormLoginAuth(c),
}


def build_auth(config: dict[str, Any] | None) -> AuthStrategy:
    if not config:
        return NoAuth()
    kind = config.get("type", "none")
    try:
        return _BUILDERS[kind](config)
    except KeyError as exc:
        raise ValueError(
            f"unknown auth type {kind!r}; choose from {sorted(_BUILDERS)}"
        ) from exc
