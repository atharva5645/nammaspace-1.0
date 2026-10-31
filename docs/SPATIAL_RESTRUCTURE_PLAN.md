# NammaSpace Corporate Spatial Reconstruction — Implementation Blueprint

**Status:** Architecture baseline for iterative implementation  
**Last updated:** 30 October 2026  
**Related:** [`../TODO.md`](../TODO.md), [`NAMMASPACE_PRD.md`](NAMMASPACE_PRD.md), [`../spatial-engine/README.md`](../spatial-engine/README.md)

## Executive direction

Restructure NammaSpace as a browser-based, human-reviewed spatial modelling workflow for homeowners and architects. The browser collects a guided image set, project context, and metric constraints. An asynchronous engine generates versioned geometry. Users approve the measured wireframe, then approve a solid scene, then approve colors and object placeholders. Existing photorealistic splat viewing remains a separate visualization capability; it is not the source of truth for dimensions, collision, or editable architecture.

Build the workflow as modular product capabilities in the current repository. Do not create a new monorepo or discard existing reconstruction utilities until the benchmark establishes that a replacement is better. Create the dedicated `spatial-engine/` boundary for workers and contracts, and integrate it with the existing React/Vite frontend using a versioned API.

## User journeys

### Homeowner

1. Create a project, name the space, select units, and answer the minimum capture questions. Do not ask users to choose a persona mode.
2. Follow illustrated capture steps on the phone/camera, upload original room images, identify the capture route/rooms, and tick off doorway/corner/lighting checks.
3. Enter one reliable measured anchor distance; optionally add ceiling height, a floor plan, sketch, room dimensions, or sensor/depth package.
4. Submit and see real asynchronous processing stages, queue state, progress events, and actionable errors.
5. Review the metric wireframe with dimensions and uncertainty/residual badges. Make supported corrections, inspect the impact, then approve or request recapture.
6. Review neutral/glossy solid geometry; approve or return to edit the wireframe.
7. Review surface colors and common object placeholders; adjust, approve, and publish a shareable scene.

Professional planning fields such as project/client reference, CAD/BIM import, room IDs, export settings, and change history can appear under optional project details when needed. Keep these out of the main capture path and do not require users to select a persona mode.

## Guided capture SOP v1

The capture UI is the interactive rendering of this SOP: users see instructions before and during capture, confirm each pass, attach images to it, and resolve preflight warnings. A checklist tick is an attestation; image-analysis checks are separately computed evidence.

### Before capture

1. Get permission to capture the property and decide who can access the resulting images/model. Remove people and movable clutter where practical; note immovable objects, mirrors/glass, and occluded areas.
2. Create a room inventory. Label every room and connected doorway. Sketch the layout or annotate a floor plan. Mark the capture start point, route, openings, stairs, and planned measurement anchors.
3. Record device make/model, camera/lens selection, date/time, capture app, units, and whether depth/LiDAR is present. Keep original image/video metadata; do not use social-media compressed copies.
4. Measure at least one unambiguous, rigid, visible distance (preferably a long wall or doorway dimension) between identifiable endpoints. Record units and endpoints. If practical, also record floor-to-ceiling height, a second independent length, and room width/depth. Specify if a measurement is approximate.

### Capture each room

1. The minimum intake is four still images per room: one or more clear views assigned to each side, captured in clockwise order starting at the entrance. The UI labels these Side 1–4. These four images establish broad side coverage only; they do not guarantee photogrammetric overlap or complete geometry.
2. Add extra still photos at corners, doorways, occlusions, and floor/ceiling transitions. A video is optional. If supplied, it should be a slow, steady perimeter walk-through and may provide additional frames, but it does not replace the four side assignments or metric dimensions.
3. Use one selected camera lens throughout a pass. Avoid digital zoom and lens changes. Where supported, lock focus, white balance, and exposure; avoid blown windows and abrupt exposure changes.
4. Start with a slow continuous perimeter pass at approximately 1.4–1.7 m camera height. Aim at wall features, not directly at the floor. Keep images sharp; stop and hold briefly at turns rather than whipping the camera.
5. Aim for approximately 70% overlap between consecutive views and at least 60% overlap between neighboring passes. Treat these as initial operating targets; the device-specific guide and preflight results may tune them. Do not invent missing coverage by taking many near-identical images.
6. Capture each corner from both approaches. Add a second pass at a lower angle for floor boundaries/furniture bases and an upper view where ceiling edges or overhead features are hidden.
7. At each doorway or transition, capture at least five usable views on each side, including views looking across the threshold in both directions. Walk through the opening and continue far enough to connect the adjoining space. Repeat for halls and narrow transitions.
8. For multiple rooms, record the room label and pass boundary, then include an explicit connecting path. Never expect the processor to infer that two disconnected image sets touch.
9. Capture fixed objects that obscure geometry from more than one side. Note people, pets, moving fans, reflective surfaces, blank corridors, and glass as potential reconstruction risks.

