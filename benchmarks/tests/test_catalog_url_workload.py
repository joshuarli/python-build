"""Fixed complete outputs for the public catalog URL workload."""

from __future__ import annotations

import unittest

from benchmarks.workloads import catalog_url, catalog_url_breadth
from benchmarks.workloads.registry import BY_NAME


class CatalogUrlWorkloadTests(unittest.TestCase):
    def test_complete_batch_identity_and_units(self) -> None:
        self.assertEqual(BY_NAME["catalog_url_normalize"].module, "catalog_url")
        first = catalog_url.catalog_url_normalize(1)
        repeated = catalog_url.catalog_url_normalize(2)
        self.assertEqual(first["input_digest"],
                         "7593b5e1e89029f11d467bdbd9a6b5392ce088f9591251c72133324c6a94d38f")
        self.assertEqual(first["digest"],
                         "a6fedf33e0fd5e72b79af8d77499b9a7bb8e8d53491955f2e554570679e04941")
        self.assertEqual((first["urls_per_operation"], first["keys_per_operation"]), (48, 48))
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(repeated["operation_count"], 2)
        self.assertEqual(repeated["digest"], first["digest"])
        self.assertGreater(first["elapsed_seconds"], 0)

    def test_catalog_behavior_for_ipv6_and_malformed_escapes(self) -> None:
        catalog = catalog_url._catalog_normalize()
        batch = catalog_url._batch()
        self.assertEqual(len(set(batch)), 36)
        self.assertEqual(catalog.normalize_url(batch[4][0]),
                         "https://reader:secret@2001:db8::1:443/docs?q=ok#part")
        self.assertEqual(catalog.normalize_url(batch[5][0]),
                         "https://example.org/%2f/%ZZ/%?bad=%G1#%")
        self.assertEqual(catalog.stable_key(batch[1][1]),
                         "caf%C3%A9/%E2%82%AC%20price/a%2Fb")

    def test_search_form_frames_complete_round_tripped_requests(self) -> None:
        self.assertEqual(BY_NAME["catalog_search_form"].module, "catalog_url_breadth")
        first = catalog_url_breadth.catalog_search_form(1)
        repeated = catalog_url_breadth.catalog_search_form(2)
        self.assertEqual(first["digest"],
                         "a56d64f19accb1be3bb302cc60f406928d15182828c2b7e975e957d503dc1f22")
        self.assertEqual(repeated["digest"], first["digest"])
        self.assertEqual(first["input_digest"], catalog_url._EXPECTED_INPUT)
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(repeated["operation_count"], 2)
        self.assertEqual((first["records_per_operation"], first["query_encodes_per_operation"],
                          first["requests_per_operation"], first["parses_per_operation"],
                          first["parsed_pairs_per_operation"],
                          first["parsed_fields_per_operation"],
                          first["quote_plus_calls_per_operation"]),
                         (48, 48, 48, 48, 240, 480, 480))

    def test_request_path_frames_complete_rebuilt_urls_and_bytes(self) -> None:
        self.assertEqual(BY_NAME["catalog_request_path"].module, "catalog_url_breadth")
        first = catalog_url_breadth.catalog_request_path(1)
        repeated = catalog_url_breadth.catalog_request_path(2)
        self.assertEqual(first["digest"],
                         "52db5e5b89587be9b6690dde7ffccaf709c6c2592b31f881c05354d1475d2eff")
        self.assertEqual(repeated["digest"], first["digest"])
        self.assertEqual(first["input_digest"], catalog_url._EXPECTED_INPUT)
        self.assertEqual(first["operation_count"], 1)
        self.assertEqual(repeated["operation_count"], 2)
        self.assertEqual((first["records_per_operation"], first["splits_per_operation"],
                          first["byte_unquotes_per_operation"], first["quotations_per_operation"],
                          first["unsplits_per_operation"], first["path_checks_per_operation"]),
                         (48, 96, 96, 48, 48, 48))

    def test_unknown_breadth_task_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown catalog URL breadth task"):
            catalog_url_breadth._url_task(1, "not_registered")


if __name__ == "__main__":
    unittest.main()
