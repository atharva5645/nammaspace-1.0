import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import database, main
from app.auth import Identity, current_identity
from app.settings import Settings


class ProjectWorkspaceApiTests(unittest.TestCase):
    def test_saved_project_can_be_reopened_and_is_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = Settings(database_path=root / "capture.sqlite3", storage_root=root / "objects")
            identity = Identity(tenant_id="tenant-a", user_id="user-a")
            main.app.dependency_overrides[current_identity] = lambda: identity
            try:
                with patch.object(database, "get_settings", return_value=settings), TestClient(main.app) as client:
                    response = client.post("/v1/projects", json={
                        "project_name": "Test home", "room_name": "Living room", "units": "m", "known_distance": 2.4,
                        "anchor_name": "Door width", "anchor_start_label": "Left jamb", "anchor_end_label": "Right jamb",
                        "anchor_start_pick": {"image_filename": "side-one.jpg", "x_normalized": 0.2, "y_normalized": 0.4},
                        "anchor_end_pick": {"image_filename": "side-one.jpg", "x_normalized": 0.8, "y_normalized": 0.4},
                        "room_length": 4.2, "room_width": 3.1, "ceiling_height": 2.6, "openings": [],
                        "sop_acknowledgments": ["overlap", "corners_openings", "steady_lighting"],
                    })
                    self.assertEqual(response.status_code, 201, response.text)
                    project_id = response.json()["project_id"]
                    listed = client.get("/v1/projects")
                    self.assertEqual(listed.status_code, 200)
                    self.assertEqual(listed.json()[0]["project_id"], project_id)
                    workspace = client.get(f"/v1/projects/{project_id}")
                    self.assertEqual(workspace.status_code, 200, workspace.text)
                    self.assertEqual(workspace.json()["anchor_start_pick"]["x_normalized"], 0.2)
                    self.assertEqual(workspace.json()["room_length"], 4.2)
                    self.assertEqual(workspace.json()["uploads"], [])
                    draft = client.get(f"/v1/projects/{project_id}/wireframe-draft")
                    self.assertEqual(draft.status_code, 200, draft.text)
                    self.assertEqual(draft.json()["reviewState"], "needs_review")
                    self.assertFalse(draft.json()["provenance"]["photogrammetryUsed"])
                    self.assertEqual(draft.json()["revision"], 0)
                    saved = client.post(f"/v1/projects/{project_id}/wireframe-revisions", json={
                        "length": 4.2, "width": 3.1, "height": 2.6,
                        "openings": [{"id": "door-main", "label": "Entry door", "kind": "door", "side": "side1", "width": 0.9, "height": 2.1, "offset_from_corner": 0.5}],
                    })
                    self.assertEqual(saved.status_code, 201, saved.text)
                    self.assertEqual(saved.json()["revision"], 1)
                    self.assertIsNone(saved.json()["parentRevision"])
                    self.assertEqual(saved.json()["inputOpenings"][0]["label"], "Entry door")
                    self.assertIn("opening-door-main-bottom", [edge["id"] for edge in saved.json()["edges"]])
                    reopened_draft = client.get(f"/v1/projects/{project_id}/wireframe-draft")
                    self.assertEqual(reopened_draft.json()["revision"], 1)
                    self.assertEqual(reopened_draft.json()["nodes"], saved.json()["nodes"])
                    revised = client.post(f"/v1/projects/{project_id}/wireframe-revisions", json={"length": 5.0, "width": 3.2, "height": 2.7, "openings": []})
                    self.assertEqual(revised.status_code, 201, revised.text)
                    self.assertEqual(revised.json()["revision"], 2)
                    self.assertEqual(revised.json()["parentRevision"], 1)
                    self.assertEqual(revised.json()["inputDimensions"]["length"], 5.0)
                    self.assertEqual(client.get(f"/v1/projects/{project_id}/wireframe-draft").json()["revision"], 2)

                    main.app.dependency_overrides[current_identity] = lambda: Identity(tenant_id="tenant-b", user_id="user-b")
                    self.assertEqual(client.get("/v1/projects").json(), [])
                    self.assertEqual(client.get(f"/v1/projects/{project_id}").status_code, 404)
                    self.assertEqual(client.get(f"/v1/projects/{project_id}/wireframe-draft").status_code, 404)
                    self.assertEqual(client.post(f"/v1/projects/{project_id}/wireframe-revisions", json={"length": 4, "width": 3, "height": 2}).status_code, 404)
            finally:
                main.app.dependency_overrides.clear()

    def test_anchor_picks_must_be_both_marked_in_the_same_photo(self):
        from app.schemas import ProjectCreate
        from pydantic import ValidationError

        payload = {
            "project_name": "Test home", "known_distance": 2.4,
            "anchor_start_pick": {"image_filename": "a.jpg", "x_normalized": 0.2, "y_normalized": 0.4},
            "anchor_end_pick": {"image_filename": "b.jpg", "x_normalized": 0.8, "y_normalized": 0.4},
            "sop_acknowledgments": ["overlap", "corners_openings", "steady_lighting"],
        }
        with self.assertRaises(ValidationError):
            ProjectCreate.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