### Validate and hand off

1. Review a thumbnail contact sheet for all four side assignments, blur, omissions, repeated frames, and exposure changes before leaving the site.
2. Intake preflight independently checks file integrity, image resolution, metadata, blur/sharpness, near-duplicates, camera/lens consistency, overlap/pose connectivity, and whether each declared room/doorway has observations. It returns pass/warn/block with specific affected images/areas.
3. A block requires more data or a documented override by an authorized reviewer. Overrides include operator, reason, evidence, SOP version, and time.
4. Upload original images plus room/pass assignment, capture metadata, units, measured dimensions and endpoints, optional plans/sensors, and consent/access classification. Resume failed uploads without re-selecting files.

**These capture targets are starting heuristics, not universal guarantees.** Pilot validation with the chosen camera mix must set final device-specific thresholds. A completed checklist cannot resolve a wrong or ambiguous anchor measurement.

The low-friction path asks for four still images (one assigned to each side) and one measured distance. Video, extra photos, floor plan, ceiling height, and professional project details are optional. This is minimum intake, not a promise that reconstruction can solve every room from five inputs. If image overlap, texture, or visibility is inadequate, preflight must request more evidence; it must not invent walls or report false precision.

## Human-in-the-loop workspace UX

The product should borrow Blender's persistent 3D viewport and direct manipulation while deliberately omitting its dense menus, node editor, and expert tool surface. The default experience is guided and mode-based; technical detail appears only when the user asks for it.

### Workspace frame

- A clear top bar for project/room name, save state, stage progress, help, and back/exit.
- A large central 3D viewport as the dominant part of the screen, with orbit/pan/zoom, fit-to-view, perspective/orthographic toggle, and clear selection.
- A compact left rail for captured images/evidence and stage navigation. Selecting a photo shows its side, quality warnings, and whether the latest reconstruction used it.
- A contextual right panel with only selected-object actions and relevant measurements. Raw solver data lives under a “Technical details” disclosure.
- A bottom revision strip for generated/edited versions, undo/redo, compare, and restore. Preserve approved revisions and confirm destructive resets.
- One strong primary action at a time: “Review wireframe”, “Approve and refine”, or “Add more photos”. Show actual save/job state clearly.

### Progressive detail, not a giant form

1. Ask only for project name, units (metric by default), four side-assigned still images, and one measured scale anchor. Default room label to “Room 1”; ceiling height, plan, video, extra photos, and professional project details remain optional.
2. Create a starter candidate only when the inputs support one. Mark inferred geometry with confidence and disclose missing observations. Keep “Improve this model” available to add dimensions, photos, a plan, or optional video later.
3. New evidence creates a candidate revision with a difference/impact summary. Never silently overwrite the reviewed revision; keep compare and rollback.
4. If the minimum data is insufficient, ask for the exact additional view, transition, or measurement needed and retain previously entered data.

### Image mask and crop review

- Keep every original image unchanged. Orientation correction or border trimming creates a reversible derived view with a mapping to original pixels.
- Offer a simple “Exclude from reconstruction” mode with brush, erase, polygon, undo/redo, reset, zoom, and transparent mask overlay. Initial use is transient objects or screenshot UI; never force a crop around the room itself.
- Model-suggested masks are labeled suggestions with a reason/confidence and explicit accept/edit/reject controls. Masks are versioned; uncertain boundaries default to no exclusion.
- Show original and mask result together, identify excluded areas, and state which processing stage uses the mask. Masking can be skipped.
- CV/segmentation may suggest regions; AI crop output must not set metric dimensions, room boundaries, or the 3D coordinate frame.

