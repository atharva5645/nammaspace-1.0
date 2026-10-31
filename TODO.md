# NammaSpace Restructure - Living TODO

**Product direction:** browser-based spatial reconstruction workbench for homeowners and architects. Guided capture produces three reviewable, versioned deliverables: (1) dimensioned wireframe, (2) solid/material preview, and (3) color plus object placeholders. A human approves each stage before the next stage is generated.

**Accuracy rule:** photographs alone cannot guarantee metric precision. Collect measured dimensions and optional floor plans/sensor data; report uncertainty and constraint residuals; require review before calling geometry dimensionally validated.

**Low-friction UX:** start from four side-assigned still images and one measured scale anchor; video, extra photos, floor plan, ceiling height, and architect metadata are optional. The first result may be incomplete and must show uncertainty; users can add evidence and refine a new revision later.

**Current checkpoint:** intake persists projects, chunked media, SOP acknowledgments, measured-anchor provenance including optional normalized image-space endpoint picks, optional room dimensions and openings, optional plans, and optional validated PLY point clouds. Versioned job snapshots carry these inputs. A dimension-driven rectangular wireframe can be previewed, edited for room length/width/height and opening placeholders, saved as tenant-scoped immutable `needs_review` revisions, and reopened. The sparse-SfM action runs against uploaded photos; a user run produced 9 registered cameras and 593 sparse points (an earlier run produced 11 cameras and 942 points). This is only photo alignment and sparse evidence. The UI now explicitly says no 3D surface was generated and moves the four internal diagnostic downloads behind an optional disclosure. Dense reconstruction, an in-app image-derived surface, metric-scale registration, and architectural surface extraction are not implemented. The bundled local COLMAP build is CPU-only/no-CUDA, so dense MVS capability has not been demonstrated. Moving wireframe corners, undo/redo, and approval are also not implemented. Production identity, object storage, managed queue/database, and pilot accuracy criteria remain deployment/product blockers.

## Decision log

- [x] Keep the browser application as the user-facing product; no native install required.
- [x] Keep the existing PlayCanvas/3DGS viewer for photorealistic viewing.
- [x] Establish `spatial-engine/` as the boundary for contracts, orchestration, geometry, metrics, and Blender processing.
- [x] Treat Blender/Bpy as geometry processing and scene-authoring tooling, not as the photogrammetry engine or an accuracy guarantee.
- [x] Wire a guided intake preview as the default frontend entry and preserve the existing viewer as a demo (`?view=demo`).
- [x] Simplify intake to project/room name, units, four side-assigned stills, SOP acknowledgments, and one measured distance; remove homeowner/architect mode selection and make ceiling height optional.
- [x] Reduce the initial required input to project name, four side-assigned photos, and one scale measurement; role and ceiling height are optional, as are video, extra photos, and floor plan.
- [x] Update capture UI to require photos for four room sides while keeping room video explicitly optional; keep extra detail photos optional.
- [x] Preserve the header action to open the current 3D demo viewer from the new intake journey.
- [x] Add a viewer control that returns from a demo scene to the initial project-intake page.
- [x] Set Room-001 Hall as the default scene when opening the demo viewer without an explicit scene parameter.
- [x] Add demo Editor Mode with live whole-scene position/rotation/uniform-scale controls and explicit local-only/no-save status.
- [x] Apply the reference's warm, spacious visual direction to the initial intake page without copying its unrelated dashboard widgets.
- [x] Bundle the Inter variable font locally and increase intake typography for readability.
- [x] Replace the decorative CSS pipeline sketch with an interactive PlayCanvas 3D wireframe preview (drag orbit, wheel zoom).
- [x] Lazy-load the 3D preview and demo viewer so the intake UI can render before the 3D engine chunks.
- [x] Production build passes; the intake entry is split from the PlayCanvas preview/demo engine chunk.
- [ ] Evaluate production runtime performance on supported desktop browsers and tune the preview's 3D asset/chunk budgets.
- [x] Document SOP, three approval-gated stages, constraint graph, enterprise architecture, and metric acceptance strategy in `docs/SPATIAL_RESTRUCTURE_PLAN.md`.
- [x] Add initial versioned wireframe schema and candidate-graph evaluator for measured edge lengths, distance residuals, components, isolated nodes, and invalid references.
- [x] Add automated contract/geometry cases and independently review metric evaluator output before using it in production readiness gates; exact edge lengths, zero-residual constraints, graph connectivity, invalid references, and solver residual reduction are covered. This is code verification, not pilot accuracy validation.
- [x] Improve intake error reporting for unreachable API and make opening fields adapt to the form panel width; block incomplete opening submissions and preserve a valid zero wall offset.
- [x] Simplify the dimensions step to one visible required measured distance plus a fixed optional room-dimension grid; collapse optional openings, measurement metadata/photo marks, and extra files. Keep submit enabled until actual upload begins so validation can explain any missing field.
- [x] Add a separately queued sparse reconstruction action to saved projects, report actual worker status/results, and expose tenant-checked downloads for the image manifest, SfM summary, camera poses, and sparse points.
- [x] Add the sparse reconstruction action, live status, downloads, and overlap-photo recovery directly to the post-preflight confirmation page.
- [x] Label sparse alignment as an intermediate (not a finished 3D model), move diagnostic downloads behind an optional disclosure, and state clearly that no surface was generated.
- [ ] Make an in-app image-derived surface preview the primary successful-run outcome after dense reconstruction exists.
- [ ] Compare browser-native and Unity WebGL navigation only if measured browser requirements are not met.
- [ ] Confirm pilot room, device mix, image retention policy, and definition/tolerance of dimensional accuracy.

