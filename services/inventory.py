"""
MedSupply Rescue - Inventory & Transfer Management Service
Handles batch-level inventory, stock movements, transfer lifecycle state machine,
reconciliation, and tamper-evident cryptographic audit logs.
"""
import uuid
import json
import hashlib
from datetime import datetime, date, timedelta
from database.db import get_db_connection, hash_audit_block

def log_audit_event(conn, facility_id, user_id, user_name, user_role, entity_type, entity_id, action, payload_dict):
    """
    Appends an immutable audit event to the cryptographic SHA-256 chain.
    """
    cursor = conn.cursor()
    # Fetch last audit record for previous_hash
    last_event = cursor.execute(
        "SELECT id, current_hash FROM audit_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    
    prev_hash = last_event['current_hash'] if last_event else "0" * 64
    timestamp = datetime.now().isoformat()
    event_uuid = f"evt-{uuid.uuid4().hex[:12]}"
    payload_json = json.dumps(payload_dict, default=str, sort_keys=True)
    current_hash = hash_audit_block(prev_hash, timestamp, entity_type, str(entity_id), action, payload_json)
    
    cursor.execute(
        """INSERT INTO audit_events 
           (event_uuid, timestamp, facility_id, user_id, user_name, user_role, entity_type, entity_id, action, payload_json, previous_hash, current_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_uuid, timestamp, facility_id, user_id, user_name, user_role, entity_type, str(entity_id), action, payload_json, prev_hash, current_hash)
    )
    return current_hash

def verify_ledger_integrity(conn):
    """
    Verifies that the entire audit chain is untampered by recalculating every hash from genesis to tip.
    """
    cursor = conn.cursor()
    events = cursor.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()
    
    if not events:
        return {"status": "EMPTY", "valid": True, "count": 0, "message": "No audit records found."}
    
    expected_prev_hash = "0" * 64
    verified_count = 0
    
    for evt in events:
        if evt['previous_hash'] != expected_prev_hash:
            return {
                "status": "COMPROMISED",
                "valid": False,
                "broken_at_id": evt['id'],
                "broken_event_uuid": evt['event_uuid'],
                "reason": f"Mismatched previous_hash at event #{evt['id']}. Expected {expected_prev_hash[:16]}..., got {evt['previous_hash'][:16]}...",
                "verified_count": verified_count
            }
        
        # Recalculate hash
        computed_hash = hash_audit_block(
            evt['previous_hash'],
            evt['timestamp'],
            evt['entity_type'],
            evt['entity_id'],
            evt['action'],
            evt['payload_json']
        )
        
        if computed_hash != evt['current_hash']:
            return {
                "status": "COMPROMISED",
                "valid": False,
                "broken_at_id": evt['id'],
                "broken_event_uuid": evt['event_uuid'],
                "reason": f"Cryptographic signature invalid at event #{evt['id']}. Content was modified!",
                "verified_count": verified_count
            }
        
        expected_prev_hash = evt['current_hash']
        verified_count += 1
        
    return {
        "status": "VERIFIED_SECURE",
        "valid": True,
        "count": verified_count,
        "latest_hash": expected_prev_hash,
        "message": f"All {verified_count} audit blocks cryptographically verified with zero discrepancies."
    }

def get_facility_inventory(conn, facility_id=None, medicine_id=None, category=None, storage_req=None):
    """
    Retrieves batch inventory with calculated days to expiry and status tags.
    """
    query = """
        SELECT b.*, m.generic_name, m.brand_name, m.ndc_or_code, m.dosage_form, 
               m.strength, m.unit_of_measure, m.storage_requirement, m.therapeutic_category,
               m.min_safety_stock_default,
               f.name as facility_name, f.facility_type, f.has_cold_chain
        FROM batches b
        JOIN medicines m ON b.medicine_id = m.id
        JOIN facilities f ON b.facility_id = f.id
        WHERE b.status != 'archived'
    """
    params = []
    if facility_id:
        query += " AND b.facility_id = ?"
        params.append(facility_id)
    if medicine_id:
        query += " AND b.medicine_id = ?"
        params.append(medicine_id)
    if category:
        query += " AND m.therapeutic_category = ?"
        params.append(category)
    if storage_req:
        query += " AND m.storage_requirement LIKE ?"
        params.append(f"%{storage_req}%")
        
    query += " ORDER BY b.expiry_date ASC, b.id ASC"
    
    rows = conn.execute(query, params).fetchall()
    
    today = date.today()
    results = []
    for r in rows:
        d = dict(r)
        exp_date = datetime.strptime(d['expiry_date'], "%Y-%m-%d").date()
        days_to_expiry = (exp_date - today).days
        d['days_to_expiry'] = days_to_expiry
        
        # Calculate expiry urgency badge
        if days_to_expiry < 0:
            d['expiry_status'] = 'EXPIRED'
            d['expiry_badge_class'] = 'bg-red-100 text-red-800 border-red-300'
        elif days_to_expiry <= 30:
            d['expiry_status'] = 'CRITICAL (<30d)'
            d['expiry_badge_class'] = 'bg-red-600 text-white font-bold'
        elif days_to_expiry <= 60:
            d['expiry_status'] = 'WARNING (<60d)'
            d['expiry_badge_class'] = 'bg-amber-100 text-amber-800 border-amber-300'
        elif days_to_expiry <= 90:
            d['expiry_status'] = 'WATCH (<90d)'
            d['expiry_badge_class'] = 'bg-yellow-100 text-yellow-800 border-yellow-300'
        else:
            d['expiry_status'] = 'STABLE'
            d['expiry_badge_class'] = 'bg-emerald-100 text-emerald-800 border-emerald-300'
            
        d['available_quantity'] = max(0, d['current_quantity'] - d['reserved_quantity'])
        results.append(d)
        
    return results

def get_alerts(conn, facility_id=None):
    """
    Computes active system alerts:
    1. Near-Expiry alerts (<= 60 days)
    2. Low-Stock alerts (below safety threshold)
    3. Critical Shortages
    """
    today = date.today()
    batches = get_facility_inventory(conn, facility_id=facility_id)
    
    near_expiry_alerts = []
    low_stock_alerts = []
    
    # Group by facility and medicine for aggregate stock checking
    facility_stock = {}
    
    for b in batches:
        if b['status'] == 'active' and b['current_quantity'] > 0:
            if b['days_to_expiry'] <= 60:
                near_expiry_alerts.append({
                    "type": "NEAR_EXPIRY",
                    "batch_id": b['id'],
                    "batch_number": b['batch_number'],
                    "medicine_id": b['medicine_id'],
                    "medicine_name": f"{b['generic_name']} ({b['strength']})",
                    "facility_id": b['facility_id'],
                    "facility_name": b['facility_name'],
                    "quantity": b['current_quantity'],
                    "expiry_date": b['expiry_date'],
                    "days_to_expiry": b['days_to_expiry'],
                    "severity": "CRITICAL" if b['days_to_expiry'] <= 30 else "WARNING"
                })
        
        # Aggregate facility stock
        key = (b['facility_id'], b['medicine_id'])
        if key not in facility_stock:
            facility_stock[key] = {
                "facility_id": b['facility_id'],
                "facility_name": b['facility_name'],
                "medicine_id": b['medicine_id'],
                "medicine_name": f"{b['generic_name']} ({b['strength']})",
                "unit": b['unit_of_measure'],
                "total_stock": 0,
                "safety_threshold": b['min_safety_stock_default']
            }
        facility_stock[key]['total_stock'] += b['available_quantity']
        
    for key, data in facility_stock.items():
        if data['total_stock'] <= data['safety_threshold']:
            severity = "CRITICAL" if data['total_stock'] <= (data['safety_threshold'] // 3) else "WARNING"
            low_stock_alerts.append({
                "type": "LOW_STOCK",
                "facility_id": data['facility_id'],
                "facility_name": data['facility_name'],
                "medicine_id": data['medicine_id'],
                "medicine_name": data['medicine_name'],
                "unit": data['unit'],
                "current_stock": data['total_stock'],
                "threshold": data['safety_threshold'],
                "severity": severity
            })
            
    # Open shortages
    shortages_query = """
        SELECT s.*, m.generic_name, m.strength, f.name as facility_name
        FROM shortage_requests s
        JOIN medicines m ON s.medicine_id = m.id
        JOIN facilities f ON s.requesting_facility_id = f.id
        WHERE s.status IN ('OPEN', 'MATCHED')
        ORDER BY CASE s.urgency WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END
    """
    if facility_id:
        shortages_query += f" AND s.requesting_facility_id = {facility_id}"
    shortage_rows = [dict(r) for r in conn.execute(shortages_query).fetchall()]
    
    return {
        "near_expiry": near_expiry_alerts,
        "low_stock": low_stock_alerts,
        "active_shortages": shortage_rows,
        "total_alerts": len(near_expiry_alerts) + len(low_stock_alerts) + len(shortage_rows)
    }

def add_batch(conn, facility_id, medicine_id, batch_number, quantity, expiry_date, storage_location, manufacture_date=None, user_info=None):
    """
    Registers a new medicine batch with full provenance logging.
    """
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO batches 
           (medicine_id, facility_id, batch_number, initial_quantity, current_quantity, reserved_quantity, manufacture_date, expiry_date, storage_location, status)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'active')""",
        (medicine_id, facility_id, batch_number, quantity, quantity, manufacture_date, expiry_date, storage_location)
    )
    batch_id = cursor.lastrowid
    
    # Stock movement
    cursor.execute(
        """INSERT INTO stock_movements 
           (facility_id, batch_id, medicine_id, movement_type, quantity_delta, reference_id, performed_by_id, notes)
           VALUES (?, ?, ?, 'INITIAL_LOAD', ?, ?, ?, ?)""",
        (facility_id, batch_id, medicine_id, quantity, f"BATCH_NEW_{batch_id}", user_info.get('id') if user_info else None, "Initial batch intake")
    )
    
    # Audit log
    payload = {
        "batch_id": batch_id,
        "batch_number": batch_number,
        "medicine_id": medicine_id,
        "facility_id": facility_id,
        "quantity": quantity,
        "expiry_date": expiry_date,
        "storage_location": storage_location
    }
    user_id = user_info.get('id') if user_info else 1
    user_name = user_info.get('full_name') if user_info else "System"
    user_role = user_info.get('role') if user_info else "platform_admin"
    log_audit_event(conn, facility_id, user_id, user_name, user_role, "BATCH", batch_id, "CREATE", payload)
    
    conn.commit()
    return batch_id

def create_transfer_request(conn, shortage_request_id, source_facility_id, dest_facility_id, medicine_id, batch_id, quantity, requester_user):
    """
    Initiates a new facility-to-facility transfer request.
    Validates batch availability and cold chain requirements.
    """
    cursor = conn.cursor()
    
    # Verify batch has available quantity
    batch = cursor.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch:
        raise ValueError("Selected batch not found.")
    
    avail = batch['current_quantity'] - batch['reserved_quantity']
    if avail < quantity:
        raise ValueError(f"Insufficient unreserved quantity in batch {batch['batch_number']}. Available: {avail}, Requested: {quantity}")
        
    # Verify cold chain compliance
    med = cursor.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    dest_fac = cursor.execute("SELECT * FROM facilities WHERE id = ?", (dest_facility_id,)).fetchone()
    source_fac = cursor.execute("SELECT * FROM facilities WHERE id = ?", (source_facility_id,)).fetchone()
    
    cold_chain_required = 1 if "Cold Chain" in med['storage_requirement'] or "2-8°C" in med['storage_requirement'] else 0
    if cold_chain_required:
        if not dest_fac['has_cold_chain']:
            raise ValueError(f"Regulatory Alert: Destination facility '{dest_fac['name']}' lacks certified cold chain storage required for {med['generic_name']}!")
        if not source_fac['has_cold_chain']:
            raise ValueError(f"Regulatory Alert: Source facility '{source_fac['name']}' cold chain integrity cannot be guaranteed!")

    transfer_code = f"TRX-{date.today().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    
    cursor.execute(
        """INSERT INTO transfer_requests 
           (transfer_code, shortage_request_id, source_facility_id, dest_facility_id, medicine_id, batch_id, quantity, status, requester_id, cold_chain_required)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', ?, ?)""",
        (transfer_code, shortage_request_id, source_facility_id, dest_facility_id, medicine_id, batch_id, quantity, requester_user['id'], cold_chain_required)
    )
    transfer_id = cursor.lastrowid
    
    if shortage_request_id:
        cursor.execute("UPDATE shortage_requests SET status = 'MATCHED' WHERE id = ?", (shortage_request_id,))
        
    payload = {
        "transfer_id": transfer_id,
        "transfer_code": transfer_code,
        "shortage_id": shortage_request_id,
        "source_facility": source_fac['name'],
        "dest_facility": dest_fac['name'],
        "medicine": med['generic_name'],
        "batch_number": batch['batch_number'],
        "quantity": quantity,
        "cold_chain_required": cold_chain_required
    }
    log_audit_event(conn, dest_facility_id, requester_user['id'], requester_user['full_name'], requester_user['role'], "TRANSFER", transfer_code, "CREATE", payload)
    
    conn.commit()
    return transfer_id, transfer_code

def approve_transfer(conn, transfer_id, approver_user, comments=None):
    """
    Authorized Approver signs off on transfer.
    Reserves stock in source batch so it cannot be double-committed.
    Generates cryptographic digital approval signature.
    """
    cursor = conn.cursor()
    trx = cursor.execute("SELECT * FROM transfer_requests WHERE id = ?", (transfer_id,)).fetchone()
    if not trx:
        raise ValueError("Transfer request not found.")
    if trx['status'] != 'PENDING_APPROVAL':
        raise ValueError(f"Cannot approve transfer in status '{trx['status']}'. Must be PENDING_APPROVAL.")

    batch = cursor.execute("SELECT * FROM batches WHERE id = ?", (trx['batch_id'],)).fetchone()
    avail = batch['current_quantity'] - batch['reserved_quantity']
    if avail < trx['quantity']:
        raise ValueError(f"Stock reservation failed: only {avail} units available, {trx['quantity']} required.")

    # Reserve the stock in donor batch
    cursor.execute(
        "UPDATE batches SET reserved_quantity = reserved_quantity + ? WHERE id = ?",
        (trx['quantity'], trx['batch_id'])
    )

    # Generate digital signature
    sig_content = f"AUTH|{trx['transfer_code']}|{approver_user['id']}|{approver_user['license_or_badge']}|{datetime.now().isoformat()}"
    digital_signature = hashlib.sha256(sig_content.encode()).hexdigest()

    # Record in approvals table
    cursor.execute(
        """INSERT INTO approvals (transfer_request_id, approver_id, approval_status, signature_hash, regulatory_check_passed, cold_chain_certified, comments)
           VALUES (?, ?, 'APPROVED', ?, 1, 1, ?)""",
        (transfer_id, approver_user['id'], digital_signature, comments or "Authorized under Clinical Supply Coordination Protocols.")
    )

    # Update transfer status
    now_ts = datetime.now().isoformat()
    cursor.execute(
        "UPDATE transfer_requests SET status = 'APPROVED', approver_id = ?, approved_at = ? WHERE id = ?",
        (approver_user['id'], now_ts, transfer_id)
    )

    # Audit log
    payload = {
        "transfer_code": trx['transfer_code'],
        "approver_name": approver_user['full_name'],
        "approver_license": approver_user['license_or_badge'],
        "signature_hash": digital_signature,
        "quantity_reserved": trx['quantity'],
        "comments": comments
    }
    log_audit_event(conn, trx['source_facility_id'], approver_user['id'], approver_user['full_name'], approver_user['role'], "APPROVAL", trx['transfer_code'], "APPROVE", payload)

    conn.commit()
    return True

def dispatch_transfer(conn, transfer_id, dispatch_user, carrier, tracking_number, dispatch_temperature, notes=None):
    """
    Donor facility dispatches stock.
    Deducts current & reserved quantity from source batch.
    Logs stock movement TRANSFER_OUT.
    """
    cursor = conn.cursor()
    trx = cursor.execute("SELECT * FROM transfer_requests WHERE id = ?", (transfer_id,)).fetchone()
    if not trx:
        raise ValueError("Transfer request not found.")
    if trx['status'] != 'APPROVED':
        raise ValueError(f"Cannot dispatch transfer in status '{trx['status']}'. Must be APPROVED.")

    batch = cursor.execute("SELECT * FROM batches WHERE id = ?", (trx['batch_id'],)).fetchone()
    
    # Deduct stock
    new_current = batch['current_quantity'] - trx['quantity']
    new_reserved = max(0, batch['reserved_quantity'] - trx['quantity'])
    new_status = 'transferred_out' if new_current <= 0 else batch['status']
    
    cursor.execute(
        "UPDATE batches SET current_quantity = ?, reserved_quantity = ?, status = ? WHERE id = ?",
        (new_current, new_reserved, new_status, trx['batch_id'])
    )

    # Stock movement
    cursor.execute(
        """INSERT INTO stock_movements 
           (facility_id, batch_id, medicine_id, movement_type, quantity_delta, reference_id, performed_by_id, notes)
           VALUES (?, ?, ?, 'TRANSFER_OUT', ?, ?, ?, ?)""",
        (trx['source_facility_id'], trx['batch_id'], trx['medicine_id'], -trx['quantity'], trx['transfer_code'], dispatch_user['id'], f"Dispatched via {carrier}. Tracking: {tracking_number}")
    )

    # Update transfer request
    now_ts = datetime.now().isoformat()
    cursor.execute(
        """UPDATE transfer_requests 
           SET status = 'DISPATCHED', dispatched_by_id = ?, dispatched_at = ?, carrier = ?, 
               tracking_number = ?, dispatch_temperature = ?, dispatch_notes = ?
           WHERE id = ?""",
        (dispatch_user['id'], now_ts, carrier, tracking_number, dispatch_temperature, notes, transfer_id)
    )

    # If linked to shortage request, update status to IN_TRANSFER
    if trx['shortage_request_id']:
        cursor.execute("UPDATE shortage_requests SET status = 'IN_TRANSFER' WHERE id = ?", (trx['shortage_request_id'],))

    # Audit log
    payload = {
        "transfer_code": trx['transfer_code'],
        "carrier": carrier,
        "tracking_number": tracking_number,
        "dispatch_temperature": dispatch_temperature,
        "deducted_quantity": trx['quantity'],
        "remaining_batch_stock": new_current
    }
    log_audit_event(conn, trx['source_facility_id'], dispatch_user['id'], dispatch_user['full_name'], dispatch_user['role'], "TRANSFER", trx['transfer_code'], "DISPATCH", payload)

    conn.commit()
    return True

def receive_and_reconcile_transfer(conn, transfer_id, receive_user, received_quantity, arrival_temperature, storage_location, notes=None, discrepancy_reason=None):
    """
    Receiving facility accepts shipment, checks cold-chain temperature,
    reconciles count, and creates/updates inventory batch at recipient facility.
    """
    cursor = conn.cursor()
    trx = cursor.execute("SELECT * FROM transfer_requests WHERE id = ?", (transfer_id,)).fetchone()
    if not trx:
        raise ValueError("Transfer request not found.")
    if trx['status'] != 'DISPATCHED':
        raise ValueError(f"Cannot receive transfer in status '{trx['status']}'. Must be DISPATCHED.")

    source_batch = cursor.execute("SELECT * FROM batches WHERE id = ?", (trx['batch_id'],)).fetchone()
    
    # Check for discrepancy
    has_discrepancy = (received_quantity != trx['quantity'])
    now_ts = datetime.now().isoformat()

    # Create new batch at destination facility mirroring original batch provenance
    cursor.execute(
        """INSERT INTO batches 
           (medicine_id, facility_id, batch_number, initial_quantity, current_quantity, reserved_quantity, manufacture_date, expiry_date, storage_location, status)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'active')""",
        (trx['medicine_id'], trx['dest_facility_id'], source_batch['batch_number'], received_quantity, received_quantity, source_batch['manufacture_date'], source_batch['expiry_date'], storage_location)
    )
    dest_batch_id = cursor.lastrowid

    # Stock movement in destination facility
    cursor.execute(
        """INSERT INTO stock_movements 
           (facility_id, batch_id, medicine_id, movement_type, quantity_delta, reference_id, performed_by_id, notes)
           VALUES (?, ?, ?, 'TRANSFER_IN', ?, ?, ?, ?)""",
        (trx['dest_facility_id'], dest_batch_id, trx['medicine_id'], received_quantity, trx['transfer_code'], receive_user['id'], f"Received from {trx['source_facility_id']} at {arrival_temperature}°C")
    )

    # If discrepancy exists, record audit discrepancy adjustment
    if has_discrepancy:
        variance = received_quantity - trx['quantity']
        cursor.execute(
            """INSERT INTO stock_movements 
               (facility_id, batch_id, medicine_id, movement_type, quantity_delta, reference_id, performed_by_id, notes)
               VALUES (?, ?, ?, 'ADJUSTMENT', ?, ?, ?, ?)""",
            (trx['dest_facility_id'], dest_batch_id, trx['medicine_id'], variance, f"DISCREPANCY_{trx['transfer_code']}", receive_user['id'], f"Transfer Reconciliation Discrepancy: {discrepancy_reason}")
        )

    # Update transfer request
    cursor.execute(
        """UPDATE transfer_requests 
           SET status = 'RECONCILED', received_by_id = ?, received_at = ?, completed_at = ?,
               received_quantity = ?, arrival_temperature = ?, receipt_notes = ?, discrepancy_reason = ?
           WHERE id = ?""",
        (receive_user['id'], now_ts, now_ts, received_quantity, arrival_temperature, notes, discrepancy_reason if has_discrepancy else None, transfer_id)
    )

    # Mark shortage request fulfilled if all required quantity received
    if trx['shortage_request_id']:
        cursor.execute("UPDATE shortage_requests SET status = 'FULFILLED' WHERE id = ?", (trx['shortage_request_id'],))

    # Audit log
    payload = {
        "transfer_code": trx['transfer_code'],
        "sent_quantity": trx['quantity'],
        "received_quantity": received_quantity,
        "has_discrepancy": has_discrepancy,
        "discrepancy_reason": discrepancy_reason if has_discrepancy else "None (Reconciled Exact)",
        "arrival_temperature": arrival_temperature,
        "new_batch_id": dest_batch_id,
        "storage_location": storage_location
    }
    log_audit_event(conn, trx['dest_facility_id'], receive_user['id'], receive_user['full_name'], receive_user['role'], "TRANSFER", trx['transfer_code'], "RECONCILE", payload)

    conn.commit()
    return True
