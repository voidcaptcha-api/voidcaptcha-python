"""The VoidCaptcha client."""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Union

import requests

from . import errors
from ._version import __version__
from .types import (
    AwsClient,
    DataDomeVariant,
    FunCaptchaVariant,
    GeetestRiskType,
    ReCaptchaMobileVariant,
    ReCaptchaV2Variant,
    ReCaptchaV3Variant,
)

__all__ = ["VoidCaptcha", "Solution", "DEFAULT_BASE_URL", "MIN_POLL_INTERVAL"]

DEFAULT_BASE_URL = "https://api.voidcaptcha.com"

#: The API refuses to be polled faster than this (seconds).
MIN_POLL_INTERVAL = 2.0

_SYNC = "/v1/getResult"
_CREATE = "/v1/createTask"
_CHECK = "/v1/checkTask"
_BALANCE = "/getBalance"

#: Where each task type puts its answer, by lowercase task.type prefix.
_VALUE_FIELD = (
    ("datadome", "datadome"),
    ("cfclearance", "cf_clearance"),
    ("awstoken", "aws_token"),
    ("geetest", "pass_token"),
)


def _value_field(task_type: str) -> str:
    t = task_type.lower()
    for prefix, field in _VALUE_FIELD:
        if t.startswith(prefix):
            return field
    return "token"


class Solution(Mapping[str, Any]):
    """A finished solve.

    Reads like the ``solution`` object itself (``result["token"]``), with the
    rest of the response envelope as attributes.

    Attributes:
        value: The type's main answer: ``token`` for most types,
            ``cf_clearance``, ``datadome``, ``aws_token`` or ``pass_token`` for
            the others. None if the type answered under another field; read it
            by name then.
        solution: The ``solution`` object, as a dict.
        user_agent: The User-Agent the solve ran under. Send it downstream.
        cost: What this solve charged, as the API printed it (e.g. "$0.0012").
        balance: Your balance after the call, as the API printed it.
        elapsed_ms: How long the solve took, when the API reported it.
        test_mode: True when the key is a test key (the token is synthetic).
        task_id: The task id, when the solve went through createTask.
        raw: The whole decoded response.
    """

    def __init__(
        self, raw: Mapping[str, Any], value_field: str = "token", task_id: Optional[str] = None
    ) -> None:
        sol = raw.get("solution")
        self.solution: Dict[str, Any] = dict(sol) if isinstance(sol, Mapping) else {}
        self.raw: Dict[str, Any] = dict(raw)
        self.value_field = value_field
        self.value: Any = self.solution.get(value_field)
        ua = self.solution.get("userAgent")
        self.user_agent: Optional[str] = ua if isinstance(ua, str) else None
        self.cost: Optional[str] = raw.get("cost") if isinstance(raw.get("cost"), str) else None
        self.balance: Optional[str] = (
            raw.get("balance") if isinstance(raw.get("balance"), str) else None
        )
        ms = raw.get("elapsedMs")
        self.elapsed_ms: Optional[int] = int(ms) if isinstance(ms, (int, float)) else None
        self.test_mode: bool = bool(self.solution.get("testMode"))
        self.task_id: Optional[str] = task_id

    def __getitem__(self, key: str) -> Any:
        return self.solution[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.solution)

    def __len__(self) -> int:
        return len(self.solution)

    def __repr__(self) -> str:
        v = self.value if not isinstance(self.value, str) or len(self.value) < 24 else self.value[:20] + "..."
        return f"Solution({self.value_field}={v!r}, cost={self.cost!r}, test_mode={self.test_mode})"


