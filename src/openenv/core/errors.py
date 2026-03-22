"""Custom exceptions for Open-env."""


class OpenEnvError(Exception):
    """Base exception for Open-env failures."""


class ValidationError(OpenEnvError):
    """Raised when manifest or lockfile validation fails."""


class LockResolutionError(OpenEnvError):
    """Raised when lock-time dependency resolution cannot complete."""


class CommandError(OpenEnvError):
    """Raised when an external command fails."""

    def __init__(self, message: str, *, exit_code: int | None = None):
        """Store the human-readable command failure together with an optional exit code."""
        super().__init__(message)
        self.exit_code = exit_code
