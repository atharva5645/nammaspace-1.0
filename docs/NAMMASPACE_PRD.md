# NammaSpace Spatial Walkthrough — Product Requirements Document

**Status:** Draft for approval  
**Version:** 0.1  
**Date:** 30 October 2026  
**Decision requested:** Approve product scope and the proposed web-first 3D architecture before implementation begins.

> **Product direction updated:** The user has since expanded the requirement to a homeowner/architect capture and modelling workbench with three explicit approval-gated stages: metric wireframe, solid geometry, then color and object placeholders. [`SPATIAL_RESTRUCTURE_PLAN.md`](SPATIAL_RESTRUCTURE_PLAN.md) is the current detailed direction for those workflows, the guided SOP, nodal constraints, enterprise architecture, and implementation sequence. This earlier PRD remains the foundation for browser delivery, capture quality, scene validation, and navigation; where the two documents differ, follow the newer restructure plan and update this PRD before treating it as the single approved baseline.

## 1. Product summary

NammaSpace will turn a captured indoor space into a reviewable, labeled, walkable digital twin that runs in a desktop browser without a client install. A visitor can freely explore the space, select a point of interest (POI), and follow an automatically planned route to it. The twin must combine a photorealistic visual representation with metrically grounded walkable geometry; a visually convincing reconstruction by itself is not sufficient for safe, floor-constrained navigation.

The current repository already contains a React/Vite and PlayCanvas web viewer, first-person controls, scene manifests and quality reporting, capture/reconstruction utilities, and 3D Gaussian Splatting (3DGS) assets. The project should preserve these useful assets and workflows while adding the geometric, semantic, and navigation layers that the stated requirements need.

## 2. Problem and opportunity

Today, a user can view a reconstructed scene and move a camera through configured bounds. Scene manifests include camera settings and generic waypoints. The system does not yet establish a validated floor surface, collision geometry, room/zone POIs, or an obstacle-aware path from the user's position to a selected destination. The current viewer's bounds-based movement is not equivalent to walking on a floor or avoiding furniture. Capture guidance exists in project reports but is not yet a versioned, enforced participant SOP.

This product closes that gap by treating capture, reconstruction, geometric validation, semantic authoring, and browser delivery as one quality-controlled workflow.

## 3. Goals and success measures

### Goals

1. Define and publish a repeatable capture SOP that produces data fit for both visual reconstruction and metric geometry.
2. Produce a photorealistic 3D view and a separate, validated walkable/collision representation for each accepted scene.
3. Deliver an install-free desktop browser walkthrough with first-person WASD and mouse controls.
4. Let scene authors define and maintain named POIs and let visitors select them in the 3D scene or a companion list.
5. Compute and visibly guide a floor-constrained route to a selected POI while avoiding marked physical obstacles.
6. Make reconstruction, navigation readiness, and known coverage gaps visible and reviewable before publishing a scene.

### Initial success criteria (targets to confirm during the first validation cycle)

- A first-time visitor can load and explore a published pilot scene in a supported desktop browser without installing an application.
- In the agreed pilot capture, at least 95% of required camera poses register, all intended walkable areas have reviewed floor coverage, and no critical doorway/room transition is missing. Image-registration percentage is an input-quality signal, not proof of geometric correctness.
- A scene is not marked navigation-ready until its coordinate alignment, floor surfaces, walkable regions, obstacle set, POI anchors, and connectivity have passed author review.
- For a supported pilot scene, a reachable destination produces a route on the floor, with no route segment crossing a reviewed wall or obstacle; unreachable destinations are reported clearly.
- On the agreed reference desktop and network profile, the published pilot maintains at least 30 FPS during navigation and loads its initial walkthrough within 10 seconds at the 25 Mbps test profile. Record device, browser, scene size, and percentile methodology with results; revise targets after the pilot baseline.
- At least 8 of 10 representative test users can select a named room and follow the route to its destination without facilitator help.

## 4. Users and primary jobs

| User | Job to be done |
|---|---|
| Capture participant | Follow clear capture steps and know when coverage is complete. |
| Scene author / spatial operator | Inspect reconstruction quality, correct geometry and alignment, define POIs, mark obstacles, and publish only a usable scene. |
| Visitor | Open a shared scene, freely look and walk around, find a named destination, and follow a visible route. |
| Platform operator | Track processing, diagnose failed jobs, control asset access, and manage published scenes. |