## Phase 0 - Product and measurement baseline

- [ ] Confirm pilot users, room types, reference devices, privacy/access policy, and dimensional accuracy requirements.
- [ ] Approve SOP v1 and supported capture modes.
- [ ] Establish benchmark rooms with independently measured ground truth and tolerance bands.
- [ ] Define image, geometry, job, and project API contracts with tenant, provenance, version, and audit fields.

## Phase 1 - Intake and guided capture

- [x] Replace viewer-first landing with a first-pass intake flow; keep the legacy viewer accessible.
- [x] Collect project/room name, units, four side-assigned stills, one scale anchor, and checklist acknowledgments; no persona mode is required and ceiling height is optional.
- [x] Add four side-specific local image slots, optional video, optional detail photos, and the SOP checklist to intake preview.
- [x] Add optional room length/width, structured openings, measured-anchor description/endpoints/photo side/source/confidence, and optional floor-plan/sketch upload. API persistence and immutable job snapshots include these values; project/preflight summaries expose them.
- [x] Add optional sensor/depth-file intake: accept PLY point clouds, validate the header and vertex declaration, enforce the configured upload limit, and snapshot the evidence category. Broader depth formats and sensor interpretation remain future work.
- [x] Let users mark the two measured-anchor endpoints on a selected room photo and persist normalized image coordinates and source filename through project and job snapshots.
- [ ] Match marked image points to reconstructed 3D endpoint coordinates and register measured scale; image picks alone do not yet drive metric scale registration.
- [ ] Design/build the simple human-review workbench: large 3D canvas, evidence rail, contextual controls, revisions/undo, confidence overlays, and assisted masking. **Started:** capture confirmation now summarizes submitted dimensions, openings, scale-anchor provenance, and optional evidence; geometry-stage review/editor is still pending until reconstruction artifacts exist.
- [ ] Build editable wireframe operations (walls/corners/openings), object-level tools, persistent save/undo, and mask review; demo splats currently support whole-scene transform only.
- [ ] Add room/pass assignment, thumbnail review, upload ordering, duplicate/blur feedback, and accessible capture instructions.
- [x] Replace browser-local staging with API-backed chunk uploads and persistent project/media metadata for the local development deployment.
- [x] Add API-backed capture preflight and durable background-job submission; report actual worker state and findings without simulated progress.
- [x] Resolve local API configuration, SQLite, and media-storage paths from `backend/api` so API and worker share the same database when launched from different terminal folders.
- [ ] Productionize intake persistence with corporate OIDC configuration, approved object storage, managed database/queue, malware scanning, retention/deletion, and worker scaling.
- [ ] Persist upload session recovery across browser refresh and add durable project listing/reopen. **Partial:** tenant-scoped saved-project list/detail endpoints and a library view now reopen metadata, upload inventory, and latest preflight status; upload sessions can resume when the same files are reselected, but browser-held capture fields/file handles are not restored automatically.
- [ ] Calibrate image orientation/EXIF, blur, coverage confidence, and near-duplicate detection. **Partial:** preflight applies EXIF orientation and reports Laplacian blur hints plus dHash near-duplicate pairs; thresholds and coverage signals remain uncalibrated and require a labeled pilot capture set.

## Phase 2 - Spatial engine and Stage 1 wireframe

