"""Contract-layer exceptions."""


class ContractError(ValueError):
    """Raised when shared facts or their immutable identities are invalid."""
