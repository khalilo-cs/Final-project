import os

os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["REQUESTS_PER_LEVEL"] = "40"
os.environ["LOAD_LEVELS"] = "[1, 5, 10]"
os.environ["STARTUP_TIMEOUT_SECONDS"] = "5"
