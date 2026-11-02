"""Error types for keeporkill."""


class KeeporkillError(Exception):
    """Raised when an input is refused or a ruling cannot be generated."""


class PackValidationError(KeeporkillError):
    """Raised when an evidence pack disagrees with its rebuilt pack."""


class FloorRefusal(KeeporkillError):
    """Raised when a ruling is refused because the evidence is below the floor."""
