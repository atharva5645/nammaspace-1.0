# Spatial job orchestration v1

The reference runtime is `backend/api/app/orchestration.py`; language-neutral envelopes and results are specified in `../contracts/job.schema.json` and `../contracts/job-result.schema.json`.

## Contract and state

- Every queued job stores a validated `spatial-job.v1` envelope and an immutable snapshot of the exact project inputs and completed evidence assets (including asset hashes and storage keys).
- Every successful handler returns `spatial-result.v1` with the job type, structured output, and artifact references. `capture_preflight` currently has no generated 3D artifacts.
- A worker claims a queued row transactionally, increments its attempt count, validates the envelope version, and dispatches only to a registered handler. Unknown job types or unsupported contract versions fail closed with a stable error code.
- State transitions are `queued -> running -> completed|failed`. Results and timestamps are committed atomically. Failed jobs are not silently retried; a retry policy must be explicitly added with idempotency and lease semantics.
- Tenant and project IDs travel in the envelope and are checked against database ownership before assets are read.

## Handler interface

A handler accepts an immutable `JobEnvelope` and returns a validated `JobResult`. It must be deterministic for a fixed input snapshot where practical, must not mutate source uploads, and must write derived artifacts under job-scoped IDs. It must report structured errors rather than return fabricated progress. The registry contains `capture_preflight` and `sparse_reconstruction`. The latter stages checksum-bound images, runs Capture Splat/COLMAP, and returns camera poses plus sparse points; it does not register metric scale or generate architectural surfaces. Dense reconstruction, endpoint correspondence, scale registration, surface extraction, and real-capture benchmarking remain pending.

The local reference runner uses SQLite and processes one job at a time. This is for development only; production needs a managed queue/database, leases, concurrency limits, retry/dead-letter policies, cancellation, and observability.