## 5. Scope

### MVP (required)

- A versioned capture SOP and per-capture checklist, with support for a guided video or image-set input and optional sensor/plan inputs.
- Ingestion and preflight checks for file integrity, blur/sharpness, coverage, overlap, exposure consistency, and capture metadata; report warnings and actionable retake guidance.
- Reconstruction workflow that can reuse the existing COLMAP/3DGS tooling and yields a photorealistic visual asset plus metric geometry (mesh or equivalent) with a known shared coordinate frame.
- A browser scene viewer with first-person WASD movement, mouse look, pointer-lock release, accessible UI controls, and free exploration independent of route navigation.
- Reviewed walkable surfaces, collision/obstacle geometry, and connected navigation regions.
- POI authoring and display, including stable IDs, names, optional descriptions, and destination anchors/areas.
- Destination selection from a POI list and, where supported, direct selection from the 3D view.
- Obstacle-aware route computation, a visible floor-level route, destination marker, and active guidance that updates from user position.
- Scene readiness states, quality report, asset/manifest versioning, and publish/unpublish workflow.
- Responsive error states for missing assets, failed reconstruction, invalid geometry, and unreachable POIs.

### Later / optional

- Mobile AR navigation (bonus only; explicitly outside MVP acceptance).
- Automated room segmentation and POI suggestions, with human confirmation before publication.
- Multi-floor routing, elevators/stairs, outdoor-to-indoor transitions, author collaboration, analytics, and offline support.
- Native desktop/mobile clients or headset/VR support.

### Non-goals

- Treating a 3D Gaussian Splat as navigable collision geometry or as a substitute for a metrically validated surface model.
- Promising survey-grade measurement, BIM authoring, emergency egress certification, or safety-critical wayfinding.
- Requiring every participant to have LiDAR; video/image capture remains a valid path if the resulting geometry passes review.
- Shipping AR in the first release.

## 6. Product requirements

### Capture and SOP

**CAP-1.** Each capture session shall identify the site, operator, date/time, capture device/lens, sensor availability, units, coordinate reference, and any known restrictions. Obtain appropriate permission before recording occupied/private spaces.

**CAP-2.** The SOP shall require an initial room/space inventory and a rough floor plan or annotated route showing room names, entrances, thresholds, stairs/elevators where present, occlusions, and intended POIs. A plan is a scale/alignment aid, not a replacement for observed data.

**CAP-3.** The SOP shall prescribe a slow, continuous, overlapping capture trajectory: a perimeter pass at approximately standing eye height, additional high/low views where surfaces are occluded, coverage of floors/thresholds/doorways, and a connecting pass through each accessible transition. Capture both sides of each doorway (the existing project report recommends at least five frames on each side). Avoid abrupt turns, motion blur, moving people, reflective/glass surfaces where possible, and changing exposure/focus. Keep original files and metadata.

**CAP-4.** The pilot operating targets shall start from repository guidance—at least 70% forward overlap and 60% between adjacent passes, fixed exposure where supported, and sharp frames—and be tuned against real pilot outcomes. These are capture targets, not universal guarantees. The final SOP shall state per-device capture settings and retake criteria.

**CAP-5.** Accept a single video, a set of images, or a supported sensor/scan package. The ingestion process shall preserve source media, extract frames with timestamps/metadata, de-duplicate near-identical frames, and produce a traceable processing record. Manual room stitching is supported through explicit room assets and reviewed coordinate alignment; it must not silently join disconnected spaces.

**CAP-6.** Preflight shall report missing transition coverage, insufficient image overlap, blurred/underexposed frames, exposure shifts, and unresolved scale/orientation. An operator can accept a documented warning or request a recapture.

### Reconstruction and scene readiness

**REC-1.** Processing shall create a photorealistic visual layer (existing 3DGS/SOG path may be retained) and a separate metric geometry layer suitable for collision, floor projection, and navigation. Geometry sources may include sensor depth, photogrammetry/mesh reconstruction, CAD/BIM/floor plan input, or reviewed manual corrections.

**REC-2.** Visual and geometric layers shall share a documented coordinate system, scale, up axis, and transform. A scene author shall be able to inspect alignment at landmarks before scene approval.

