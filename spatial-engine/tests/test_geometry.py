import sys
import unittest
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from geometry.constraints import DistanceConstraint, Edge, Node, evaluate_wireframe
from geometry.room_draft import build_dimensioned_room_draft
from geometry.solver import solve_wireframe_constraints


class WireframeMetricTests(unittest.TestCase):
    def test_evaluator_reports_exact_edge_and_constraint_residuals(self):
        nodes = [
            Node("a", (0.0, 0.0, 0.0), "measured", locked=True),
            Node("b", (3.0, 0.0, 0.0), "measured"),
        ]
        edges = [Edge("ab", "a", "b", expected_length=2.5)]
        constraints = [DistanceConstraint("anchor", "a", "b", 2.0, 0.01, "tape")]

        report = evaluate_wireframe(nodes, edges, constraints)

        self.assertEqual(report["node_count"], 2)
        self.assertEqual(report["edge_count"], 1)
        self.assertEqual(report["connected_components"], 1)
        self.assertAlmostEqual(report["edge_length_rms_residual"], 0.5)
        self.assertAlmostEqual(report["constraint_rms_residual"], 1.0)
        self.assertEqual(report["constraints_failed"], 1)

    def test_evaluator_flags_missing_nodes_and_disconnected_graph(self):
        nodes = [Node("a", (0.0, 0.0, 0.0), "observed"), Node("b", (1.0, 0.0, 0.0), "observed")]
        report = evaluate_wireframe(nodes, [Edge("missing", "a", "absent")], [])

        self.assertFalse(report["graph_topology_connected"])
        self.assertEqual(report["connected_components"], 2)
        self.assertEqual(report["invalid_references"], [{"id": "missing", "kind": "edge", "reason": "missing_node"}])

    def test_solver_reduces_anchor_residual_without_moving_locked_node(self):
        nodes = [
            Node("a", (0.0, 0.0, 0.0), "measured", locked=True),
            Node("b", (2.0, 0.0, 0.0), "inferred"),
        ]
        constraint = DistanceConstraint("anchor", "a", "b", 1.0, 0.01, "tape")

        result = solve_wireframe_constraints(nodes, [], [constraint])

        self.assertLess(result.final_weighted_rms, result.initial_weighted_rms)
        self.assertAlmostEqual(result.nodes[0].position[0], 0.0)
        self.assertAlmostEqual(result.nodes[1].position[0], 1.0, places=4)
        self.assertTrue(result.potentially_underconstrained)

    def test_dimensioned_room_draft_is_explicitly_provisional_and_connected(self):
        draft = build_dimensioned_room_draft(
            scene_id="project-room-1", length=4.2, width=3.1, height=2.6, units="m",
            openings=[{"id": "door-1", "label": "Main door", "kind": "door", "side": "side1",
                       "width": 0.9, "height": 2.0, "offset_from_corner": 0.2}],
        )

        self.assertEqual(draft["reviewState"], "needs_review")
        self.assertFalse(draft["provenance"]["photogrammetryUsed"])
        self.assertEqual(draft["metrics"]["coverage"], 0.0)
        self.assertEqual(draft["metrics"]["provisionalGeometry"], "rectangular_assumption")
        self.assertEqual(draft["metrics"]["connectedComponents"], 1)
        self.assertEqual(draft["metrics"]["constraintsFailed"], 0)
        self.assertEqual(len(draft["provenance"]["openings"]), 1)

    def test_dimensioned_room_draft_does_not_place_openings_outside_the_room(self):
        draft = build_dimensioned_room_draft(
            scene_id="project-room-1", length=4.2, width=3.1, height=2.6, units="m",
            openings=[{"id": "door-1", "label": "Main door", "kind": "door", "side": "side1",
                       "width": 1.0, "height": 2.0, "offset_from_corner": 4.0}],
        )

        self.assertEqual(draft["provenance"]["openings"], [])
        self.assertEqual(draft["metrics"]["unresolvedOpenings"][0]["reason"], "opening_outside_room_bounds")


if __name__ == "__main__":
    unittest.main()
