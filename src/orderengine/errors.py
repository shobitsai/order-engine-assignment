class ValidationError(ValueError):
    """Raised when order input data is invalid (bad amounts, impossible discounts, ...).

    Type misuse (e.g. passing a float where exact money is required) raises
    TypeError instead, so programming errors are distinguishable from bad data.
    """