**REC-3.** Scene quality shall distinguish measured facts (e.g., registered images, source resolution, mesh coverage, job status) from heuristic scores. A scene cannot become navigation-ready based only on a reconstruction score or image-registration rate.

**REC-4.** Navigation readiness requires reviewed floor surfaces, walkable-area boundaries, openings/connectivity, obstacle/collision geometry, coordinate alignment, POIs, and route reachability. Keep an audit trail for author edits and scene versions.

### Browser walkthrough and navigation

**NAV-1.** The viewer shall run in a current supported desktop browser without a native client install. Web delivery includes downloading browser assets and may require WebGPU or WebGL fallback support; supported browsers and minimum hardware shall be published.

**NAV-2.** Users shall freely explore with WASD/arrow movement and mouse look, at a fixed configured eye height, constrained by walkable surfaces and collision geometry. Space/fly movement is disabled in visitor mode. Pointer lock shall start only after a user gesture and be released with Escape; provide a non-pointer-lock alternative where practical.

**NAV-3.** Free exploration shall remain available when no destination is selected. Starting, cancelling, or completing a route shall not trap the user in route-following mode.

**NAV-4.** POIs shall be selectable through an accessible list/search and a spatial marker/room zone. Selection displays the POI name and optional description. Labels shall remain legible and avoid excessive overlap.

**NAV-5.** Route planning shall operate on reviewed floor navigation geometry or an equivalent graph, use a documented pathfinding algorithm (e.g., A* on a navigation mesh/waypoint graph), and respect walls, blocked regions, obstacles, doorway connectivity, and destination approach zones. Define the cost model (distance by default; accessibility constraints where supplied).

**NAV-6.** A route shall render as a floor-conforming line/sequence of markers with a destination indicator and optional next-direction prompts. Replan when the user deviates beyond a configurable threshold, or clearly offer “recalculate route.” Do not fake a route with a camera rail.

**NAV-7.** If the origin and POI are disconnected or the floor geometry is incomplete, explain that no validated route is available and retain free exploration. Never draw a route through an unreviewed gap.

**NAV-8.** MVP routes are informational indoor guidance, not certified accessible routes. Where accessibility data (steps, slope, width, lift availability) is unavailable, disclose this and do not label the route accessible.

### POI and scene authoring

**POI-1.** Authors shall create, rename, move, disable, and delete POIs; assign a stable ID, display name, optional description/category, anchor/area, and optional destination approach point.

**POI-2.** A POI destination must snap to or be validated against a walkable region. Authoring UI shall show a warning for invalid, unreachable, or unconnected POIs.

**POI-3.** Published POI metadata and navigation geometry shall be versioned with the scene so routes remain reproducible and caches can be invalidated correctly.

## 7. Proposed system design and engine decision

### Recommendation: retain the web product and add a metric navigation layer

Use the existing React/Vite application as the browser shell and retain PlayCanvas for the existing 3DGS/SOG viewer and LOD delivery. Add a metric mesh/floor/navigation layer and scene-authoring data alongside the splat. Implement first-person collision and route visualization in the browser engine, using a navigation mesh or explicit walkable graph generated from reviewed geometry. Keep reconstruction and job orchestration in the existing Python pipeline initially; add a backend/API only for the workflows that need persistent upload, job state, access control, and asset publication.

**Do not make Unity the default implementation solely to obtain “precision.”** A game engine does not make an inaccurate reconstruction accurate. The source of path precision is calibrated/validated geometry, explicit obstacles, shared coordinates, and QA. Unity WebGL/Web builds could provide physics, navigation tools, and authoring workflows, but would introduce a second renderer/runtime, integration work for the current SOG/3DGS assets, browser payload/memory risk, and duplicated product UI. A Unity build must also be proven to meet the zero-install desktop/browser requirement.

Before committing the navigation engine, run a time-boxed technical spike (one representative room, one doorway, several furniture obstacles, and two POIs) comparing: (A) PlayCanvas/browser mesh navigation integrated with current splats, and (B) Unity WebGL embedded in the current shell with equivalent geometry and route behavior. Measure route correctness against reviewed floor truth, frame rate, first-load time, memory, asset size, browser compatibility, and authoring effort. Select Unity only if it materially improves validated navigation/authoring and meets the same browser and integration gates. The spike is a decision gate, not permission to replace the current app in advance.