def _drop_none(d: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


class VoidCaptcha:
    """Client for https://voidcaptcha.com.

    Args:
        api_key: Your key (``void_`` + 32 hex). Defaults to the
            ``VOIDCAPTCHA_KEY`` environment variable. Test keys work the same
            way and return a synthetic solution without charging.
        timeout: Seconds to wait for one solve, end to end. The default covers
            the slowest type.
        poll: False (default) waits on one synchronous ``/v1/getResult`` call.
            True uses ``/v1/createTask`` and polls ``/v1/checkTask`` instead,
            for networks that cannot hold a connection open that long.
        poll_interval: Seconds between ``checkTask`` calls. Never below 2.
        request_timeout: Seconds for each individual HTTP call when polling.
        base_url: The API host. Change it only if support tells you to.
        session: A ``requests.Session`` to reuse (proxies, adapters, retries).
        soft_id: Optional label sent as ``softId`` and echoed back, for
            correlating your own logs.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: float = 210.0,
        poll: bool = False,
        poll_interval: float = MIN_POLL_INTERVAL,
        request_timeout: float = 30.0,
        base_url: str = DEFAULT_BASE_URL,
        session: Optional[requests.Session] = None,
        soft_id: Optional[str] = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("VOIDCAPTCHA_KEY", "")
        key = key.strip()
        if not key:
            raise errors.AuthenticationError(
                "No API key. Pass api_key= or set VOIDCAPTCHA_KEY.", code="ERROR_KEY_MISSING"
            )
        self.api_key = key
        self.timeout = float(timeout)
        self.poll = poll
        self.poll_interval = max(float(poll_interval), MIN_POLL_INTERVAL)
        self.request_timeout = float(request_timeout)
        self.base_url = base_url.rstrip("/")
        self.soft_id = soft_id
        self._own_session = session is None
        self.session = session or requests.Session()
        # Replace requests' own default, but keep a User-Agent the caller chose.
        if str(self.session.headers.get("User-Agent", "")).startswith("python-requests"):
            self.session.headers["User-Agent"] = f"voidcaptcha-python/{__version__}"
        self._sleep: Callable[[float], None] = time.sleep
        self._clock: Callable[[], float] = time.monotonic

    # ── plumbing ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the HTTP session, if this client created it."""
        if self._own_session:
            self.session.close()

    def __enter__(self) -> "VoidCaptcha":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _post(self, path: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        """POST, decode, and raise the right error for any failed envelope."""
        payload = {"clientKey": self.api_key, **body}
        try:
            res = self.session.post(self.base_url + path, json=payload, timeout=timeout)
        except requests.Timeout as e:
            raise errors.NetworkError(
                f"No answer from {path} within {timeout:g}s. A solve may still complete and be billed.",
                retry="backoff",
            ) from e
        except requests.RequestException as e:
            raise errors.NetworkError(f"Request to {path} failed: {e}", retry="backoff") from e

        try:
            data = res.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise errors.ServerError(
                f"Expected JSON from {path}, got HTTP {res.status_code}.",
                http_status=res.status_code,
                retry="backoff",
            )
        if data.get("errorId", 0) != 0 or data.get("status") == "failed" or res.status_code >= 400:
            raise errors.from_response(data, res.status_code)
        return data

    def _task_body(self, task: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(task.get("type"), str) or not task["type"]:
            raise errors.InvalidRequestError("task['type'] is required.", code="ERROR_REQUIRED_FIELD")
        body: Dict[str, Any] = {"task": _drop_none(task)}
        if self.soft_id:
            body["softId"] = self.soft_id
        return body

    # ── the API ──────────────────────────────────────────────────────────

    def solve(self, task: Mapping[str, Any], *, poll: Optional[bool] = None) -> Solution:
        """Solve any task, given as the API's own ``task`` object.

        ``task`` uses the wire field names from the docs, e.g.
        ``{"type": "Turnstile", "url": "...", "site_key": "..."}``. Keys whose
        value is None are dropped. Use this for any type or option the helper
        methods do not cover.
        """
        field = _value_field(str(task.get("type", "")))
        use_poll = self.poll if poll is None else poll
        if not use_poll:
            data = self._post(_SYNC, self._task_body(task), timeout=self.timeout)
            return Solution(data, field)
        task_id = self.create_task(task)
        return self.wait_for(task_id, value_field=field)

    def create_task(self, task: Mapping[str, Any]) -> str:
        """Hand a task over and return its ``taskId`` straight away."""
        data = self._post(_CREATE, self._task_body(task), timeout=self.request_timeout)
        task_id = data.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise errors.ServerError("createTask answered without a taskId.", response=data, retry="backoff")
        return task_id

    def check_task(self, task_id: str, *, value_field: str = "token") -> Optional[Solution]:
        """One look at a task: a Solution when done, None while it is processing.

        Raises the task's error if the solve failed, and TaskNotFoundError once
        the result has aged out (results are held for ten minutes).
        """
        data = self._post(_CHECK, {"taskId": task_id}, timeout=self.request_timeout)
        if data.get("status") == "processing":
            return None
        return Solution(data, value_field, task_id=task_id)

    def wait_for(
        self, task_id: str, *, timeout: Optional[float] = None, value_field: str = "token"
    ) -> Solution:
        """Poll ``checkTask`` every ``poll_interval`` seconds until the task finishes."""
        limit = self.timeout if timeout is None else float(timeout)
        deadline = self._clock() + limit
        network_misses = 0
        while True:
            self._sleep(self.poll_interval)
            try:
                data = self._post(_CHECK, {"taskId": task_id}, timeout=self.request_timeout)
            except errors.RateLimitError:
                data = {"status": "processing"}
            except errors.NetworkError:
                # checkTask is safe to repeat; a dropped poll is not a failed solve.
                network_misses += 1
                if network_misses >= 3:
                    raise
                data = {"status": "processing"}
            else:
                network_misses = 0
            if data.get("status") != "processing":
                return Solution(data, value_field, task_id=task_id)
            if self._clock() + self.poll_interval > deadline:
                raise errors.SolveTimeoutError(
                    f"Task {task_id} was still processing after {limit:g}s. "
                    "It may still finish and be billed; check it again with check_task().",
                    retry="backoff",
                )

    def balance(self) -> float:
        """Your balance in US dollars."""
        data = self._post(_BALANCE, {}, timeout=self.request_timeout)
        value = data.get("balance")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise errors.ServerError("getBalance answered without a balance.", response=data)
        return float(value)

    # ── one helper per public type ───────────────────────────────────────

    def turnstile(
        self, url: str, site_key: str, *, user_agent: Optional[str] = None, **extra: Any
    ) -> Solution:
        """Cloudflare Turnstile. Proxyless: the widget's action and cData are read off the page."""
        return self.solve(
            {"type": "Turnstile", "url": url, "site_key": site_key, "user_agent": user_agent, **extra}
        )

    def recaptcha_v2(
        self,
        url: str,
        site_key: str,
        *,
        proxy: str,
        variant: ReCaptchaV2Variant = "ReCaptchaV2",
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """reCAPTCHA v2, checkbox or invisible. ``variant`` selects Enterprise / Max."""
        return self.solve(
            {"type": variant, "url": url, "site_key": site_key, "proxy": proxy, "user_agent": user_agent, **extra}
        )

    def recaptcha_v3(
        self,
        url: str,
        site_key: str,
        *,
        proxy: str,
        action: Optional[str] = None,
        variant: ReCaptchaV3Variant = "ReCaptchaV3",
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """reCAPTCHA v3. ``action`` must match what the page passes to grecaptcha.execute."""
        return self.solve(
            {
                "type": variant,
                "url": url,
                "site_key": site_key,
                "action": action,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def recaptcha_mobile(
        self,
        site_key: str,
        *,
        proxy: Optional[str] = None,
        app_package: Optional[str] = None,
        action: Optional[str] = None,
        device: Optional[str] = None,
        device_model: Optional[str] = None,
        random_device: Optional[bool] = None,
        variant: ReCaptchaMobileVariant = "ReCaptchaMobile",
        **extra: Any,
    ) -> Solution:
        """reCAPTCHA Mobile (Android SDK). ``proxy`` is required for ReCaptchaMobile, ignored by ReCaptchaMobileDirect."""
        return self.solve(
            {
                "type": variant,
                "site_key": site_key,
                "app_package": app_package,
                "action": action,
                "device": device,
                "device_model": device_model,
                "random_device": random_device,
                "proxy": proxy,
                **extra,
            }
        )

    def funcaptcha(
        self,
        url: str,
        site_key: str,
        *,
        js_domain: str,
        proxy: str,
        blob: Optional[str] = None,
        variant: FunCaptchaVariant = "FunCaptcha_Invisible",
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """Arkose FunCaptcha. ``blob`` is single-use: fetch a fresh one per task."""
        return self.solve(
            {
                "type": variant,
                "url": url,
                "site_key": site_key,
                "JSdomain": js_domain,
                "blob": blob,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def datadome(
        self,
        url: str,
        *,
        proxy: str,
        ddk: Optional[str] = None,
        challenge_url: Optional[str] = None,
        method: Optional[str] = None,
        init_cookies: Optional[Union[str, Mapping[str, Any]]] = None,
        variant: DataDomeVariant = "datadome_Interstitial",
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """DataDome. ``result.value`` is the cookie; send ``result["headers"]`` with it."""
        return self.solve(
            {
                "type": variant,
                "url": url,
                "ddk": ddk,
                "challenge_url": challenge_url,
                "method": method,
                "init_cookies": init_cookies,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def incapsula(
        self,
        url: str,
        incapsula_url: str,
        *,
        proxy: str,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """Imperva Incapsula (reese84). ``incapsula_url`` is the reese84 script, not the page."""
        return self.solve(
            {
                "type": "IncapsulaToken",
                "url": url,
                "Incapsula_url": incapsula_url,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def geetest_v4(
        self,
        url: str,
        site_key: str,
        *,
        proxy: str,
        risk_type: Optional[GeetestRiskType] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """GeeTest v4. ``site_key`` is the captcha_id."""
        return self.solve(
            {
                "type": "GeetestV4",
                "url": url,
                "site_key": site_key,
                "riskType": risk_type,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def geetest_v3(
        self,
        url: str,
        gt: str,
        challenge: str,
        *,
        proxy: str,
        api_server_subdomain: Optional[str] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """GeeTest v3. ``challenge`` is single-use: fetch it fresh before every call."""
        return self.solve(
            {
                "type": "GeetestV3",
                "url": url,
                "gt": gt,
                "challenge": challenge,
                "geetestApiServerSubdomain": api_server_subdomain,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def hunt(
        self,
        url: str,
        api_get_lib: str,
        *,
        proxy: str,
        data: Optional[str] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """Hunt Captcha. Without ``data`` you get an X-HD; with the site's meta.token, the captcha token."""
        return self.solve(
            {
                "type": "HuntCaptcha",
                "url": url,
                "apiGetLib": api_get_lib,
                "data": data,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )

    def cf_clearance(
        self,
        url: str,
        *,
        proxy: str,
        timeout_ms: Optional[int] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """Cloudflare Clearance. Replay ``result["cookies"]`` with the returned user_agent and hints."""
        return self.solve(
            {
                "type": "CFClearance",
                "url": url,
                "proxy": proxy,
                "timeout": timeout_ms,
                "user_agent": user_agent,
                **extra,
            }
        )

    def aws_waf(
        self,
        url: str,
        *,
        proxy: str,
        client: Optional[AwsClient] = None,
        aws_js_url: Optional[str] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> Solution:
        """AWS WAF. Send ``result.value`` as the aws-waf-token cookie or x-aws-waf-token header."""
        return self.solve(
            {
                "type": "awsToken",
                "url": url,
                "client": client,
                "aws_js_url": aws_js_url,
                "proxy": proxy,
                "user_agent": user_agent,
                **extra,
            }
        )
