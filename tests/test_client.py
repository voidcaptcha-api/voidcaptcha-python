import json

import pytest
import requests
import responses

import voidcaptcha
from voidcaptcha import VoidCaptcha

KEY = "void_a1b2c3d4e5f60718293a4b5c6d7e8f90"
API = "https://api.voidcaptcha.com"


def ready(solution, **extra):
    return {"errorId": 0, "status": "ready", "solution": solution, "cost": "$0.0012", "balance": "$9.99", **extra}


def failed(error_id, code, desc="nope"):
    return {"errorId": error_id, "status": "failed", "errorCode": code, "errorDescription": desc}


def sent(call):
    return json.loads(call.request.body)


@pytest.fixture
def client():
    c = VoidCaptcha(KEY)
    c._sleep = lambda s: None  # polling tests should not take real seconds
    return c


# ── construction ──────────────────────────────────────────────────────────


def test_key_from_environment(monkeypatch):
    monkeypatch.setenv("VOIDCAPTCHA_KEY", KEY)
    assert VoidCaptcha().api_key == KEY


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("VOIDCAPTCHA_KEY", raising=False)
    with pytest.raises(voidcaptcha.AuthenticationError) as e:
        VoidCaptcha()
    assert e.value.code == "ERROR_KEY_MISSING"


def test_poll_interval_never_below_two_seconds():
    assert VoidCaptcha(KEY, poll_interval=0.1).poll_interval == 2.0
    assert VoidCaptcha(KEY, poll_interval=5).poll_interval == 5.0


def test_base_url_override():
    assert VoidCaptcha(KEY, base_url="https://alt.example/").base_url == "https://alt.example"


# ── synchronous solves ────────────────────────────────────────────────────


@responses.activate
def test_turnstile_sync(client):
    responses.post(f"{API}/v1/getResult", json=ready({"token": "0.abc", "userAgent": "UA"}, elapsedMs=1820))
    r = client.turnstile("https://example.com/register", "0x4AAAAAAADnPIDROrmt1Wwj")

    assert sent(responses.calls[0]) == {
        "clientKey": KEY,
        "task": {"type": "Turnstile", "url": "https://example.com/register", "site_key": "0x4AAAAAAADnPIDROrmt1Wwj"},
    }
    assert r.value == "0.abc" and r["token"] == "0.abc" and dict(r) == {"token": "0.abc", "userAgent": "UA"}
    assert r.user_agent == "UA" and r.cost == "$0.0012" and r.balance == "$9.99"
    assert r.elapsed_ms == 1820 and r.test_mode is False
    assert responses.calls[0].request.headers["User-Agent"] == f"voidcaptcha-python/{voidcaptcha.__version__}"


@responses.activate
def test_none_fields_dropped_and_extras_passed(client):
    responses.post(f"{API}/v1/getResult", json=ready({"token": "t"}))
    client.recaptcha_v3("https://e.com", "6Ld", proxy="h:1:u:p", variant="ReCaptchaV3Enterprise", foo="bar")
    assert sent(responses.calls[0])["task"] == {
        "type": "ReCaptchaV3Enterprise", "url": "https://e.com", "site_key": "6Ld", "proxy": "h:1:u:p", "foo": "bar",
    }


HELPERS = [
    (lambda c: c.recaptcha_v2("u", "k", proxy="p"), "ReCaptchaV2", "token", {"site_key": "k", "proxy": "p"}),
    (lambda c: c.recaptcha_mobile("k", variant="ReCaptchaMobileDirect", random_device=True),
     "ReCaptchaMobileDirect", "token", {"random_device": True}),
    (lambda c: c.funcaptcha("u", "k", js_domain="client-api.arkoselabs.com", proxy="p"),
     "FunCaptcha_Invisible", "token", {"JSdomain": "client-api.arkoselabs.com"}),
    (lambda c: c.datadome("u", proxy="p", challenge_url="cu"), "datadome_Interstitial", "datadome",
     {"challenge_url": "cu"}),
    (lambda c: c.incapsula("u", "https://e.com/abc", proxy="p"), "IncapsulaToken", "token",
     {"Incapsula_url": "https://e.com/abc"}),
    (lambda c: c.geetest_v4("u", "k", proxy="p", risk_type="slide"), "GeetestV4", "pass_token",
     {"site_key": "k", "riskType": "slide"}),
    (lambda c: c.geetest_v3("u", "gt", "ch", proxy="p", api_server_subdomain="s"), "GeetestV3", "pass_token",
     {"gt": "gt", "challenge": "ch", "geetestApiServerSubdomain": "s"}),
    (lambda c: c.hunt("u", "lib", proxy="p", data="m"), "HuntCaptcha", "token", {"apiGetLib": "lib", "data": "m"}),
    (lambda c: c.cf_clearance("u", proxy="p", timeout_ms=90000), "CFClearance", "cf_clearance", {"timeout": 90000}),
    (lambda c: c.aws_waf("u", proxy="p", client="web"), "awsToken", "aws_token", {"client": "web"}),
]


