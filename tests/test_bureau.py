"""Baseline regressions for the existing stdlib schema/store/demo machinery."""
import unittest
from bureau import demo
from bureau.schema import validate
from bureau.store import Store
from bureau.adapters import adapt
from bureau.server import coverage


class BureauTests(unittest.TestCase):
    def test_demo_schema_and_store(self):
        records = demo.build()
        self.assertEqual(len(records), 28)
        self.assertTrue(all(not validate(r) for r in records))
        store = Store(':memory:')
        try:
            self.assertEqual(store.ingest_many(records)['inserted'], 28)
            self.assertEqual(store.ingest_many(records)['duplicate'], 28)
            self.assertTrue(store.ledger(event_type='mandate_revoked'))
            self.assertEqual({r['status'] for r in coverage(store)}, {'OBSERVED', 'DERIVED', 'UNKNOWN'})
        finally: store.close()

    def test_canonical_adapter_preserves_records(self):
        records = demo.build()
        adapted = adapt({'format': 'openline.bureau.canonical.v1', 'records': records},
                        {'source_repo': 'synthetic', 'source_path': 'demo.json'})
        self.assertEqual([r['receipt_id'] for r in adapted], [r['receipt_id'] for r in records])
