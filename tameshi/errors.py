"""Error types for tameshi."""


class TameshiError(Exception):
    """Raised when an input is refused or a ruling cannot be generated."""


class PackValidationError(TameshiError):
    """Raised when an evidence pack disagrees with its rebuilt pack."""


class FloorRefusal(TameshiError):
    """Raised when a ruling is refused because the evidence is below the floor."""
