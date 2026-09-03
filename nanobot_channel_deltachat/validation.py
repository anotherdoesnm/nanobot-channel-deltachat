"""Delta Chat setup validation owned by the channel package."""

from typing import Any

from nanobot.channels.contracts import ChannelValidationContext
from nanobot.channels.validation import check, required_checks, status_from_checks, string_value


def validate(
    values: dict[str, Any],
    context: ChannelValidationContext,
) -> dict[str, Any]:
    checks, missing = required_checks("deltachat", values)

    account_url = string_value(values.get("accountUrl"))
    if account_url:
        if account_url.lower().startswith("dcaccount:"):
            checks.append(
                check(
                    "account_url",
                    "Account URL",
                    "pass",
                    "DCACCOUNT account URL is set.",
                )
            )
        else:
            checks.append(
                check(
                    "account_url",
                    "Account URL",
                    "fail",
                    "Account URL must start with DCACCOUNT: "
                    "(e.g. DCACCOUNT://nine.testrun.org).",
                )
            )

    identity = {"account": account_url}
    return status_from_checks("deltachat", checks, missing, identity=identity)


__all__ = ["validate"]
