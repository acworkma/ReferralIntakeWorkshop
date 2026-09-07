import os
from pathlib import Path

TEST_DATABASE = Path("test-referrals.db")
TEST_DATABASE.unlink(missing_ok=True)
os.environ["LOCAL_MOCK_IDENTITY"] = "true"
os.environ["ALLOW_LOCAL_MOCK_EXTRACTION"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    del session, exitstatus
    from referral.database import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
