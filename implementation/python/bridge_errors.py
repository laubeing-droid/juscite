"""Shared bridge exceptions — imported by legal_entry and e07_coordinator.

Lives in its own module (no imports) so the classes are single objects even
when legal_entry runs as a script: a module-level cross-import between
legal_entry and e07_coordinator would create a second legal_entry instance
under import and the exception types would no longer match.
"""


class NotConnected(RuntimeError):
    pass


class HarnessCommandError(RuntimeError):
    """Typed harness business failure (UnitsError code) or entry failure."""


class SessionRejected(RuntimeError):
    """F-9 fail-closed rejection at the session-creation entry (T18)."""