@pytest.mark.parametrize("call, task_type, value_field, wire", HELPERS)
@responses.activate
def test_every_helper_sends_wire_names(client, call, task_type, value_field, wire):
    responses.post(f"{API}/v1/getResult", json=ready({value_field: "VALUE"}))
    r = call(client)
    task = sent(responses.calls[0])["task"]
    assert task["type"] == task_type
    for k, v in wire.items():
        assert task[k] == v
    assert r.value == "VALUE"


@responses.activate
def test_test_key_solution(client):
    body = ready({"token": "voidcaptcha_test_000", "elapsed_time": "0.00", "testMode": True})
    body["cost"] = "$0.0000"
    responses.post(f"{API}/v1/getResult", json=body)
    r = client.turnstile("u", "k")
    assert r.test_mode is True and r.cost == "$0.0000"


@responses.activate
def test_soft_id_is_sent():
    c = VoidCaptcha(KEY, soft_id="job-42")
    responses.post(f"{API}/v1/getResult", json=ready({"token": "t"}))
    c.turnstile("u", "k")
    assert sent(responses.calls[0])["softId"] == "job-42"


# ── errors ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status, error_id, code, cls, retryable",
    [
        (401, 101, "ERROR_KEY_INVALID", voidcaptcha.AuthenticationError, False),
        (400, 202, "ERROR_REQUIRED_FIELD", voidcaptcha.InvalidRequestError, False),
        (404, 206, "ERROR_TASK_NOT_FOUND", voidcaptcha.TaskNotFoundError, False),
        (200, 301, "ERROR_IP_BLOCKED", voidcaptcha.SolveError, True),
        (200, 305, "ERROR_TIMEOUT", voidcaptcha.SolveError, True),
        (200, 399, "ERROR_NO_DDK", voidcaptcha.SolveError, True),  # unlisted code: the group decides
        (402, 400, "ERROR_INSUFFICIENT_BALANCE", voidcaptcha.InsufficientBalanceError, False),
        (429, 401, "ERROR_THREAD_LIMIT", voidcaptcha.ThreadLimitError, True),
        (429, 402, "ERROR_RATE_LIMITED", voidcaptcha.RateLimitError, True),
        (500, 500, "ERROR_INTERNAL", voidcaptcha.ServerError, True),
    ],
)
@responses.activate
def test_error_mapping(client, status, error_id, code, cls, retryable):
    responses.post(f"{API}/v1/getResult", json=failed(error_id, code, "why"), status=status)
    with pytest.raises(cls) as e:
        client.turnstile("u", "k")
    err = e.value
    assert isinstance(err, voidcaptcha.VoidCaptchaError)
    assert err.code == code and err.error_id == error_id and err.http_status == status
    assert err.description == "why" and err.retryable is retryable
    assert err.response["errorCode"] == code


@responses.activate
def test_non_json_response_is_server_error(client):
    responses.post(f"{API}/v1/getResult", body="<html>502 Bad Gateway</html>", status=502)
    with pytest.raises(voidcaptcha.ServerError) as e:
        client.turnstile("u", "k")
    assert e.value.http_status == 502 and e.value.code is None


@responses.activate
def test_network_failure(client):
    responses.post(f"{API}/v1/getResult", body=requests.ConnectionError("reset"))
    with pytest.raises(voidcaptcha.NetworkError):
        client.turnstile("u", "k")


@responses.activate
def test_read_timeout_is_network_error(client):
    responses.post(f"{API}/v1/getResult", body=requests.ReadTimeout("slow"))
    with pytest.raises(voidcaptcha.NetworkError) as e:
        client.turnstile("u", "k")
    assert "billed" in str(e.value)


