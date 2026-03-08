"""Test configuration and fixtures."""
import scripts.llm_router as llm_router


def pytest_runtest_setup(item):
    """Reset global state before each test to prevent state leakage."""
    # Reset the requests.Session singleton between tests
    llm_router._session = None