### Logical architecture

1. **Capture inputs:** raw video/images, optional depth/LiDAR, floor plan/CAD, capture manifest.
2. **Preflight and reconstruction:** current capture-splat/COLMAP/gsplat workflows retained and adapted; geometry extraction/import and alignment added.
3. **Review and authoring:** human QA for geometry, floors, obstacles, connectivity, and POIs; scene cannot publish as navigable before sign-off.
4. **Scene package:** versioned manifest, SOG/3DGS visual asset(s), metric mesh, collision/navigation data, POIs, transforms, provenance, and quality report.
5. **Delivery:** React/Vite browser shell; PlayCanvas visual rendering; navigation/collision runtime; route and POI interface; CDN/object storage for large assets.

The frontend manifest should evolve from the current scene manifest to reference versioned geometry, nav data, coordinate frame, POIs, and readiness status. The API is a delivery/orchestration boundary, not a reason to rewrite working offline pipeline utilities.

## 8. Existing project disposition

| Existing project area | Decision | Rationale / next action |
|---|---|---|
| `frontend/namma-space` React/Vite shell and PlayCanvas viewer | Keep and extend | Already delivers install-free browser viewing, WebGPU/WebGL selection, scene loading, and splat rendering. Add reviewed geometry, POI UI, collision, and routes. |
| `frontend/namma-space/src/controls/FirstPersonControls.ts` | Keep as a starting point; revise | Existing WASD/mouse movement and camera bounds do not establish floor following or obstacle collision. Replace bounds-only movement behavior with validated walkable/collision queries. |
| Scene manifests, quality analysis, scene registry | Keep and extend | Useful foundation. Add coordinate frame, geometry/nav assets, POI schema, readiness gates, provenance, and separate geometry quality metrics. |
| `pipeline-capture-splat` capture, COLMAP, training, and reports | Keep selectively and harden | Reuse proven capture preparation and reconstruction where their input/output contracts fit. Turn capture guidance into a versioned SOP; add geometry production/import and QA. |
| `pipeline/filter` and surface-mesh extraction tools | Keep selectively | Evaluate mesh extraction/refinement as candidate geometry tooling; validate scale, watertightness/coverage, floor quality, and obstacle fidelity before using it for navigation. |
| `pipeline/tools/tool-splat-transform` | Keep as asset tooling | Retain useful conversion/compression/LOD tooling for visual delivery; not a navigation or collision system. |
| `backend/api` placeholder | Build only needed service capabilities | Add upload/session, processing-job status, artifact/manifest delivery, auth/access policy, and publish lifecycle after workflow/API contracts are agreed. |
| `research/` literature tracker | Keep as internal reference | It is not a runtime dependency. |
| `archive/`, `scratch/`, duplicate experimental assets and reports | Audit; do not include in the production runtime by default | Preserve source/history until dependencies and provenance are checked. Remove or relocate only after a separate approved cleanup plan. |
| Unity | Evaluate in a bounded spike; not yet a committed migration | Compare against extending the current browser stack using measurable product gates. |

## 9. Core data contracts (draft)

Each published scene needs stable IDs and versioned records for:

- `Scene`: id, version, name, status, units, up-axis, origin/coordinate frame, bounds, visual asset refs, geometry asset refs, capture/reconstruction provenance, quality report.
- `Geometry`: mesh reference, transform into scene coordinates, scale/units, geometry source, review status, coverage/known gaps.
- `Navigation`: navmesh or graph reference, generation parameters/version, walkable areas, obstacle/blocker data, connected regions, review status.
- `POI`: id, name, description/category, anchor or polygon/volume, destination approach point, associated room/zone, enabled state.
- `Capture`: source media refs, device/lens/sensor metadata, timestamps, route/pass labels, SOP version, operator checklist, preflight report.

All transforms shall be explicit, unit-tested at contract boundaries, and visualized during author review. The final schema and API transport format are a technical design deliverable after PRD approval.

## 10. Iterative delivery plan and review gates

The team shall refine the product in short, reviewable cycles. Each cycle starts with a stated assumption and a testable question; ends with a demonstrable artifact, evidence, decisions, and updated risks. Keep a decision log and do not promote heuristic output to validated product behavior without a human review gate.

