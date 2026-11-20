"""
MedSupply Rescue - Comprehensive Verification & Validation Test Suite
Tests all core product features, state machine transitions, cold chain logic,
forecasting challenge, and cryptographic ledger verification.
"""
import unittest
import os
import sqlite3
from datetime import datetime, date, timedelta

from database.db import get_db_connection, init_db
from services.inventory import (
    get_facility_inventory, get_alerts, add_batch,
    create_transfer_request, approve_transfer, dispatch_transfer,
    receive_and_reconcile_transfer, verify_ledger_integrity
)
from services.matching import find_eligible_donors
from services.forecasting import (
    calculate_facility_forecast, generate_network_redistribution_suggestions
)
from app import app

class TestMedSupplyRescue(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Force re-seed database to pristine baseline
        init_db(force_reseed=True)
        cls.conn = get_db_connection()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_facilities_and_catalogue_seeded(self):
        """Verify baseline facilities, medicines, and role-based users are correctly populated."""
        fac_count = self.conn.execute("SELECT count(*) as c FROM facilities").fetchone()['c']
        self.assertGreaterEqual(fac_count, 5, "Should have at least 5 healthcare facilities")

        med_count = self.conn.execute("SELECT count(*) as c FROM medicines").fetchone()['c']
        self.assertGreaterEqual(med_count, 8, "Should have at least 8 essential medicines")

        users_count = self.conn.execute("SELECT count(*) as c FROM users").fetchone()['c']
        self.assertGreaterEqual(users_count, 6, "Should have at least 6 role-based users")

        # Verify role types
        roles = [r['role'] for r in self.conn.execute("SELECT DISTINCT role FROM users").fetchall()]
        self.assertIn("platform_admin", roles)
        self.assertIn("facility_manager", roles)
        self.assertIn("approver", roles)
        self.assertIn("staff", roles)

    def test_02_batch_inventory_and_alerts(self):
        """Test batch-level tracking, expiry countdown calculation, and low-stock alerts."""
        batches = get_facility_inventory(self.conn)
        self.assertGreater(len(batches), 10, "Should have multiple batches across network")
        facility_counts = self.conn.execute(
            "SELECT facility_id, count(*) AS batch_count FROM batches GROUP BY facility_id"
        ).fetchall()
        self.assertTrue(
            all(row['batch_count'] >= 20 for row in facility_counts),
            "Each demo facility should have at least 20 inventory batches"
        )

        # Check calculated fields
        sample = batches[0]
        self.assertIn('days_to_expiry', sample)
        self.assertIn('available_quantity', sample)
        self.assertIn('expiry_badge_class', sample)

        # Alerts calculation
        alerts = get_alerts(self.conn)
        self.assertIn('near_expiry', alerts)
        self.assertIn('low_stock', alerts)
        self.assertIn('active_shortages', alerts)
        self.assertGreater(len(alerts['near_expiry']), 0, "Should detect near-expiry batches (<=60d)")

    def test_inventory_table_scrolls_and_paginates(self):
        self.client.get('/quick-login/1')
        response = self.client.get('/inventory')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Scrollable inventory records', response.data)
        self.assertIn(b'max-h-[390px] overflow-auto', response.data)
        total_batches = self.conn.execute(
            "SELECT count(*) FROM batches"
        ).fetchone()[0]
        self.assertIn(f'{total_batches}</strong> records'.encode(), response.data)
        self.assertIn(b'1-7', response.data)
        self.assertEqual(
            response.data.count(b'class="hover:bg-slate-50/80 transition"'),
            7
        )

        page_two = self.client.get('/inventory?page=2')
        self.assertIn(b'8-14', page_two.data)

    def test_seeded_transfer_pipeline_has_actionable_workflow_states(self):
        statuses = {
            row['status'] for row in self.conn.execute(
                "SELECT status FROM transfer_requests"
            ).fetchall()
        }
        self.assertEqual(
            statuses,
            {'PENDING_APPROVAL', 'APPROVED', 'DISPATCHED', 'RECONCILED'}
        )
        self.assertTrue(verify_ledger_integrity(self.conn)['valid'])

        self.client.get('/quick-login/2')
        response = self.client.get('/transfers')
        self.assertEqual(response.status_code, 200)
        for action in (
            b'Authorize & Sign Transfer',
            b'Dispatch Shipment',
            b'Receive & Reconcile',
            b'Chain of Custody Completed'
        ):
            self.assertIn(action, response.data)

    def test_03_intelligent_matching_engine(self):
        """Test intelligent shortage matching prioritizing near-expiry surplus stock."""
        # Northside Community Clinic (Fac 2) has a shortage of Amoxicillin (Med 1)
        matches = find_eligible_donors(self.conn, medicine_id=1, requesting_facility_id=2, required_quantity=40)
        self.assertGreater(len(matches), 0, "Should find candidate donor facilities")

        # Top candidate should be St. Jude Hospital (Fac 1) because it has batch expiring in 28 days with surplus!
        top_match = matches[0]
        self.assertEqual(top_match['facility_id'], 1, "St. Jude Hospital should be ranked #1 due to near-expiry rescue priority")
        self.assertGreaterEqual(top_match['match_score'], 80.0, "Top near-expiry rescue match should score >= 80%")
        self.assertTrue(top_match['eligible'], "Should be eligible")

    def test_04_cold_chain_compatibility_rule(self):
        """Verify cold-chain compliance check disallows non-cold-chain facilities from transferring refrigerated medicines."""
        # Insulin Glargine (Med 2) requires Cold Chain (2-8°C)
        # Valley Hope Dispensary (Fac 3) does NOT have cold chain (has_cold_chain = 0)
        matches = find_eligible_donors(self.conn, medicine_id=2, requesting_facility_id=3, required_quantity=10)
        for m in matches:
            self.assertFalse(m['eligible'], "Transfers to non-cold-chain facilities must be disqualified")
            self.assertIn("cold chain", m['disqualification_reason'].lower())

    def test_05_end_to_end_transfer_workflow_and_reconciliation(self):
        """
        Validate complete state machine:
        REQUESTED -> APPROVED -> DISPATCHED -> RECONCILED with stock reservation,
        deduction, destination addition, and cryptographic hash linkage.
        """
        requester = dict(self.conn.execute("SELECT * FROM users WHERE id = 3").fetchone()) # Dr. Sarah Chen
        approver = dict(self.conn.execute("SELECT * FROM users WHERE id = 4").fetchone())  # Dr. Elena Rostova
        dispatcher = dict(self.conn.execute("SELECT * FROM users WHERE id = 2").fetchone()) # Marcus Vance
        receiver = requester

        # Target batch: St. Jude Amoxicillin
        batch = dict(self.conn.execute("SELECT * FROM batches WHERE facility_id = 1 AND medicine_id = 1 AND status = 'active'").fetchone())
        initial_stock = batch['current_quantity']
        transfer_qty = 30

        # Step 1: Create Transfer Request
        trx_id, trx_code = create_transfer_request(
            self.conn, None, source_facility_id=1, dest_facility_id=2, medicine_id=1,
            batch_id=batch['id'], quantity=transfer_qty, requester_user=requester
        )
        self.assertTrue(trx_code.startswith("TRX-"))

        # Verify initial status
        trx = self.conn.execute("SELECT * FROM transfer_requests WHERE id = ?", (trx_id,)).fetchone()
        self.assertEqual(trx['status'], 'PENDING_APPROVAL')

        # Step 2: Approver signs off
        approve_transfer(self.conn, trx_id, approver_user=approver, comments="Legally approved for inter-clinic emergency transfer.")
        
        # Verify status is APPROVED and stock is RESERVED
        trx = self.conn.execute("SELECT * FROM transfer_requests WHERE id = ?", (trx_id,)).fetchone()
        self.assertEqual(trx['status'], 'APPROVED')
        updated_batch = self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch['id'],)).fetchone()
        self.assertEqual(updated_batch['reserved_quantity'], transfer_qty, "Batch stock must be reserved")

        # Step 3: Donor dispatches shipment
        dispatch_transfer(
            self.conn, trx_id, dispatch_user=dispatcher, carrier="Direct Medical Logistics",
            tracking_number="TRK-TEST-9981", dispatch_temperature=21.2, notes="Ambient secure package"
        )
        
        # Verify status is DISPATCHED, stock deducted from donor
        trx = self.conn.execute("SELECT * FROM transfer_requests WHERE id = ?", (trx_id,)).fetchone()
        self.assertEqual(trx['status'], 'DISPATCHED')
        updated_batch = self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch['id'],)).fetchone()
        self.assertEqual(updated_batch['current_quantity'], initial_stock - transfer_qty, "Stock must be deducted from donor batch")
        self.assertEqual(updated_batch['reserved_quantity'], 0, "Reserved stock cleared upon dispatch")

        # Step 4: Destination receives and reconciles
        dest_before_batches = self.conn.execute(
            "SELECT count(*) as c FROM batches WHERE facility_id = 2 AND medicine_id = 1"
        ).fetchone()['c']

        receive_and_reconcile_transfer(
            self.conn, trx_id, receive_user=receiver, received_quantity=transfer_qty,
            arrival_temperature=21.0, storage_location="Clinic Main Room - Bay 3",
            notes="Received all 30 bottles in perfect condition, seals intact.", discrepancy_reason=None
        )

        # Verify status is RECONCILED and new batch is added to destination facility
        trx = self.conn.execute("SELECT * FROM transfer_requests WHERE id = ?", (trx_id,)).fetchone()
        self.assertEqual(trx['status'], 'RECONCILED')
        
        dest_after_batches = self.conn.execute(
            "SELECT count(*) as c FROM batches WHERE facility_id = 2 AND medicine_id = 1"
        ).fetchone()['c']
        self.assertEqual(dest_after_batches, dest_before_batches + 1, "New batch should be added to recipient inventory")

    def test_06_cryptographic_audit_ledger_integrity(self):
        """Recalculate SHA-256 hash chains for all blocks to guarantee zero tampering."""
        report = verify_ledger_integrity(self.conn)
        self.assertTrue(report['valid'], f"Ledger verification failed: {report}")
        self.assertEqual(report['status'], 'VERIFIED_SECURE')
        self.assertGreater(report['count'], 3, "Should have multiple chained audit events")

    def test_07_advanced_forecasting_and_waste_redistribution(self):
        """Verify burn rate analysis, Days of Supply, stockout predictions, and redistribution suggestions."""
        forecasts = calculate_facility_forecast(self.conn)
        self.assertGreater(len(forecasts), 0)

        # Check presence of required forecasting metrics
        for f in forecasts:
            self.assertIn('daily_burn_rate', f)
            self.assertIn('days_of_supply', f)
            self.assertIn('lead_time_days', f)
            self.assertIn('stockout_status', f)
            self.assertIn('total_forecasted_waste', f)

        # Generate automated redistribution proposals
        suggestions = generate_network_redistribution_suggestions(self.conn)
        self.assertGreater(len(suggestions), 0, "Should generate proactive redistribution proposals")
        top_sug = suggestions[0]
        self.assertIn('suggested_quantity', top_sug)
        self.assertIn('priority_score', top_sug)
        self.assertIn('impact_summary', top_sug)

    def test_08_flask_http_routes(self):
        """Ensure all web views render HTTP 200 OK."""
        routes = ['/', '/inventory', '/shortages', '/transfers', '/forecasting', '/audit', '/simulation', '/login', '/workspaces']
        for r in routes:
            resp = self.client.get(r, follow_redirects=True)
            self.assertEqual(resp.status_code, 200, f"Route {r} failed with status {resp.status_code}")

    def test_audit_hash_is_loaded_only_on_demand_and_is_read_only(self):
        event = self.conn.execute(
            "SELECT id, current_hash FROM audit_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        page = self.client.get('/audit')

        self.assertEqual(page.status_code, 200)
        self.assertNotIn(event['current_hash'].encode(), page.data)
        self.assertNotIn(b'Previous Hash', page.data)
        self.assertIn(b'Quantity approved', page.data)
        self.assertNotIn(b'signature_hash', page.data)

        hash_response = self.client.get(f"/audit/{event['id']}/hash")
        self.assertEqual(hash_response.status_code, 200)
        self.assertEqual(hash_response.get_json()['current_hash'], event['current_hash'])
        self.assertEqual(self.client.get('/audit/999999/hash').status_code, 404)
        self.assertEqual(self.client.post(f"/audit/{event['id']}/hash").status_code, 405)

    def test_09_personal_workspaces_are_saved_and_owner_scoped(self):
        """Users can create multiple saved views, but cannot open another user's workspace."""
        self.client.get('/quick-login/3')

        self.client.post('/workspaces/create', data={
            'name': 'Expiry queue',
            'view_type': 'expiry_watchlist'
        })
        self.client.post('/workspaces/create', data={
            'name': 'Stock sheet',
            'view_type': 'inventory'
        })

        workspaces = self.conn.execute(
            "SELECT id, name FROM saved_workspaces WHERE owner_user_id = 3 ORDER BY id"
        ).fetchall()
        self.assertEqual([row['name'] for row in workspaces], ['Expiry queue', 'Stock sheet'])

        workspace_id = workspaces[0]['id']
        response = self.client.get(f'/workspaces/{workspace_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Expiry queue', response.data)
        self.assertIn(b'Spreadsheet view', response.data)
        inventory_response = self.client.get(f"/workspaces/{workspaces[1]['id']}")
        self.assertEqual(inventory_response.status_code, 200)

        for view_type in ('shortages', 'transfers', 'forecasting'):
            name = f'{view_type.title()} sheet'
            self.client.post('/workspaces/create', data={
                'name': name,
                'view_type': view_type
            })
            view_workspace = self.conn.execute(
                "SELECT id FROM saved_workspaces WHERE owner_user_id = 3 AND name = ?",
                (name,)
            ).fetchone()
            self.assertIsNotNone(view_workspace)
            view_response = self.client.get(f"/workspaces/{view_workspace['id']}")
            self.assertEqual(view_response.status_code, 200, f"{view_type} workspace failed to render")
            if view_type == 'forecasting':
                page_two_response = self.client.get(
                    f"/workspaces/{view_workspace['id']}?page=2"
                )
                self.assertEqual(page_two_response.status_code, 200)
                self.assertIn(b'Rows 11-', page_two_response.data)

        for index in range(10):
            self.client.post('/workspaces/create', data={
                'name': f'Extra sheet {index + 1}',
                'view_type': 'inventory'
            })
        workspace_count = self.conn.execute(
            "SELECT count(*) FROM saved_workspaces WHERE owner_user_id = 3"
        ).fetchone()[0]
        self.assertEqual(workspace_count, 15, "Workspace creation should not impose a small fixed limit")

        self.client.get('/quick-login/5')
        response = self.client.get(f'/workspaces/{workspace_id}')
        self.assertEqual(response.status_code, 404)

        self.client.get('/quick-login/3')
        batch_count_before = self.conn.execute("SELECT count(*) FROM batches").fetchone()[0]
        for row in self.conn.execute(
            "SELECT id FROM saved_workspaces WHERE owner_user_id = 3"
        ).fetchall():
            response = self.client.post(f"/workspaces/{row['id']}/delete")
            self.assertEqual(response.status_code, 302)
            self.assertIsNone(self.conn.execute(
                "SELECT id FROM saved_workspaces WHERE id = ?", (row['id'],)
            ).fetchone())
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM batches").fetchone()[0],
            batch_count_before
        )

if __name__ == '__main__':
    unittest.main()
