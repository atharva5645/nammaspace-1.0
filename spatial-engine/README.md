# NammaSpace Spatial Engine

This folder is the boundary for the asynchronous pipeline that turns participant media and measured inputs into reviewable, versioned spatial scenes. It is separate from the browser renderer and from the existing experimental capture/training scripts. The geometry package includes a dimension-driven rectangular wireframe draft that the API can persist as an immutable, tenant-scoped revision; it remains provisional, uses only entered room dimensions, and carries no image-derived geometry or image coverage.

## Product output: three approval-gated layers

1. **Metric wireframe:** room/floor graph, measured dimensions, wall/floor/ceiling planes, corners, openings, units, coordinate frame, constraint residuals, and confidence/coverage. This is the geometry source of truth. “Blender-compatible” means the result can be exported as standard mesh/scene formats and opened/edited with Blender; Blender itself does not infer accurate geometry from photos.
2. **Solid scene:** generated surfaces and architectural solids with simple neutral/glossy materials. It must preserve a link back to the approved wireframe and report mesh defects.
3. **Color and objects:** colors/textures and object instances or labeled placeholders. Estimated objects remain distinguishable from measured architecture.

Every stage is an immutable generated version plus explicit user edits and an approval event. Editing a dimension invalidates dependent downstream layers and marks them stale; the system must not silently present stale output as current.

## Proposed boundaries

```text
spatial-engine/
  contracts/       # versioned job, constraint, scene, stage, and metric schemas
  orchestration/   # job state machine, retries, cancellation, idempotency
  geometry/        # wireframe graph QA and nodal/edge residual calculations
  reconstruction/  # upload staging, COLMAP adapter, metric scale registration
  workers/
    ingest/        # media validation, EXIF, frame extraction, quality signals
    reconstruction/# camera poses, SfM/MVS adapters, scale and alignment
    geometry/      # planes, room graph, constrained wireframe, validation
    blender/       # headless Blender/Bpy import/export and mesh operations
    materials/     # simple material/color and placeholder assignment
  adapters/        # adapters to existing COLMAP/gsplat/tooling
  tests/           # contract and synthetic geometry cases
```

This is the target module layout, not a claim that those services are already implemented. Versioned `spatial-job.v1` and `spatial-result.v1` JSON Schemas now exist; the reference worker runtime is in `backend/api/app/orchestration.py` and currently dispatches capture preflight only. The wireframe contract and deterministic candidate-graph metric evaluator exist in `contracts/wireframe.schema.json` and `geometry/constraints.py`. `geometry/solver.py` adds a small-room, damped least-squares adjustment for weighted distance measurements, with optional node position priors and fixed nodes. `reconstruction/` now contains checksum-bound image staging, an adapter to the existing Capture Splat/COLMAP sparse-SfM runner, and a scale-registration function requiring matched 3D endpoints. These are not yet wired into API jobs; COLMAP is not installed in the current development environment, and intake does not collect endpoint correspondences. No image-derived wireframe or 3D model is generated. Keep binaries and raw user uploads outside source control and use managed object storage in production.

## Processing sequence

`intake accepted → preflight → camera/pose solve → metric registration → wireframe generation → constraint/mesh QA → author review → solid generation → author review → color/placeholders → publish`

The implemented capture worker claims `queued` jobs transactionally, increments attempt count, validates the versioned envelope, dispatches a registered handler, and stores a structured result atomically. Its input snapshot pins the project/SOP values and completed evidence upload IDs, hashes, media types, sides, and storage keys. Successful preflight jobs expose the report through the existing job API; they have no 3D artifacts. Retry leases, cancellation, production queues, and reconstruction progress are future work. See [`orchestration/README.md`](orchestration/README.md) for current runtime limits.

## Geometry and metrics

The engine must not label a result “precise” from image count or feature-match count alone. Capture inputs provide scale anchors; the solver reports each anchor's measured value, fitted value, residual, and uncertainty. Geometry QA should include coordinate units/scale, registration coverage, plane/corner residuals, loop closure, floor flatness, opening connectivity, mesh defects, and areas without observation. Tolerance bands are configured per project class and calibrated against an independently measured pilot dataset.

An initial proposed data flow is images/video + EXIF + user dimensions/floor plan/optional depth → COLMAP or compatible camera/SfM solver → metric scale and constraint adjustment → geometric primitives/mesh → Blender Bpy for deterministic mesh operations and interchange export → glTF/GLB for browser review, with source scene and provenance retained. Select each solver after the Phase 1 benchmark; Blender is not a substitute for SfM/MVS or metric controls.

## Integration contract (initial)

- API owns project, tenant, user authorization, job submission/status, and artifact access.
- Worker consumes an immutable input manifest and writes stage artifacts plus structured progress/results.
- Scene manifests reference versioned artifacts by ID/URI and declare units, up-axis, transforms, geometry revision, stage approvals, and readiness.
- Frontend never fabricates processing progress; it subscribes/polls for real job events and shows the last completed stage if a worker is unavailable.

See [`../TODO.md`](../TODO.md) for the live build sequence and completion state.
