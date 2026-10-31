"""Small-room weighted least-squares adjustment for candidate wireframe nodes.

This is a deterministic geometry adjustment step. It needs an upstream process
to provide candidate node coordinates; it does not derive room geometry from
images or remove rigid camera/scene ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite, sqrt
from typing import Literal

from .constraints import DistanceConstraint, Edge, Node, Vec3, evaluate_wireframe


@dataclass(frozen=True)
class SolverOptions:
    max_iterations: int = 100
    initial_damping: float = 1e-3
    finite_difference_step: float = 1e-6
    step_tolerance: float = 1e-8
    objective_tolerance: float = 1e-10
    max_damping: float = 1e12


@dataclass(frozen=True)
class SolverResult:
    nodes: list[Node]
    status: Literal["converged", "max_iterations", "stalled", "no_constraints", "no_free_nodes"]
    iterations: int
    initial_weighted_rms: float | None
    final_weighted_rms: float | None
    degrees_of_freedom: int
    equation_count: int
    potentially_underconstrained: bool
    has_hard_anchors: bool
    evaluation: dict


def _distance(a: Vec3, b: Vec3) -> float:
    return sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _weighted_rms(residuals: list[float], weights: list[float]) -> float | None:
    weight_sum = sum(weights)
    if not residuals or weight_sum <= 0:
        return None
    return sqrt(sum(weight * residual * residual for residual, weight in zip(residuals, weights)) / weight_sum)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Solve a dense system with partial pivoting; return None if singular."""
    size = len(vector)
    augmented = [matrix[row][:] + [vector[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-18:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for cell in range(column, size + 1):
            augmented[column][cell] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            for cell in range(column, size + 1):
                augmented[row][cell] -= factor * augmented[column][cell]
    return [augmented[row][size] for row in range(size)]


def _validate_inputs(nodes: list[Node], constraints: list[DistanceConstraint]) -> dict[str, Node]:
    node_by_id = {node.id: node for node in nodes}
    if len(node_by_id) != len(nodes):
        raise ValueError("Candidate contains duplicate node IDs")
    if not nodes:
        raise ValueError("At least one candidate node is required")
    for node in nodes:
        if len(node.position) != 3 or not all(isfinite(value) for value in node.position):
            raise ValueError(f"Node {node.id!r} has invalid coordinates")
        if node.sigma is not None and (not isfinite(node.sigma) or node.sigma < 0):
            raise ValueError(f"Node {node.id!r} has invalid positional sigma")
    for constraint in constraints:
        if constraint.start not in node_by_id or constraint.end not in node_by_id:
            raise ValueError(f"Constraint {constraint.id!r} references a missing node")
        if constraint.start == constraint.end:
            raise ValueError(f"Constraint {constraint.id!r} cannot measure a node against itself")
        if not isfinite(constraint.target) or constraint.target <= 0:
            raise ValueError(f"Constraint {constraint.id!r} must have a positive finite target")
        if not isfinite(constraint.tolerance) or constraint.tolerance < 0:
            raise ValueError(f"Constraint {constraint.id!r} has an invalid tolerance")
        if not isfinite(constraint.weight) or constraint.weight <= 0:
            raise ValueError(f"Constraint {constraint.id!r} must have a positive finite weight")
    return node_by_id


def solve_wireframe_constraints(
    nodes: list[Node],
    edges: list[Edge],
    constraints: list[DistanceConstraint],
    options: SolverOptions = SolverOptions(),
) -> SolverResult:
    """Adjust candidate coordinates to fit weighted measured distances.

    Constraint ``weight`` is treated as inverse variance in squared world units.
    ``tolerance`` is an acceptance band reported by the evaluator; it does not
    alter the optimizer objective. Nodes with ``locked=True`` or ``sigma=0``
    remain fixed. Nodes with positive ``sigma`` receive a Gaussian position
    prior around their input candidate location. All input coordinates and
    targets must use the same units.
    """
    if options.max_iterations < 1 or options.initial_damping <= 0 or options.finite_difference_step <= 0:
        raise ValueError("Solver options must use positive iteration and damping values")
    if (options.max_damping <= options.initial_damping or options.step_tolerance <= 0
            or options.objective_tolerance < 0 or not all(isfinite(value) for value in (
                options.initial_damping, options.finite_difference_step, options.step_tolerance,
                options.objective_tolerance, options.max_damping,
            ))):
        raise ValueError("Solver damping and convergence tolerances are invalid")
    node_by_id = _validate_inputs(nodes, constraints)
    initial_positions = {node.id: node.position for node in nodes}
    free_nodes = [node for node in nodes if not node.locked and node.sigma != 0]
    free_variables = [(node.id, axis) for node in free_nodes for axis in range(3)]
    dof = len(free_variables)
    distance_weights = [constraint.weight for constraint in constraints]
    initial_residuals = [
        _distance(node_by_id[c.start].position, node_by_id[c.end].position) - c.target
        for c in constraints
    ]
    initial_rms = _weighted_rms(initial_residuals, distance_weights)

    if not constraints:
        evaluation = evaluate_wireframe(nodes, edges, constraints)
        return SolverResult(nodes[:], "no_constraints", 0, None, None, dof, 0, dof > 0,
                            any(node.locked or node.sigma == 0 for node in nodes), evaluation)
    if not dof:
        evaluation = evaluate_wireframe(nodes, edges, constraints)
        return SolverResult(nodes[:], "no_free_nodes", 0, initial_rms, initial_rms, 0, len(constraints),
                            False, True, evaluation)

    prior_variables = [
        (node.id, axis, node.sigma)
        for node in free_nodes
        if node.sigma is not None and node.sigma > 0
        for axis in range(3)
    ]

    def positions_for(values: list[float]) -> dict[str, Vec3]:
        positions = dict(initial_positions)
        mutable = {node.id: list(node.position) for node in free_nodes}
        for index, (node_id, axis) in enumerate(free_variables):
            mutable[node_id][axis] = values[index]
        positions.update({node_id: (coords[0], coords[1], coords[2]) for node_id, coords in mutable.items()})
        return positions

    def residual_vector(values: list[float]) -> list[float]:
        positions = positions_for(values)
        residuals = [
            sqrt(constraint.weight)
            * (_distance(positions[constraint.start], positions[constraint.end]) - constraint.target)
            for constraint in constraints
        ]
        for node_id, axis, sigma in prior_variables:
            residuals.append((positions[node_id][axis] - initial_positions[node_id][axis]) / sigma)
        return residuals

    values = [initial_positions[node_id][axis] for node_id, axis in free_variables]
    residuals = residual_vector(values)
    objective = sum(value * value for value in residuals) / 2
    damping = options.initial_damping
    status: Literal["converged", "max_iterations", "stalled"] = "max_iterations"
    iterations = 0

    for iteration in range(1, options.max_iterations + 1):
        iterations = iteration
        columns: list[list[float]] = []
        for column_index, value in enumerate(values):
            step = options.finite_difference_step * max(1.0, abs(value))
            shifted = values[:]
            shifted[column_index] += step
            shifted_residuals = residual_vector(shifted)
            columns.append([(shifted_residuals[row] - residuals[row]) / step for row in range(len(residuals))])

        variable_count = len(values)
        normal = [[0.0] * variable_count for _ in range(variable_count)]
        gradient = [0.0] * variable_count
        for i in range(variable_count):
            gradient[i] = sum(columns[i][row] * residuals[row] for row in range(len(residuals)))
            for j in range(i, variable_count):
                value = sum(columns[i][row] * columns[j][row] for row in range(len(residuals)))
                normal[i][j] = value
                normal[j][i] = value

        damped = [row[:] for row in normal]
        for index in range(variable_count):
            damped[index][index] += damping * max(normal[index][index], 1.0)
        delta = _solve_linear_system(damped, [-value for value in gradient])
        if delta is None:
            damping *= 10
            if damping > options.max_damping:
                status = "stalled"
                break
            continue
        if max(abs(value) for value in delta) <= options.step_tolerance:
            status = "converged"
            break

        candidate_values = [value + change for value, change in zip(values, delta)]
        candidate_residuals = residual_vector(candidate_values)
        candidate_objective = sum(value * value for value in candidate_residuals) / 2
        if candidate_objective < objective:
            improvement = objective - candidate_objective
            values, residuals, objective = candidate_values, candidate_residuals, candidate_objective
            damping = max(damping / 3, 1e-12)
            if improvement <= options.objective_tolerance * max(1.0, objective):
                status = "converged"
                break
        else:
            damping *= 10
            if damping > options.max_damping:
                status = "stalled"
                break

    final_positions = positions_for(values)
    solved_nodes = [replace(node, position=final_positions[node.id]) for node in nodes]
    solved_by_id = {node.id: node for node in solved_nodes}
    final_residuals = [
        _distance(solved_by_id[c.start].position, solved_by_id[c.end].position) - c.target
        for c in constraints
    ]
    evaluation = evaluate_wireframe(solved_nodes, edges, constraints)
    constraint_components = {node_id for c in constraints for node_id in (c.start, c.end)}
    unconstrained_nodes = sorted(node.id for node in free_nodes if node.id not in constraint_components)
    evaluation["solver"] = {
        "algorithm": "damped_gauss_newton_finite_difference.v1",
        "status": status,
        "iterations": iterations,
        "initialWeightedRms": initial_rms,
        "finalWeightedRms": _weighted_rms(final_residuals, distance_weights),
        "degreesOfFreedom": dof,
        "equationCount": len(constraints) + len(prior_variables),
        "potentiallyUnderconstrained": len(constraints) + len(prior_variables) < dof,
        "unconstrainedNodes": unconstrained_nodes,
        "hasHardAnchors": any(node.locked or node.sigma == 0 for node in nodes),
        "translationAndRotationGaugePreservedFromCandidate": True,
    }
    return SolverResult(
        solved_nodes, status, iterations, initial_rms, _weighted_rms(final_residuals, distance_weights), dof,
        len(constraints) + len(prior_variables), len(constraints) + len(prior_variables) < dof,
        any(node.locked or node.sigma == 0 for node in nodes), evaluation,
    )
