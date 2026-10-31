"""Contract checks for the complete catalog TOML load workload."""

from __future__ import annotations

import tomllib
import unittest

from benchmarks.workloads import catalog_toml
from benchmarks.workloads.registry import BY_NAME


class CatalogTomlWorkloadTests(unittest.TestCase):
    def test_complete_load_bytes_and_units(self) -> None:
        self.assertEqual(BY_NAME["catalog_toml_load"].module, "catalog_toml")
        first = catalog_toml.catalog_toml_load(1)
        repeated = catalog_toml.catalog_toml_load(2)
        self.assertEqual(first["input_digest"], catalog_toml._EXPECTED_INPUT)
        self.assertEqual(first["digest"], catalog_toml._EXPECTED_OUTPUT)
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(repeated["operation_count"], 2)
        self.assertEqual(repeated["digest"], first["digest"])
        self.assertEqual((first["records_per_operation"], first["bytes_per_operation"]),
                         (512, 349799))

    def test_document_covers_every_toml_value_kind(self) -> None:
        tables = tomllib.loads(catalog_toml.catalog_document())
        entry = tables["entry"][1]
        self.assertEqual(len({record["identifier"] for record in tables["entry"]}), 512)
        kinds = {type(value).__name__ for value in entry.values()}
        self.assertLessEqual(
            {"str", "int", "float", "bool", "datetime", "date", "list", "dict"}, kinds)
        self.assertTrue(any("🐍" in record["body"] for record in tables["entry"]))


if __name__ == "__main__":
    unittest.main()
