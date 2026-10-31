import time
import logging

from .database import initialize_database
from .orchestration import migrate_legacy_queued_jobs, process_one_job
from .settings import get_settings


def main():
    initialize_database()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    delay = max(0.2, get_settings().worker_poll_seconds)
    migrated = migrate_legacy_queued_jobs()
    if migrated:
        print(f"Upgraded {migrated} queued job(s) to spatial-job.v1.", flush=True)
    print("NammaSpace spatial job worker started; registered handlers: capture_preflight, sparse_reconstruction.", flush=True)
    while True:
        if not process_one_job():
            time.sleep(delay)


if __name__ == "__main__":
    main()
