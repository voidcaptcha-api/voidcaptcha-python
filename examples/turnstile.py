"""Solve one Cloudflare Turnstile and print the result.

    VOIDCAPTCHA_KEY=void_... python examples/turnstile.py https://example.com/register 0x4AAAAAAADnPIDROrmt1Wwj

Add --poll to go through createTask / checkTask instead of one held call.
"""

import sys
import time

import voidcaptcha
from voidcaptcha import VoidCaptcha


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--poll"]
    if len(args) != 2:
        print(__doc__)
        return 2
    url, site_key = args

    with VoidCaptcha(poll="--poll" in sys.argv) as client:
        print("balance before:", client.balance())
        started = time.monotonic()
        try:
            result = client.turnstile(url, site_key)
        except voidcaptcha.VoidCaptchaError as e:
            print("failed:", e.code, e.description)
            return 1
        print(f"solved in {time.monotonic() - started:.1f}s")
        print("token:", (result.value or "")[:40] + "...")
        print("cost:", result.cost, "| test mode:", result.test_mode, "| task:", result.task_id)
        print("balance after:", client.balance())
    return 0


if __name__ == "__main__":
    sys.exit(main())