def test_task_without_type(client):
    with pytest.raises(voidcaptcha.InvalidRequestError):
        client.solve({"url": "u"})


# ── createTask / checkTask ────────────────────────────────────────────────


@responses.activate
def test_poll_mode(client):
    sleeps = []
    client._sleep = sleeps.append
    responses.post(f"{API}/v1/createTask", json={"errorId": 0, "status": "processing", "taskId": "vt_1"})
    responses.post(f"{API}/v1/checkTask", json={"errorId": 0, "status": "processing"})
    responses.post(f"{API}/v1/checkTask", json=ready({"cf_clearance": "CF", "userAgent": "UA"}))

    r = client.solve({"type": "CFClearance", "url": "u", "proxy": "p"}, poll=True)
    assert r.value == "CF" and r.task_id == "vt_1"
    assert sent(responses.calls[1]) == {"clientKey": KEY, "taskId": "vt_1"}
    assert sleeps == [2.0, 2.0]


@responses.activate
def test_client_level_poll_setting():
    c = VoidCaptcha(KEY, poll=True)
    c._sleep = lambda s: None
    responses.post(f"{API}/v1/createTask", json={"errorId": 0, "status": "processing", "taskId": "vt_2"})
    responses.post(f"{API}/v1/checkTask", json=ready({"token": "T"}))
    assert c.turnstile("u", "k").value == "T"
    assert [x.request.url for x in responses.calls] == [f"{API}/v1/createTask", f"{API}/v1/checkTask"]


@responses.activate
def test_poll_rides_out_rate_limit_and_network_blip(client):
    responses.post(f"{API}/v1/createTask", json={"errorId": 0, "status": "processing", "taskId": "vt_3"})
    responses.post(f"{API}/v1/checkTask", json=failed(402, "ERROR_RATE_LIMITED"), status=429)
    responses.post(f"{API}/v1/checkTask", body=requests.ConnectionError("blip"))
    responses.post(f"{API}/v1/checkTask", json=ready({"token": "T"}))
    assert client.solve({"type": "Turnstile", "url": "u", "site_key": "k"}, poll=True).value == "T"


@responses.activate
def test_poll_raises_solve_failure(client):
    responses.post(f"{API}/v1/createTask", json={"errorId": 0, "status": "processing", "taskId": "vt_4"})
    responses.post(f"{API}/v1/checkTask", json=failed(303, "ERROR_CAPTCHA_UNSOLVABLE"))
    with pytest.raises(voidcaptcha.SolveError):
        client.solve({"type": "Turnstile", "url": "u", "site_key": "k"}, poll=True)


@responses.activate
def test_poll_timeout(client):
    now = [0.0]
    client._clock = lambda: now[0]

    def tick(s):
        now[0] += s

    client._sleep = tick
    responses.post(f"{API}/v1/checkTask", json={"errorId": 0, "status": "processing"})
    with pytest.raises(voidcaptcha.SolveTimeoutError):
        client.wait_for("vt_5", timeout=7)
    assert now[0] <= 7


@responses.activate
def test_check_task_once(client):
    responses.post(f"{API}/v1/checkTask", json={"errorId": 0, "status": "processing"})
    responses.post(f"{API}/v1/checkTask", json=ready({"aws_token": "A"}))
    assert client.check_task("vt_6") is None
    r = client.check_task("vt_6", value_field="aws_token")
    assert r.value == "A" and r.task_id == "vt_6"


@responses.activate
def test_create_task_returns_id(client):
    responses.post(f"{API}/v1/createTask", json={"errorId": 0, "status": "processing", "taskId": "vt_7"})
    assert client.create_task({"type": "Turnstile", "url": "u", "site_key": "k"}) == "vt_7"


# ── balance ───────────────────────────────────────────────────────────────


@responses.activate
def test_balance(client):
    responses.post(f"{API}/getBalance", json={"errorId": 0, "balance": 12.34, "packages": []})
    assert client.balance() == 12.34
    assert sent(responses.calls[0]) == {"clientKey": KEY}


@responses.activate
def test_balance_bad_key(client):
    responses.post(f"{API}/getBalance", json=failed(101, "ERROR_KEY_INVALID"), status=401)
    with pytest.raises(voidcaptcha.AuthenticationError):
        client.balance()
