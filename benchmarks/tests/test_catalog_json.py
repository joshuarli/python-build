"""Contract checks for the complete catalog JSON export workload."""

from __future__ import annotations

import json
import unittest

from benchmarks.workloads import catalog_json
from benchmarks.workloads.registry import BY_NAME


class CatalogJsonWorkloadTests(unittest.TestCase):
    def test_complete_export_bytes_and_units(self) -> None:
        self.assertEqual(BY_NAME["catalog_json_export"].module, "catalog_json")
        first = catalog_json.catalog_json_export(1)
        repeated = catalog_json.catalog_json_export(2)
        self.assertEqual(first["input_digest"], catalog_json._EXPECTED_INPUT)
        self.assertEqual(first["digest"], catalog_json._EXPECTED_OUTPUT)
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(repeated["operation_count"], 2)
        self.assertEqual(repeated["digest"], first["digest"])
        self.assertEqual((first["records_per_operation"], first["bytes_per_operation"]),
                         (512, 259349))

    def test_public_export_contains_every_distinct_record(self) -> None:
        CatalogEntry, EntryKind, _, export_json = catalog_json._catalog_modules()
        entries = catalog_json._entries(CatalogEntry, EntryKind)
        document = json.loads(export_json(entries))
        self.assertEqual(len(document), 512)
        self.assertEqual(len({record["id"] for record in document}), 512)
        self.assertEqual({record["kind"] for record in document},
                         {kind.value for kind in EntryKind})
        self.assertEqual(document[0]["id"], "item-0000")
        self.assertEqual(document[-1]["id"], "item-0511")
        self.assertTrue(any("🐍" in record["body"] for record in document))


if __name__ == "__main__":
    unittest.main()
