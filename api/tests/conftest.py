import os
from pathlib import Path
import shutil

TEST_DATABASE = Path("test-referrals.db")
TEST_LANDING_ZONE = Path("test-landingzone")
TEST_DATABASE.unlink(missing_ok=True)
shutil.rmtree(TEST_LANDING_ZONE, ignore_errors=True)
os.environ["LOCAL_MOCK_IDENTITY"] = "true"
os.environ["ALLOW_LOCAL_MOCK_EXTRACTION"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"
os.environ["LOCAL_LANDING_ZONE_ROOT"] = str(TEST_LANDING_ZONE)


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    del session, exitstatus
    from referral.database import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
    shutil.rmtree(TEST_LANDING_ZONE, ignore_errors=True)