- [x] Implement versioned `spatial-job.v1` / `spatial-result.v1` contracts, immutable capture evidence snapshots, worker handler dispatch, atomic job claims/results, and legacy queued-job upgrade path; reconstruction handler remains unregistered.
- [x] Add a solver that adjusts candidate node coordinates against weighted distance measurements, honors fixed nodes and optional positional priors, and reports residuals/convergence/underconstraint indicators. It requires candidate geometry; camera-pose and image-to-geometry inference remain unimplemented.
- [x] Test reconstruction image staging for checksum binding, EXIF normalization, and storage-path safety; test SfM adapter prerequisite errors and required sparse artifacts without claiming a real COLMAP run.
- [ ] Integrate media ingest, camera pose estimation, sparse/dense reconstruction, and metric scale registration. **Partial:** checksum-bound image normalization with common-size center cropping, a verified local Capture Splat command, official COLMAP 4.2.1 CPU binaries in ignored `tools/colmap-4.2.1/`, an adapter to the sparse runner, a registered queued worker job, tenant-checked sparse artifact downloads, and a scale-registration primitive are implemented. User captures have completed sparse SfM (9 cameras/593 points and 11 cameras/942 points). Dense MVS, mesh generation, in-app surface visualization, endpoint correspondences, and metric scale registration are still absent; sparse data is not sufficient evidence for a reliable architectural surface. The local COLMAP build is explicitly no-CUDA, so dense-stereo runtime compatibility must be established before claiming an end-to-end surface result.
- [ ] Fuse measured dimensions/floor plan/depth constraints; record residuals, confidence, and ambiguity per constraint.
- [ ] Generate editable architecture wireframe: floor/wall/ceiling planes, corners, openings, room graph, dimensions, and coordinate frame. **Partial:** an on-demand 3D draft uses explicit length/width/ceiling dimensions and creates corners, edges, constraints, and dimensioned opening frames. It is labeled as a rectangular assumption with zero image coverage and can be edited for dimensions/openings and saved/reopened as tenant-scoped `needs_review` revisions. It is not derived from uploaded images and cannot yet edit corners or be approved.
- [ ] Provide limited edits: set known dimension, move corner, add/remove opening, set floor/ceiling height, undo/redo, reset to generated. **Partial:** dimensions and opening labels/types/walls/sizes/offsets can be revised with immutable revision history; corner movement, undo/redo, and reset remain.
- [ ] Require wireframe approval before Stage 2; save generated and authored revisions plus audit history.

## Phase 3 - Stage 2 solid/material preview

- [ ] Convert approved wireframe into metric solids with mesh diagnostics.
- [ ] Assign simple standard materials and openings; preserve links to wireframe constraints.
- [ ] Add a small material preset editor and approval gate; geometry edits return to Stage 1 review.
- [ ] Validate non-manifold edges, intersections, missing surfaces, scale, and room connectivity.

## Phase 4 - Stage 3 color and object placeholders

- [ ] Add image-derived or user-selected surface colors with provenance/confidence and manual overrides.
- [ ] Suggest common object categories where confidence permits; otherwise provide labeled placeholders (vase, sofa, table, plant).
- [ ] Allow simple move/rotate/scale/delete and placeholder category replacement.
- [ ] Distinguish measured architecture, inferred objects, and user-authored placeholders.

## Phase 5 - Navigation and enterprise release

- [ ] Derive reviewed walkable surface, obstacles, POIs, and route graph/navmesh from approved geometry.
- [ ] Add free first-person browser walkthrough, POI selection, obstacle-aware routes, and unreachable states.
- [ ] Implement tenant isolation, SSO/RBAC, encryption, retention/deletion, audit, observability, backup/recovery, and deployment controls.
- [ ] Benchmark load time, memory, browser support, reconstruction quality, and route correctness; document limitations.
- [ ] Pilot with homeowners and architects; prioritize revisions from measured user feedback.

## Current repository disposition

- Keep `frontend/namma-space` as the browser shell; current viewer is preserved as a demo.
- Keep `pipeline-capture-splat`, COLMAP/gsplat assets, and `pipeline/filter` selectively; add adapters after benchmarking.
- Keep `pipeline/tools/tool-splat-transform` for web visual asset delivery.
- `spatial-engine/` contains versioned job/result JSON Schemas, geometry metrics/solver, initial geometry/contract tests, image staging, COLMAP adapter, scale-registration primitive, and orchestration/worker-interface documentation. The Python reference runner in `backend/api/app/orchestration.py` registers capture preflight and sparse reconstruction; dense image-to-surface reconstruction and scene generation remain unimplemented.
- Exclude `archive/`, `scratch/`, research trackers, and raw training experiments from deployed runtime unless a reviewed dependency requires them.

## Update convention

Update this file with every implementation change: mark only evidenced work complete, move the checkpoint forward, record assumptions/decisions, and name blockers and needed owners. A UI mock does not count as a working upload, reconstruction, or metric feature.
