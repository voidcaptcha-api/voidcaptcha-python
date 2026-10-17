# Changelog

## 0.1.0

First release.

- `VoidCaptcha` client: `solve()` for any task, plus `turnstile()`, `recaptcha_v2()`,
  `recaptcha_v3()`, `recaptcha_mobile()`, `funcaptcha()`, `datadome()`, `incapsula()`,
  `geetest_v4()`, `geetest_v3()`, `hunt()`, `cf_clearance()`, `aws_waf()`.
- Synchronous `/v1/getResult` by default; `poll=True` uses `createTask` / `checkTask`
  (never faster than every 2 s).
- `balance()`, typed errors by error group, test-key support.
