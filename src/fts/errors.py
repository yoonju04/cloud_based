"""Errors for the handoff control plane."""


class FtsError(Exception):
    """Base error. Callers can catch this without catching every Exception."""


class PackageIntegrityError(FtsError):
    """A package hash, fingerprint, or self-check did not match."""


class TransitionError(FtsError):
    """The job is not in a state that allows this operation."""


class LeaseError(FtsError):
    """The caller does not hold a live lease."""


class IdempotencyConflict(FtsError):
    """An idempotency key was reused for a different request."""


class AlreadyCommitted(FtsError):
    """This job already has a committed result. A second result was rejected."""


class EnvironmentMismatch(FtsError):
    """The worker refused a request that does not match its pinned environment."""


class AdapterUnavailable(FtsError):
    """The adapter is a stub, or it has no result to fetch."""
