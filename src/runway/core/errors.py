"""Error taxonomy. Messages never contain payload data."""

from __future__ import annotations


class RunwayError(Exception):
    """Base class for all Runway errors."""

    code = "RUNWAY_ERROR"


class ContractError(RunwayError):
    code = "CONTRACT_ERROR"


class ProviderError(RunwayError):
    code = "PROVIDER_ERROR"

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class OutputParseError(RunwayError):
    code = "OUTPUT_PARSE_ERROR"


class ValidatorCrashed(RunwayError):
    code = "VALIDATOR_ERROR"


class RepeatedOutputError(RunwayError):
    code = "REPEATED_OUTPUT"


class BudgetExceededError(RunwayError):
    code = "BUDGET_EXCEEDED"

    def __init__(self, scope: str, dimension: str, used: float, limit: float) -> None:
        super().__init__(f"{scope} budget exceeded on {dimension}: {used} > {limit}")
        self.scope, self.dimension, self.used, self.limit = scope, dimension, used, limit


class ReplayStaleError(RunwayError):
    code = "REPLAY_STALE"


class ConfigError(RunwayError):
    code = "CONFIG_ERROR"


class TaskFailed(RunwayError):
    """Raised inside the runtime to fail a task with a stable error code."""

    def __init__(self, error_code: str, attempts: int = 0) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.attempts = attempts
