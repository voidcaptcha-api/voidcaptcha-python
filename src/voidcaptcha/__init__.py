"""Official Python client for the VoidCaptcha CAPTCHA solving API.

    from voidcaptcha import VoidCaptcha

    client = VoidCaptcha("void_...")
    result = client.turnstile("https://example.com/register", "0x4AAAAAAADnPIDROrmt1Wwj")
    print(result.value)

Docs: https://voidcaptcha.com/docs
"""

from ._version import __version__
from .client import DEFAULT_BASE_URL, MIN_POLL_INTERVAL, Solution, VoidCaptcha
from .errors import (
    AuthenticationError,
    BillingError,
    InsufficientBalanceError,
    InvalidRequestError,
    NetworkError,
    RateLimitError,
    ServerError,
    SolveError,
    SolveTimeoutError,
    TaskNotFoundError,
    ThreadLimitError,
    VoidCaptchaError,
)

__all__ = [
    "__version__",
    "VoidCaptcha",
    "Solution",
    "DEFAULT_BASE_URL",
    "MIN_POLL_INTERVAL",
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
