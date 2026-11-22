import os

import pytest

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"


@pytest.fixture(autouse=True)
def _fresh_result_cache():
    """Tests that change analyzers must not get a result cached by another test."""
    from app.services import result_cache

    result_cache.clear()
    yield
    result_cache.clear()