### Stage-specific interactions

- **Capture review:** large photo viewer, side/pass label, image-quality/coverage cues, optional masks, and “Add photos”.
- **Wireframe:** simple select/move/corner/opening actions, direct dimension labels, confidence colors, focused “needs review” list, one-click undo, and a 2D plan/elevation toggle.
- **Solid:** clean room form and a small neutral/glossy material palette; geometry correction returns to wireframe with an explanation.
- **Color and objects:** surface swatches and a small placeholder catalog; objects are marked estimated/user-placed with simple move/rotate/scale/delete controls.

Keep controls keyboard accessible with visible focus, tooltips as support (not sole instruction), tablet-friendly layout, no mandatory pointer lock, reduced-motion support, and clear empty/loading/error states. Heavy reconstruction and Blender work remains in background workers.

## Project intake fields

### Minimum required to start a room

- Project name, room name (default “Room 1”), units (metric by default), four still images assigned to sides 1–4, and one measured distance with visible endpoints.
- Consent/authorization confirmation and capture metadata where available. Role can default to homeowner; the user may select architect.
- Ceiling height, extra photos, video, floor plan, other room dimensions, LiDAR/depth, and professional details are optional improvements.
- Minimum input does not guarantee a usable reconstruction; preflight may request more evidence before creating a wireframe.

### Architect additions

Optional firm/project/client reference, plan revision, CAD/BIM/floor-plan file, room IDs, design-vs-existing state, and export preferences. Minimize personal data and keep optional fields genuinely optional.

## Three-stage modelling contract

Stages are independent, versioned artifacts with explicit acceptance. Processing is asynchronous; the UI only reports worker events actually received.

| Stage | Generated artifact | User can edit | Required evidence and approval |
|---|---|---|---|
| **1. Metric wireframe** | Coordinate frame; room/door graph; floor, wall, ceiling planes; corner nodes; openings; dimensions; constraint graph; optional observed point/mesh overlay; confidence/coverage. | Set scale from a known dimension; correct room outline; move a corner with connected edges preserved; add/remove/move an opening; set floor/ceiling height; undo/redo; mark an occlusion/unknown area. | Anchor residuals and uncertainty; pose/loop closure; plane/corner fit error; room dimensions; opening connectivity; coverage and unresolved regions; observed-vs-inferred labels. Must be approved before Stage 2. |
| **2. Solid geometry** | Clean architectural solids/surfaces in the same metric frame, with neutral or glossy standard materials and editable wall/floor/ceiling/opening elements. | Select element; change a small set of material presets; undo; send geometry correction back to Stage 1. | Unit/scale consistency; manifold/intersection diagnostics; surface coverage; opening/wall continuity; differences from approved wireframe. Approve before Stage 3. |
| **3. Color and object placeholders** | Surface color/material estimates with confidence/provenance, plus detected objects or editable generic placeholders (e.g., vase, sofa, table, plant). | Replace placeholder category; move/rotate/scale/delete; override colors; mark object uncertain. | Distinguish measured structure, image-derived material, inferred object, and user placeholder. Preserve approved architectural geometry. |

Any Stage 1 geometry edit invalidates dependent Stage 2/3 artifacts and marks them stale. Stage 2/3 appearance edits need not invalidate geometry. The user can keep the previous approved revision while a new version processes.

## Metrics and nodal constraints

The wireframe is a graph, not just a collection of lines:

- **Nodes:** measured/solved corners, opening endpoints, floor/ceiling intersections, control points, and room anchors. Each node stores coordinate, units/frame, source, observation count, covariance/uncertainty, locked/free state, and revision.
- **Edges:** wall segments, opening spans, room connections, and verticals. Store length, constraints, adjacency, evidence references, and residual.
- **Planes:** floor, ceiling, and wall fits. Store normal, offset, support observations, fit residual, and confidence.
- **Constraints:** known distances, parallel/perpendicular relationships when declared, shared-wall constraints, floor/ceiling heights, plan alignment, and loop closure. Store target, tolerance, weight/source, measured-vs-assumed status, residual after solve, and whether it is satisfied.

