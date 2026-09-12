"""Basic tests for the UPSET package."""


def test_upset_import() -> None:
    """Verify that the UPSET package can be imported."""
    import upset

    assert upset is not None