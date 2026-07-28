"""Fail-closed hardware compatibility gate."""

from hardware_identity import DECISION, parse_decision

SUPPORTED_REVISION = "ORIGINAL_MAGTAG_2.9"
SUPPORTED_CONTROLLERS = ("UC8151D", "IL0373")


def validate(config):
    decision = parse_decision(
        getattr(config, "HARDWARE_COMPATIBILITY_DECISION", DECISION)
    )
    if decision != "COMPATIBLE":
        raise RuntimeError(
            "hardware identity decision is %s; physical display refused" % decision
        )
    if not config.ENABLE_PHYSICAL_DISPLAY:
        raise RuntimeError(
            "Physical display disabled. Complete docs/HARDWARE_SETUP.md first."
        )
    if config.MAGTAG_REVISION != SUPPORTED_REVISION:
        raise RuntimeError("unsupported or unconfirmed MagTag revision")
    if config.DISPLAY_CONTROLLER not in SUPPORTED_CONTROLLERS:
        raise RuntimeError("unsupported or unconfirmed display controller")
    return True