Initial quality report (calibrated on ground-truth pilots):

- Capture: images/usable images, resolution, blur/duplicate ratio, coverage by room/opening, pose-graph connectivity, and observed blind areas.
- Metric fit: anchor count and source, scale uncertainty, anchor residuals, independent-check residuals, room length/width/height residuals, corner/plane RMS, and loop-closure error.
- Geometry: missing/inferred surface percentage, room topology/opening consistency, mesh manifoldness/intersections, and outlier rates.
- Confidence: per-room/element/node confidence and reason, with observed vs inferred vs user-authored provenance.
- Readiness: blocked/warning/pass for next stage with actionable reasons; never only a single opaque score.

Do not choose numeric pass tolerances by intuition. Survey/laser-measured pilot ground truth, stakeholder use case, and error distribution establish tolerances for homeowner visualization versus architect documentation. UI labels must show units, tolerance policy, and whether an output is a measurement or estimate.

## Engine and technology strategy

### Blender

Use Blender as an open-source desktop creation tool and headless Python/Bpy geometry worker for mesh cleanup, deterministic procedural generation, validation, and interchange where benchmarks show value. Emit standard assets such as glTF/GLB and optionally Blender files for expert handoff. Use a versioned Blender container/worker image and record Blender version, add-ons, scripts, inputs, and outputs. Review Blender Python API stability and licensing obligations before enterprise distribution.

Do not describe Blender as the image-reconstruction solver or as an “accuracy standard.” It cannot infer hidden dimensions from photos without sufficient evidence. Camera pose estimation/SfM and dense geometry use dedicated reconstruction software; a metric optimizer fuses scale anchors and constraints; Blender processes and visualizes the resulting geometry.

### Existing web renderer and Unity

Keep React/Vite as product shell. Retain PlayCanvas/3DGS for existing photorealistic splat rendering. Render metric mesh and wireframe as separate overlays with selection/edit handles. The MVP modeller should be browser-first. Benchmark a Unity WebGL embedded build only if browser-native tools cannot deliver stable geometry editing, collision, or navigation; Unity does not improve source measurement accuracy. Preserve zero-install acceptance and use the same scene package format regardless of viewer engine.

### Reconstruction adapters

Reuse COLMAP/gsplat and capture-splat selectively for camera poses and visuals. Benchmark dense mesh alternatives for architectural surfaces, scale them using constraints, then compare against known ground truth. Do not force a 3DGS model into a mesh when extraction loses edges/floor topology; allow a hybrid sensor/plan-guided procedural architectural wireframe.

## Corporate target architecture

```text
Browser UI (React/Vite)
  ├─ project intake, resumable upload, SOP/preflight, review/edit stages
  ├─ metric geometry editor + PlayCanvas visual/3DGS view
  └─ API client / progress event subscription

API and identity boundary
  ├─ SSO/OIDC, tenant RBAC, project/scene/version APIs
  ├─ signed upload/download URLs and malware/file validation
  ├─ job orchestration, audit events, cancellation, review approvals
  └─ WebSocket/SSE progress feed

Durable services
  ├─ relational metadata DB (projects, constraints, versions, approvals)
  ├─ encrypted object storage (originals, plans, intermediates, published assets)
  ├─ queue + retry/dead-letter handling
  └─ isolated, versioned CPU/GPU reconstruction and Blender workers
```

Production requirements: tenant isolation at API, database, object, queue, and log layers; SSO and least-privilege roles; encryption in transit/at rest; signed short-lived asset URLs; consent and retention/deletion lifecycle; immutable audit for geometry edits/approvals; malware scanning; secrets management; resource quotas; worker sandboxing; monitoring/tracing/alerting; backups/recovery objectives; software/model provenance; data residency and vendor/license review. Keep sensitive media and proprietary plans out of logs and source control.

## API and job lifecycle

