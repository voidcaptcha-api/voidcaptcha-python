"""Typed errors for the VoidCaptcha API.

Every failure the API reports carries a numeric ``errorId`` and a stable
``errorCode`` string. The hundreds digit of ``errorId`` is the group, and each
group has its own exception class, so you can catch as broadly or as narrowly
as you need::

    try:
        result = client.turnstile(url, site_key)
    except voidcaptcha.SolveError as e:      # 300-range: worth a retry
        ...
    except voidcaptcha.BillingError as e:    # 400-range: balance or limits
        ...
    except voidcaptcha.VoidCaptchaError as e:  # anything else
        ...

The full table is at https://voidcaptcha.com/docs/errors
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Type

__all__ = [
    "VoidCaptchaError",
    "AuthenticationError",
    "InvalidRequestError",
    "TaskNotFoundError",
    "SolveError",
    "BillingError",
    "InsufficientBalanceError",
    "ThreadLimitError",
    "RateLimitError",
    "ServerError",
    "NetworkError",
    "SolveTimeoutError",
]

#: Whether retrying each documented code is worth it: "yes", "backoff" or "no".
#: Mirrors the last column of https://voidcaptcha.com/docs/errors
RETRY: Dict[str, str] = {
    "ERROR_KEY_MISSING": "no",
    "ERROR_KEY_INVALID": "no",
    "ERROR_KEY_SUSPENDED": "no",
    "ERROR_TYPE_NOT_ENABLED": "no",
    "ERROR_BAD_REQUEST": "no",
    "ERROR_TYPE_UNSUPPORTED": "no",
    "ERROR_REQUIRED_FIELD": "no",
    "ERROR_URL_INVALID": "no",
    "ERROR_SITEKEY_INVALID": "no",
    "ERROR_PROXY_FORMAT": "no",
    "ERROR_TASK_NOT_FOUND": "no",
    "ERROR_PROXY_CONNECT": "yes",
    "ERROR_IP_BLOCKED": "yes",
    "ERROR_SITE_UNREACHABLE": "backoff",
    "ERROR_CAPTCHA_UNSOLVABLE": "yes",
    "ERROR_SCORE_NOT_REACHED": "yes",
    "ERROR_TIMEOUT": "backoff",
    "ERROR_BLOB_REQUIRED": "yes",
    "ERROR_BLOB_REJECTED": "yes",
    "ERROR_INSUFFICIENT_BALANCE": "no",
    "ERROR_THREAD_LIMIT": "backoff",
    "ERROR_RATE_LIMITED": "backoff",
    "ERROR_INTERNAL": "backoff",
    "ERROR_TYPE_DEGRADED": "backoff",
}


class VoidCaptchaError(Exception):
    """Base class for every error this package raises.

    Attributes:
        code: The API's ``errorCode`` (e.g. ``"ERROR_IP_BLOCKED"``), or None
            when the failure happened before the API answered.
        error_id: The API's numeric ``errorId``, or None.
        description: The API's ``errorDescription``, safe to log.
        http_status: The HTTP status of the response, or None.
        retry: ``"yes"``, ``"backoff"`` or ``"no"``.
        response: The decoded JSON body, when there was one.
    """

    def __init__(
        self,
        description: str,
        *,
        code: Optional[str] = None,
        error_id: Optional[int] = None,
        http_status: Optional[int] = None,
        retry: str = "no",
        response: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(f"{code}: {description}" if code else description)
        self.code = code
        self.error_id = error_id
        self.description = description
        self.http_status = http_status
        self.retry = retry
        self.response = dict(response) if response is not None else None

    @property
    def retryable(self) -> bool:
        """True when trying again (now, or after a pause) can succeed."""
        return self.retry != "no"


class AuthenticationError(VoidCaptchaError):
    """100-range: the key is missing, wrong, suspended, or not enabled for the type."""


class InvalidRequestError(VoidCaptchaError):
    """200-range: the request itself is wrong. Fix it; do not retry it."""


class TaskNotFoundError(InvalidRequestError):
    """``ERROR_TASK_NOT_FOUND``: unknown task id, or its result aged out (10 minutes)."""


class SolveError(VoidCaptchaError):
    """300-range: the solve failed on the target's side. Nothing was charged."""


class BillingError(VoidCaptchaError):
    """400-range: balance and account limits."""


class InsufficientBalanceError(BillingError):
    """``ERROR_INSUFFICIENT_BALANCE``: top up at voidcaptcha.com."""


class ThreadLimitError(BillingError):
    """``ERROR_THREAD_LIMIT``: too many solves in flight on this account."""


class RateLimitError(BillingError):
    """``ERROR_RATE_LIMITED``: requests are arriving too fast (e.g. polling under 2 s)."""


class ServerError(VoidCaptchaError):
    """500-range, or a response that was not the API's JSON at all."""


class NetworkError(VoidCaptchaError):
    """The request never got an answer: DNS, TLS, connection reset, read timeout."""


class SolveTimeoutError(VoidCaptchaError):
    """The client gave up waiting. The task may still finish and be billed."""


_BY_CODE: Dict[str, Type[VoidCaptchaError]] = {
    "ERROR_TASK_NOT_FOUND": TaskNotFoundError,
    "ERROR_INSUFFICIENT_BALANCE": InsufficientBalanceError,
    "ERROR_THREAD_LIMIT": ThreadLimitError,
    "ERROR_RATE_LIMITED": RateLimitError,
}

_BY_GROUP: Dict[int, Type[VoidCaptchaError]] = {
    1: AuthenticationError,
    2: InvalidRequestError,
    3: SolveError,
    4: BillingError,
    5: ServerError,
}

_GROUP_RETRY = {3: "yes", 5: "backoff"}


def from_response(body: Mapping[str, Any], http_status: Optional[int]) -> VoidCaptchaError:
    """Build the right exception for a failed API envelope."""
    code = body.get("errorCode")
    code = code if isinstance(code, str) and code else None
    raw_id = body.get("errorId")
    error_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else None
    description = body.get("errorDescription")
    if not isinstance(description, str) or not description:
        description = code or "The API reported a failure without a description."

    group = error_id // 100 if error_id is not None else 0
    cls = _BY_CODE.get(code or "") or _BY_GROUP.get(group, VoidCaptchaError)
    retry = RETRY.get(code or "", _GROUP_RETRY.get(group, "no"))
    return cls(
        description,
        code=code,
        error_id=error_id,
        http_status=http_status,
        retry=retry,
        response=body,
    )
