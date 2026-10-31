"""Evaluate wireframe topology and metric constraint residuals.

For weighted candidate adjustment, see :mod:`solver`. Neither module infers
candidate room geometry or camera poses from images.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import sqrt
from typing import Literal

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Node:
    id: str
    position: Vec3
    source: Literal["observed", "measured", "inferred", "authored"]
    sigma: float | None = None
    locked: bool = False


@dataclass(frozen=True)
class Edge:
    id: str
    start: str
    end: str
    kind: Literal["wall", "opening", "vertical", "room_link"] = "wall"
    expected_length: float | None = None


@dataclass(frozen=True)
class DistanceConstraint:
    id: str
    start: str
    end: str
    target: float
    tolerance: float
    source: str
    weight: float = 1.0


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _components(node_ids: set[str], adjacency: dict[str, set[str]]) -> list[list[str]]:
    remaining = set(node_ids)
    result: list[list[str]] = []
    while remaining:
        root = remaining.pop()
        component = [root]
        queue = deque([root])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current] & remaining:
                remaining.remove(neighbor)
                component.append(neighbor)
                queue.append(neighbor)
        result.append(sorted(component))
    return sorted(result, key=lambda component: (-len(component), component[0]))


def evaluate_wireframe(
    nodes: list[Node],
    edges: list[Edge],
    constraints: list[DistanceConstraint],
) -> dict:
    """Return deterministic topology and metric diagnostics for a candidate graph."""

    node_by_id = {node.id: node for node in nodes}
    duplicate_nodes = len(node_by_id) != len(nodes)
    adjacency: dict[str, set[str]] = defaultdict(set)
    degree = {node_id: 0 for node_id in node_by_id}
    edge_results = []
    edge_errors: list[float] = []
    invalid_references: list[dict[str, str]] = []

    for edge in edges:
        if edge.start not in node_by_id or edge.end not in node_by_id:
            invalid_references.append({"id": edge.id, "kind": "edge", "reason": "missing_node"})
            continue
        adjacency[edge.start].add(edge.end)
        adjacency[edge.end].add(edge.start)
        degree[edge.start] += 1
        degree[edge.end] += 1
        length = _distance(node_by_id[edge.start].position, node_by_id[edge.end].position)
        error = None if edge.expected_length is None else length - edge.expected_length
        if error is not None:
            edge_errors.append(error)
        edge_results.append({
            "id": edge.id,
            "length": length,
            "expected_length": edge.expected_length,
            "residual": error,
        })

    constraint_results = []
    constraint_errors: list[float] = []
    for constraint in constraints:
        if constraint.start not in node_by_id or constraint.end not in node_by_id:
            invalid_references.append({"id": constraint.id, "kind": "distance_constraint", "reason": "missing_node"})
            continue
        actual = _distance(node_by_id[constraint.start].position, node_by_id[constraint.end].position)
        residual = actual - constraint.target
        satisfied = abs(residual) <= constraint.tolerance
        constraint_errors.append(residual)
        constraint_results.append({
            "id": constraint.id,
            "source": constraint.source,
            "start": constraint.start,
            "end": constraint.end,
            "target": constraint.target,
            "actual": actual,
            "residual": residual,
            "tolerance": constraint.tolerance,
            "weight": constraint.weight,
            "satisfied": satisfied,
        })

    components = _components(set(node_by_id), adjacency)
    isolated = sorted(node_id for node_id, node_degree in degree.items() if node_degree == 0)

    def rms(values: list[float]) -> float | None:
        return None if not values else sqrt(sum(value * value for value in values) / len(values))

    satisfied_count = sum(result["satisfied"] for result in constraint_results)
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "constraint_count": len(constraints),
        "duplicate_node_ids": duplicate_nodes,
        "connected_components": len(components),
        "components": components,
        "isolated_nodes": isolated,
        "node_degrees": degree,
        "invalid_references": invalid_references,
        "edge_length_rms_residual": rms(edge_errors),
        "constraint_rms_residual": rms(constraint_errors),
        "constraints_satisfied": satisfied_count,
        "constraints_failed": len(constraint_results) - satisfied_count,
        "edge_metrics": edge_results,
        "constraint_metrics": constraint_results,
        "graph_topology_connected": (
            bool(nodes)
            and not duplicate_nodes
            and len(components) == 1
            and not isolated
            and not invalid_references
        ),
    }
