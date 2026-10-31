import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .settings import get_settings

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    room_name TEXT NOT NULL,
    units TEXT NOT NULL CHECK (units IN ('m', 'ft')),
    known_distance REAL NOT NULL CHECK (known_distance > 0),
    anchor_name TEXT NOT NULL DEFAULT 'Measured span',
    anchor_start_label TEXT NOT NULL DEFAULT '',
    anchor_end_label TEXT NOT NULL DEFAULT '',
    anchor_view_side TEXT NOT NULL DEFAULT 'side1',
    anchor_source TEXT NOT NULL DEFAULT 'tape',
    anchor_confidence TEXT NOT NULL DEFAULT 'medium',
    anchor_picks_json TEXT NOT NULL DEFAULT '{}',
    room_length REAL CHECK (room_length IS NULL OR room_length > 0),
    room_width REAL CHECK (room_width IS NULL OR room_width > 0),
    openings_json TEXT NOT NULL DEFAULT '[]',
    ceiling_height REAL CHECK (ceiling_height IS NULL OR ceiling_height > 0),
    sop_version TEXT NOT NULL DEFAULT 'capture-v1',
    sop_acknowledgments_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS projects_tenant_created ON projects(tenant_id, created_at);

CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    tenant_id TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('room_image', 'extra_image', 'video', 'floor_plan', 'sensor_data')),
    side TEXT CHECK (side IS NULL OR side IN ('side1', 'side2', 'side3', 'side4')),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    expected_sha256 TEXT,
    actual_sha256 TEXT,
    status TEXT NOT NULL CHECK (status IN ('receiving', 'complete', 'rejected')),
    storage_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, original_name, category, side, byte_size)
);
CREATE INDEX IF NOT EXISTS uploads_project_tenant ON uploads(project_id, tenant_id, status);

CREATE TABLE IF NOT EXISTS upload_parts (
    upload_id TEXT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    part_number INTEGER NOT NULL CHECK (part_number >= 0),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    sha256 TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    PRIMARY KEY(upload_id, part_number)
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('capture_preflight', 'sparse_reconstruction')),
    contract_version TEXT NOT NULL DEFAULT 'spatial-job.v1',
    input_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    report_json TEXT,
    output_json TEXT,
    error_code TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS jobs_tenant_project ON jobs(tenant_id, project_id, created_at);

CREATE TABLE IF NOT EXISTS wireframe_revisions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    tenant_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    parent_revision INTEGER,
    review_state TEXT NOT NULL CHECK (review_state IN ('needs_review', 'approved')),
    model_json TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, revision)
);
CREATE INDEX IF NOT EXISTS wireframe_revisions_tenant_project ON wireframe_revisions(tenant_id, project_id, revision);
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    path = get_settings().database_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20, isolation_level=None, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def initialize_database() -> None:
    db = connect()
    try:
        db.executescript(SCHEMA)
        upload_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='uploads'").fetchone()["sql"]
        if "'sensor_data'" not in upload_sql:
            # SQLite cannot alter a CHECK constraint. Rebuild this table while FK
            # checks are paused; upload_parts continues referencing the same table name.
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("""CREATE TABLE uploads_with_sensor_data (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                tenant_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('room_image', 'extra_image', 'video', 'floor_plan', 'sensor_data')),
                side TEXT CHECK (side IS NULL OR side IN ('side1', 'side2', 'side3', 'side4')),
                byte_size INTEGER NOT NULL CHECK (byte_size > 0),
                expected_sha256 TEXT,
                actual_sha256 TEXT,
                status TEXT NOT NULL CHECK (status IN ('receiving', 'complete', 'rejected')),
                storage_key TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, original_name, category, side, byte_size)
            )""")
            db.execute("INSERT INTO uploads_with_sensor_data SELECT * FROM uploads")
            db.execute("DROP TABLE uploads")
            db.execute("ALTER TABLE uploads_with_sensor_data RENAME TO uploads")
            db.execute("CREATE INDEX IF NOT EXISTS uploads_project_tenant ON uploads(project_id, tenant_id, status)")
            db.execute("PRAGMA foreign_keys = ON")
        project_columns = {row["name"] for row in db.execute("PRAGMA table_info(projects)").fetchall()}
        if "sop_version" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN sop_version TEXT NOT NULL DEFAULT 'capture-v1'")
        if "sop_acknowledgments_json" not in project_columns:
            db.execute("ALTER TABLE projects ADD COLUMN sop_acknowledgments_json TEXT NOT NULL DEFAULT '[]'")
        project_migrations = {
            "anchor_name": "TEXT NOT NULL DEFAULT 'Measured span'",
            "anchor_start_label": "TEXT NOT NULL DEFAULT ''",
            "anchor_end_label": "TEXT NOT NULL DEFAULT ''",
            "anchor_view_side": "TEXT NOT NULL DEFAULT 'side1'",
            "anchor_source": "TEXT NOT NULL DEFAULT 'tape'",
            "anchor_confidence": "TEXT NOT NULL DEFAULT 'medium'",
            "anchor_picks_json": "TEXT NOT NULL DEFAULT '{}'",
            "room_length": "REAL",
            "room_width": "REAL",
            "openings_json": "TEXT NOT NULL DEFAULT '[]'",
        }
        for column, definition in project_migrations.items():
            if column not in project_columns:
                db.execute(f"ALTER TABLE projects ADD COLUMN {column} {definition}")
        job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
        job_migrations = {
            "contract_version": "TEXT NOT NULL DEFAULT 'spatial-job.v1'",
            "input_json": "TEXT NOT NULL DEFAULT '{}'",
            "output_json": "TEXT",
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "worker_id": "TEXT",
            "started_at": "TEXT",
            "finished_at": "TEXT",
        }
        for column, definition in job_migrations.items():
            if column not in job_columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
        job_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()["sql"]
        if "'sparse_reconstruction'" not in job_sql:
            # SQLite cannot alter CHECK constraints. Preserve every queued,
            # running, and completed job while extending the supported kinds.
            db.execute("PRAGMA foreign_keys = OFF")
            db.execute("DROP TABLE IF EXISTS jobs_with_reconstruction")
            db.execute("""CREATE TABLE jobs_with_reconstruction (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                tenant_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('capture_preflight', 'sparse_reconstruction')),
                contract_version TEXT NOT NULL DEFAULT 'spatial-job.v1',
                input_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
                report_json TEXT,
                output_json TEXT,
                error_code TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                worker_id TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            columns = "id,project_id,tenant_id,kind,contract_version,input_json,status,report_json,output_json,error_code,attempt_count,worker_id,started_at,finished_at,created_at,updated_at"
            db.execute(f"INSERT INTO jobs_with_reconstruction ({columns}) SELECT {columns} FROM jobs")
            db.execute("DROP TABLE jobs")
            db.execute("ALTER TABLE jobs_with_reconstruction RENAME TO jobs")
            db.execute("CREATE INDEX jobs_queue ON jobs(status, created_at)")
            db.execute("CREATE INDEX jobs_tenant_project ON jobs(tenant_id, project_id, created_at)")
            db.execute("PRAGMA foreign_keys = ON")
    finally:
        db.close()


@contextmanager
def transaction(immediate: bool = False):
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
