"""Literal types for the task.type variants and enum-like fields.

Only variants that are open to traffic are listed. ``VoidCaptcha.solve()``
accepts any ``task.type`` string, so a variant launched after this release
works there before the next version adds it here.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "ReCaptchaV2Variant",
    "ReCaptchaV3Variant",
    "ReCaptchaMobileVariant",
    "FunCaptchaVariant",
    "DataDomeVariant",
    "GeetestRiskType",
    "AwsClient",
]

ReCaptchaV2Variant = Literal[
    "ReCaptchaV2", "ReCaptchaV2Enterprise", "ReCaptchaV2Max", "ReCaptchaV2MaxEnterprise"
]
ReCaptchaV3Variant = Literal[
    "ReCaptchaV3",
    "ReCaptchaV3Enterprise",
    "ReCaptchaV3Fast",
    "ReCaptchaV3FastEnterprise",
    "ReCaptchaV3Max",
    "ReCaptchaV3EnterpriseMax",
]
ReCaptchaMobileVariant = Literal["ReCaptchaMobile", "ReCaptchaMobileDirect"]
FunCaptchaVariant = Literal["FunCaptcha_Invisible", "FunCaptcha_Puzzle", "FunCaptcha_Image"]
DataDomeVariant = Literal["datadome_Interstitial", "datadome_slider"]
GeetestRiskType = Literal["slide", "icon", "nine", "match", "winlinze"]
AwsClient = Literal["web", "android", "ios"]
