"""Dimension-driven provisional room wireframe generation.

This creates an explicit rectangular draft from user-entered dimensions. It
does not infer geometry from photographs and is always marked for human review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from .constraints import DistanceConstraint, Edge, Node, evaluate_wireframe


def build_dimensioned_room_draft(
    *,
    scene_id: str,
    length: float,
    width: float,
    height: float,
    units: str,
    openings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a conservative rectangular wireframe from supplied metric inputs."""
    if units not in {"m", "ft"}:
        raise ValueError("Dimensioned room drafts support metres or feet")
    for label, value in (("length", length), ("width", width), ("height", height)):
        if not isfinite(value) or value <= 0:
            raise ValueError(f"Room {label} must be a positive finite value")

    half_length, half_width = length / 2, width / 2
    floor_positions = [
        (-half_length, 0.0, -half_width),
        (half_length, 0.0, -half_width),
        (half_length, 0.0, half_width),
        (-half_length, 0.0, half_width),
    ]
    nodes: list[Node] = []
    for index, (x, y, z) in enumerate(floor_positions):
        nodes.append(Node(f"floor-{index + 1}", (x, y, z), "inferred"))
        nodes.append(Node(f"ceiling-{index + 1}", (x, height, z), "inferred"))

    edges: list[Edge] = []
    constraints: list[DistanceConstraint] = []
    for index in range(4):
        next_index = (index + 1) % 4
        floor_a, floor_b = f"floor-{index + 1}", f"floor-{next_index + 1}"
        top_a, top_b = f"ceiling-{index + 1}", f"ceiling-{next_index + 1}"
        side_length = length if index in {0, 2} else width
        edges.extend([
            Edge(f"floor-edge-{index + 1}", floor_a, floor_b, "wall", side_length),
            Edge(f"ceiling-edge-{index + 1}", top_a, top_b, "wall", side_length),
            Edge(f"vertical-edge-{index + 1}", floor_a, top_a, "vertical", height),
        ])
        constraints.extend([
            DistanceConstraint(f"room-side-{index + 1}", floor_a, floor_b, side_length, 0.0, "user_dimension"),
            DistanceConstraint(f"ceiling-height-{index + 1}", floor_a, top_a, height, 0.0, "user_dimension"),
        ])

    opening_records = []
    unresolved_openings = []
    sides = [
        ("side1", floor_positions[0], floor_positions[1], length),
        ("side2", floor_positions[1], floor_positions[2], width),
        ("side3", floor_positions[2], floor_positions[3], length),
        ("side4", floor_positions[3], floor_positions[0], width),
    ]
    for opening in openings or []:
        side_data = next((item for item in sides if item[0] == opening.get("side")), None)
        opening_width, opening_height, offset = opening.get("width"), opening.get("height"), opening.get("offset_from_corner")
        if side_data is None or not all(isinstance(value, (int, float)) and isfinite(value) for value in (opening_width, opening_height, offset)):
            unresolved_openings.append({"id": opening.get("id"), "label": opening.get("label"), "reason": "missing_wall_or_dimensions_or_offset"})
            continue
        side, start, end, side_length = side_data
        if opening_width <= 0 or opening_height <= 0 or offset < 0 or offset + opening_width > side_length or opening_height > height:
            unresolved_openings.append({"id": opening.get("id"), "label": opening.get("label"), "reason": "opening_outside_room_bounds"})
            continue
        direction = tuple((end[axis] - start[axis]) / side_length for axis in range(3))
        lower_a = tuple(start[axis] + direction[axis] * offset for axis in range(3))
        lower_b = tuple(start[axis] + direction[axis] * (offset + opening_width) for axis in range(3))
        frame_nodes = {
            "a0": (lower_a[0], 0.0, lower_a[2]), "b0": (lower_b[0], 0.0, lower_b[2]),
            "a1": (lower_a[0], opening_height, lower_a[2]), "b1": (lower_b[0], opening_height, lower_b[2]),
        }
        prefix = f"opening-{opening.get('id', len(opening_records) + 1)}"
        for suffix, position in frame_nodes.items():
            nodes.append(Node(f"{prefix}-{suffix}", position, "measured"))
        edges.extend([
            Edge(f"{prefix}-bottom", f"{prefix}-a0", f"{prefix}-b0", "opening", opening_width),
            Edge(f"{prefix}-top", f"{prefix}-a1", f"{prefix}-b1", "opening", opening_width),
            Edge(f"{prefix}-left", f"{prefix}-a0", f"{prefix}-a1", "opening", opening_height),
            Edge(f"{prefix}-right", f"{prefix}-b0", f"{prefix}-b1", "opening", opening_height),
        ])
        opening_records.append({"id": opening.get("id"), "label": opening.get("label"), "kind": opening.get("kind"), "side": side,
                                "nodeIds": [f"{prefix}-{suffix}" for suffix in frame_nodes], "source": "user_dimensions"})
        side_index = next(index for index, side_item in enumerate(sides) if side_item[0] == side)
        edges.append(Edge(f"{prefix}-wall-link", f"floor-{side_index + 1}", f"{prefix}-a0", "room_link"))

    report = evaluate_wireframe(nodes, edges, constraints)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schemaVersion": "1.0.0",
        "sceneId": scene_id,
        "revision": 1,
        "units": units,
        "coordinateFrame": {"upAxis": "Y", "origin": [0.0, 0.0, 0.0], "handedness": "right"},
        "nodes": [{"id": node.id, "position": list(node.position), "source": node.source, "observationCount": 0,
                   "sigma": None, "locked": False, "evidenceIds": []} for node in nodes],
        "edges": [{"id": edge.id, "start": edge.start, "end": edge.end, "kind": edge.kind,
                   "expectedLength": edge.expected_length, "roomId": scene_id} for edge in edges],
        "constraints": [{"id": constraint.id, "kind": "distance", "nodeIds": [constraint.start, constraint.end],
                         "target": constraint.target, "tolerance": constraint.tolerance, "residual": 0.0,
                         "source": "assumption", "weight": constraint.weight, "status": "satisfied", "evidenceIds": []}
                        for constraint in constraints],
        "planes": [],
        "metrics": {"computedAt": now, "constraintRmsResidual": report["constraint_rms_residual"],
                    "anchorRmsResidual": None, "cornerRmsResidual": None, "constraintsSatisfied": report["constraints_satisfied"],
                    "constraintsFailed": report["constraints_failed"], "connectedComponents": report["connected_components"],
                    "coverage": 0.0, "toleranceProfileId": "dimension_driven_preview.v1", "readiness": "warning",
                    "provisionalGeometry": "rectangular_assumption", "unresolvedOpenings": unresolved_openings},
        "reviewState": "needs_review",
        "parentRevision": None,
        "provenance": {"engineVersion": "dimensioned-room-draft.v1", "createdBy": None,
                       "source": "user_supplied_dimensions", "photogrammetryUsed": False,
                       "openings": opening_records},
    }