- `POST /projects` creates a tenant-owned draft with role and project metadata.
- `POST /projects/{id}/uploads` creates resumable upload sessions and expected file metadata.
- `POST /projects/{id}/intake-validation` starts preflight and returns findings with file/room references.
- `POST /projects/{id}/jobs` submits an immutable capture manifest, measurements, SOP version, and accepted warnings; returns a job ID.
- `GET /jobs/{id}` and SSE/WebSocket events expose real state, stage, progress, retryability, and safe error details.
- `GET /scenes/{id}/versions/{v}` returns versioned scene/geometry/metrics; `POST .../approvals` records reviewer, stage, revision hash, and decision.
- `POST .../edits` creates an authored revision with operations and optimistic concurrency token; never mutate a generated artifact in place.

Job state: `draft → uploading → preflight → queued → processing(stage) → needs_review(stage) → approved(stage) → processing(next) → published`, with `failed`, `cancelled`, `stale`, and `needs_recapture` transitions. Idempotency keys, input-hash deduplication, cooperative cancellation, bounded retries, and per-tenant concurrency limits are required.

## Delivery iterations and exit criteria

1. **Design validation:** align homeowner/architect journeys, pilot room, device list, privacy constraints, dimensions/tolerance class, and benchmark truth.
2. **Capture slice:** persistent project API, resumable image upload, SOP and quality preflight; make no reconstruction claims yet.
3. **Wireframe benchmark:** one measured room through reconstruction, constraint fitting, editable nodes, uncertainty display, and approval. Compare solver approaches against ground truth.
4. **Solid/color layers:** deterministic generation from approved revision with invalidation/version behavior and simple, deliberately limited editing.
5. **Pilot navigation/viewing:** POIs and obstacle-aware paths derive from approved architecture; retain free exploration.
6. **Enterprise readiness:** security/privacy review, load/failure testing, cost/capacity model, operational dashboards/runbooks, user pilot, and release approval.

Every iteration produces a demonstrable workflow slice, contract/geometry tests, benchmark evidence, a decision-log update, and TODO updates. “Looks right” is insufficient for metric acceptance; compare against independent measurements.

## Immediate implementation status

- New default frontend entry is the project-intake preview. The legacy 3D viewer remains accessible from the intake header and via `?view=demo`.
- The demo viewer has an Editor Mode panel with live whole-scene position/rotation/scale controls. These changes are in-memory preview state only; splat-only demo data cannot support individual wall/object geometry edits.
- The initial intake uses the reference's warm visual tone and simplified required inputs; it does not reproduce the inspiration dashboard's unrelated occupancy/analytics cards or ask users to choose a homeowner/architect mode.
- The pipeline preview is now an interactive PlayCanvas wireframe room with pointer-driven orbit and wheel zoom; it is example geometry, not a model generated from the user's intake.
- The Inter variable font is self-hosted through the frontend package rather than fetched from a remote font service.
- Current intake asks project name, room (defaulted), units, four side-assigned stills, SOP acknowledgments, and one scale reference. Role and ceiling height are optional; video, extra photos, and floor plan are optional.
- Intake now creates tenant-scoped local-development project records, accepts resumable chunk uploads, snapshots capture provenance into versioned preflight jobs, and exposes saved-project list/detail views. This is a local SQLite/disk development implementation, not corporate production storage.
- Preflight currently checks file signatures, image dimensions, brightness, blur hints, exact duplicates, near-duplicate hints, and required side assignments. It does not estimate camera poses, solve image geometry, construct meshes, or start later scene stages.
- The measured anchor can optionally be marked at two normalized points in one selected photo. These points are not matched to 3D coordinates yet, so metric scale registration remains unavailable end to end.
- `spatial-engine/` contains job/result and wireframe contracts, a weighted constraint solver/evaluator, geometry tests, image normalization, a COLMAP adapter, and a scale-registration primitive. The worker registers capture preflight only; no image-derived wireframe or 3D model is generated.
- The production bundle keeps intake separate from the lazy-loaded 3D viewer, but its PlayCanvas engine chunk is approximately 2.1 MB before gzip (about 545 kB gzip). Runtime/browser-device measurement and further tuning remain open.
