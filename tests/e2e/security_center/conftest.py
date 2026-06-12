"""Security Center e2e fixture bridge.

The explicit Web inbox entrypoint uses the same real API/Web/runtime subprocess
baseline as integration security tests so Web observations cannot drift into a
separate fake environment.
"""

pytest_plugins = ("tests.integration.conftest",)