| Phase | Deliverable | Exit gate |
|---|---|---|
| 0. Product and capture discovery | Confirm pilot building/room, users, privacy/access constraints, device mix, coordinate truth source, and reference test hardware; publish SOP v1. | Stakeholders approve the pilot and capture checklist. |
| 1. Geometry/navigation spike | Reconstruct or import one representative scene; align visual and metric geometry; compare browser-native and Unity WebGL options using the same benchmark. | Demonstrated floor-constrained movement and obstacle-aware routes; documented performance and engine decision. |
| 2. Capture-to-scene vertical slice | Capture upload/preflight, processing handoff, scene package, human geometry review, manifest update. | One new capture can become a reviewed navigation-ready scene through the documented workflow. |
| 3. Walkthrough MVP | First-person controls, POIs, route display/replanning, unreachable handling, scene quality/readiness UI. | Acceptance criteria in Section 11 pass for the pilot scene. |
| 4. Pilot and hardening | Usability sessions, browser/device matrix, performance/asset budgets, failure recovery, access controls, operational documentation. | Product owner accepts pilot evidence and release checklist. |
| 5. Optional AR discovery | Evaluate mobile tracking, localization, safety, and platform constraints. | Separate AR PRD and approval; not part of desktop MVP completion. |

## 11. Acceptance criteria for the MVP

1. SOP v1 is available to capture participants and defines inputs, repeatable trajectories, coverage checks, retake criteria, metadata, and handoff format.
2. A pilot capture can be processed into both the 3DGS visual layer and a metric geometry/navigation layer with traceable shared coordinates.
3. An author can inspect and approve floors, obstacle geometry, transitions, POIs, and route connectivity; unresolved critical gaps prevent navigation-ready publication.
4. A visitor opens the shared scene in a supported desktop browser without installing a client, freely walks using WASD and mouse, and can cancel a route at any time.
5. Selecting each test POI reveals its name; reachable POIs receive a route that stays on reviewed walkable geometry and avoids reviewed obstacles.
6. A disconnected or invalid POI produces a clear “route unavailable” state and no misleading route line.
7. The viewer remains usable while idle or freely explored with no active navigation, and the visual scene does not need a route to render.
8. Performance, load-time, browser, and user-task targets in Section 3 are measured on a named pilot scene and reference environment; deviations are documented and accepted before release.

## 12. Risks, assumptions, and decisions to close during refinement

| Risk / assumption | Mitigation / decision |
|---|---|
| 3DGS appearance is view-dependent and not a reliable collision surface. | Maintain separate metric geometry, and show alignment/coverage QA. |
| Monocular/video reconstruction can have scale ambiguity, holes, or drift. | Use sensor/known dimensions/floor plan controls where available; require scale and landmark review. |
| The current project's very low default camera eye height and transformed demo data may be demo-specific. | Normalize units and human-scale navigation per scene; validate with measured pilot landmarks. |
| Sparse or incorrect obstacle geometry can route through furniture/walls. | Human review, route QA cases, explicit blockers, and visible “navigation unavailable” states. |
| Unity could increase browser load and complicate current splat rendering. | Gate migration on the comparative prototype and integration measurements. |
| Fully automatic processing may not be reliable across arbitrary buildings. | Start with supported indoor capture conditions and human-in-the-loop geometry QA; expand after evidence. |
| Web GPU availability varies by browser/device. | Publish support matrix, use tested fallback rendering where possible, and define minimum desktop hardware. |
| Floor plans, imagery, and occupancy can contain sensitive information. | Define consent, retention, access, and deletion policies as a launch prerequisite for real customer captures. |

### Assumptions to validate

- Initial product is desktop-first, browser-delivered, and supports indoor, single-floor scenes for the MVP.
- Participants can supply a phone/camera video or image set; sensor scans and plans improve quality but are not mandatory.
- Human review of navigation geometry is acceptable for the pilot and required before publishing routes.
- The current NammaSpace repository and its existing demo assets are intended to be the starting point.

## 13. Out of scope for this approval

This document sets product requirements and the proposed implementation direction. It does not authorize or perform a Unity migration, delete/archive repository content, select a final third-party navigation package, define final API schemas, build the capture SOP application, or implement the product. Those decisions follow PRD approval and the stated discovery/spike gates.

