# Capture API and preflight worker

This service creates tenant-scoped project records, accepts resumable chunk uploads, validates uploaded file signatures, and queues a background capture-quality preflight. Preflight is not 3D reconstruction and does not certify dimensions.

Capture uploads support room photos, optional video, PDF/image floor plans, and optional PLY point clouds. PLY validation checks the header format and a nonzero vertex declaration; the configured global upload-size cap applies. Point clouds are stored as evidence but the current preflight/reconstruction flow does not interpret them.

During intake, users may optionally click the measured span's two endpoints on a selected photo. Normalized image coordinates and the source filename are stored with project provenance and copied into the immutable job snapshot. This is not yet a 2D-to-3D correspondence; scale registration remains disabled until reconstruction can match those points into the sparse scene.

## Local development

From `backend/api`:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

In a second terminal, from `backend/api`:

```powershell
.venv\Scripts\Activate.ps1
python -m app.worker
```

Run the frontend with `VITE_NAMMASPACE_API_URL=http://127.0.0.1:8000`. In Vite development mode it uses the local-only development bearer token. The fixed local token is rejected outside `APP_ENV=development`.

The API and worker resolve `.env`, SQLite, and local media paths relative to `backend/api`, even if launched from another working directory. A dimension-driven draft can be saved as an immutable, tenant-scoped wireframe revision and reopened through the project workspace API. Users can adjust its room dimensions and opening placeholders before saving another revision; each remains `needs_review` and is not approved geometry.

## Production boundary

Production access requires OIDC issuer, audience, JWKS URL, and a tenant claim. Configure allowed origins explicitly. This first implementation writes to local disk and SQLite for development; deploy behind corporate identity and network controls, then replace those adapters with approved object storage and a managed database before handling production data. Configure private storage, encryption, retention/deletion, malware scanning, upload quotas, backups, audit export, and worker concurrency as deployment requirements.

The worker queue is durable in SQLite but currently processes one job at a time. The preflight reports EXIF-corrected image dimensions, brightness, heuristic blur and near-duplicate hints, exact duplicate file hashes, and missing side assignments. Saved projects can be listed and reopened through tenant-scoped APIs; detail responses omit internal storage paths. The worker does not estimate camera poses, solve image geometry, construct meshes, or start later scene stages.
