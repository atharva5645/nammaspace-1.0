import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class VersionedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contract_dir = ROOT / "spatial-engine" / "contracts"
        cls.job = json.loads((contract_dir / "job.schema.json").read_text(encoding="utf-8"))
        cls.result = json.loads((contract_dir / "job-result.schema.json").read_text(encoding="utf-8"))
        cls.wireframe = json.loads((contract_dir / "wireframe.schema.json").read_text(encoding="utf-8"))

    def test_job_contract_carries_capture_provenance_and_evidence(self):
        project = self.job["properties"]["input"]["properties"]["project"]
        evidence = self.job["properties"]["input"]["properties"]["evidence"]["items"]

        self.assertEqual(self.job["properties"]["contract_version"]["const"], "spatial-job.v1")
        self.assertIn("anchor_view_side", project["properties"])
        self.assertIn("anchor_start_pick", project["properties"])
        self.assertIn("sensor_data", evidence["properties"]["category"]["enum"])
        self.assertTrue(self.job["additionalProperties"] is False)

    def test_result_and_wireframe_contracts_require_reviewable_artifacts(self):
        self.assertIn("artifacts", self.result["required"])
        self.assertIn("reviewState", self.wireframe["required"])
        self.assertIn("metrics", self.wireframe["required"])
        self.assertIn("constraints", self.wireframe["required"])
        self.assertIn("inputDimensions", self.wireframe["properties"])
        self.assertIn("inputOpenings", self.wireframe["properties"])
        self.assertEqual(self.wireframe["properties"]["revision"]["minimum"], 0)


if __name__ == "__main__":
    unittest.main()
