"""Shared bounded startup allowance for every managed application launch."""

from typing import Final


# Cold startup on slower machines can exceed 20 seconds. This finite allowance
# applies equally to current launch, candidate health, rollback and recovery;
# preparation and process shutdown keep their independent phase budgets.
MANAGED_STARTUP_HEALTH_TIMEOUT_SEC: Final[float] = 120.0
