# voidcaptcha

Official Python client for [VoidCaptcha](https://voidcaptcha.com), the CAPTCHA solving API.
Cloudflare Turnstile and Clearance, reCAPTCHA v2 / v3 / Mobile, AWS WAF, DataDome, Imperva
Incapsula, Arkose FunCaptcha, GeeTest and Hunt, through one small typed client.

```bash
pip install voidcaptcha
```

Python 3.9+. One dependency: `requests`.

## Quick start

```python
from voidcaptcha import VoidCaptcha

client = VoidCaptcha("void_your_api_key")  # or set VOIDCAPTCHA_KEY

result = client.turnstile(
    "https://example.com/register",
    "0x4AAAAAAADnPIDROrmt1Wwj",
)
print(result.value)       # the Turnstile token
print(result.user_agent)  # the User-Agent the solve ran under
print(result.cost)        # what it charged, e.g. "$0.0012"
```

Get a key at [voidcaptcha.com](https://voidcaptcha.com). Prices, supported sites and
limits are on the website and in the [docs](https://voidcaptcha.com/docs); nothing in
this package hard-codes them.

## Every type

Each helper takes the documented fields as keyword arguments and returns a `Solution`.
`result.value` is the type's main answer; every other field of the API's `solution`
object reads like a dict: `result["cookies"]`.

```python
proxy = "proxy.example.com:9090:user:pass"   # sticky session

# reCAPTCHA v2 (checkbox / invisible). variant: ReCaptchaV2Enterprise, ReCaptchaV2Max, ...
client.recaptcha_v2("https://example.com/login", "6LcR_okUAAAAAPYrPe-HK_0RULO1aZM15ENyM-Mf", proxy=proxy)

# reCAPTCHA v3. action must match what the page passes to grecaptcha.execute
client.recaptcha_v3("https://example.com/login", "6LdyC2cUAAAAACGuDKpXeDorzUDWXmdqeg-xy696",
                    action="login", proxy=proxy)

# reCAPTCHA Mobile (Android). ReCaptchaMobileDirect needs no proxy
client.recaptcha_mobile("6Lf...", app_package="com.example.app", variant="ReCaptchaMobileDirect")

# Cloudflare Clearance: replay the cookies AND the identity
cf = client.cf_clearance("https://example.com/", proxy=proxy)
cookies = cf["cookies"]
headers = {"User-Agent": cf["user_agent"], "sec-ch-ua": cf["sec_ch_ua"],
           "sec-ch-ua-platform": cf["sec_ch_ua_platform"]}

# AWS WAF: send result.value as the aws-waf-token cookie or x-aws-waf-token header
client.aws_waf("https://example.com/api/search", proxy=proxy)

# DataDome: result.value is the cookie, result["headers"] the identity that earned it
client.datadome("https://example.com/search?q=shoes", proxy=proxy)

# Imperva Incapsula (reese84): the second argument is the reese84 script URL
client.incapsula("https://example.com/account", "https://example.com/Towardiant-Thou-Wals-Becommeth-Lady-Macb",
                 proxy=proxy)

# Arkose FunCaptcha. variant: FunCaptcha_Invisible, FunCaptcha_Puzzle, FunCaptcha_Image
client.funcaptcha("https://example.com/signup", "476068BF-9607-4799-B53D-966BE98E2B81",
                  js_domain="client-api.arkoselabs.com", proxy=proxy)

# GeeTest v4 and v3. result.value is pass_token; the other fields are on the result
client.geetest_v4("https://example.com/register", "54088bb07d2df3c46b79f80300b0abbe", proxy=proxy)
client.geetest_v3("https://example.com/register", gt="022397c99c9f646f6477822485f30404",
                  challenge="fresh-challenge", proxy=proxy)

# Hunt Captcha: first call without data gives an X-HD, then send the site's meta.token
client.hunt("https://example.com/en/registration",
            "https://example.com/hd-api/external/apps/<app-hash>/api.js", proxy=proxy)
```

Anything a helper does not name passes straight through: `client.turnstile(url, key, foo="bar")`
sends `"foo": "bar"` in the task. For a type or option without a helper, send the API's own
`task` object:

```python
result = client.solve({"type": "ReCaptchaV3Fast", "url": "...", "site_key": "...", "proxy": proxy})
```

## Waiting: one call, or create and poll

By default each solve is one synchronous call to `/v1/getResult` that holds open until the
answer is ready. If your network cannot hold a connection that long (serverless, strict
proxies), poll instead:

```python
client = VoidCaptcha(poll=True)                # every solve via createTask + checkTask
result = client.turnstile(url, site_key)

# or drive it yourself
task_id = client.create_task({"type": "Turnstile", "url": url, "site_key": site_key})
result = client.wait_for(task_id)              # polls every 2 s, the API's minimum
```

`check_task(task_id)` looks once and returns `None` while the task is still processing.
Results are held for ten minutes; after that `check_task` raises `TaskNotFoundError`.

## Errors

Every API failure raises a subclass of `VoidCaptchaError` with the API's `code`,
`error_id`, `description` and `http_status`, plus `retryable`:

| Exception | Codes | Retry? |
|---|---|---|
| `AuthenticationError` | 100-range: bad, missing or suspended key | no |
| `InvalidRequestError` (`TaskNotFoundError`) | 200-range: the request is wrong | no |
| `SolveError` | 300-range: blocked IP, unsolvable, timeout. Not charged | yes |
| `BillingError` (`InsufficientBalanceError`, `ThreadLimitError`, `RateLimitError`) | 400-range | balance: no; limits: after a pause |
| `ServerError` | 500-range, or a non-JSON answer | after a pause |
| `NetworkError` | no answer at all | after a pause, but see below |
| `SolveTimeoutError` | `wait_for` gave up | check the task again |

```python
import voidcaptcha

for attempt in range(3):
    try:
        result = client.recaptcha_v2(url, site_key, proxy=proxy)
        break
    except voidcaptcha.SolveError as e:
        print("retrying after", e.code)
```

Solves are not idempotent. A `NetworkError` on the synchronous call can mean the solve
finished and was charged after your side gave up; use `soft_id=` to correlate.
The full code list is at [voidcaptcha.com/docs/errors](https://voidcaptcha.com/docs/errors).

## Balance and test keys

```python
print(client.balance())   # 12.34 (US dollars)
```

A test key (created in the dashboard) runs the same code path and returns a
correctly shaped but synthetic token, charging nothing. `result.test_mode` is `True` for
those.

## Options

```python
VoidCaptcha(
    api_key=None,          # default: VOIDCAPTCHA_KEY
    timeout=210,           # seconds for one solve, end to end
    poll=False,            # True: createTask + checkTask instead of one held call
    poll_interval=2.0,     # never below 2
    request_timeout=30,    # per HTTP call while polling
    session=None,          # your own requests.Session (proxies to reach the API, retries)
    soft_id=None,          # label echoed back as softId
)
```

`VoidCaptcha` is also a context manager and closes its session on exit.

## Links

- Docs: https://voidcaptcha.com/docs
- API reference: https://voidcaptcha.com/docs/api-reference
- Node.js client: https://www.npmjs.com/package/voidcaptcha
- Support: https://t.me/VoidCaptchaSupport

MIT licensed.
