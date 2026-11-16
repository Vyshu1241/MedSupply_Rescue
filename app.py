"""
MedSupply Rescue - Main Web Application
Facility-to-Facility Medicine Stock Visibility & Transfer Coordination System
"""
import os
import json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db_connection, init_db
from services.inventory import (
    get_facility_inventory, get_alerts, add_batch,
    create_transfer_request, approve_transfer, dispatch_transfer,
    receive_and_reconcile_transfer, verify_ledger_integrity, log_audit_event
)
from services.matching import find_eligible_donors
from services.forecasting import (
    calculate_facility_forecast, generate_network_redistribution_suggestions
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'medsupply-rescue-secure-key-2026-production')

# Ensure DB is initialized upon startup
with app.app_context():
    init_db()

@app.before_request
def load_logged_in_user():
    g.db = get_db_connection()
    user_id = session.get('user_id')
    if user_id is None:
        # Default demo user for easy evaluation if not logged in
        # We auto-assign Dr. Sarah Chen (Northside Clinic Staff) so the app opens immediately usable!
        session['user_id'] = 3
        user_id = 3
    
    user = g.db.execute(
        """SELECT u.*, f.name as facility_name, f.facility_type, f.has_cold_chain, f.city, f.region
           FROM users u
           LEFT JOIN facilities f ON u.facility_id = f.id
           WHERE u.id = ?""",
        (user_id,)
    ).fetchone()
    
    g.user = dict(user) if user else None

    # Load all demo users for quick role switcher in header
    g.all_demo_users = [
        dict(r) for r in g.db.execute(
            """SELECT u.id, u.username, u.full_name, u.role, u.facility_id, f.name as facility_name 
               FROM users u LEFT JOIN facilities f ON u.facility_id = f.id ORDER BY u.id"""
        ).fetchall()
    ]

    # Global alert badge count
    try:
        user_fac = g.user['facility_id'] if g.user and g.user['role'] != 'platform_admin' else None
        alerts = get_alerts(g.db, facility_id=user_fac)
        g.alert_summary = alerts
    except Exception:
        g.alert_summary = {"total_alerts": 0, "near_expiry": [], "low_stock": [], "active_shortages": []}

@app.teardown_appcontext
def close_db(error):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

# ----------------- AUTHENTICATION ROUTES ----------------- #

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = g.db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash(f"Welcome back, {user['full_name']} ({user['role']})!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials. Try using the quick demo login buttons below.", "error")

    demo_users = [dict(r) for r in g.db.execute(
        "SELECT u.*, f.name as facility_name FROM users u LEFT JOIN facilities f ON u.facility_id = f.id"
    ).fetchall()]
    return render_template('login.html', demo_users=demo_users)

@app.route('/quick-login/<int:user_id>')
def quick_login(user_id):
    user = g.db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        session['user_id'] = user['id']
        flash(f"Switched active session to: {user['full_name']} ({user['role']})", "info")
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Facility info
        fac_name = request.form.get('facility_name')
        fac_type = request.form.get('facility_type')
        license_num = request.form.get('license_number')
        address = request.form.get('address')
        city = request.form.get('city')
        region = request.form.get('region')
        contact_email = request.form.get('contact_email')
        contact_phone = request.form.get('contact_phone')
        has_cold_chain = 1 if request.form.get('has_cold_chain') else 0

        # Staff user info
        username = request.form.get('username')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        role = request.form.get('role', 'facility_manager')
        user_badge = request.form.get('license_or_badge')

        try:
            cur = g.db.cursor()
            cur.execute(
                """INSERT INTO facilities (name, facility_type, license_number, address, city, region, contact_email, contact_phone, has_cold_chain)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fac_name, fac_type, license_num, address, city, region, contact_email, contact_phone, has_cold_chain)
            )
            fac_id = cur.lastrowid

            pwd_hash = generate_password_hash(password, method="pbkdf2:sha256")
            cur.execute(
                """INSERT INTO users (username, password_hash, full_name, role, facility_id, email, license_or_badge)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (username, pwd_hash, full_name, role, fac_id, contact_email, user_badge)
            )
            user_id = cur.lastrowid
            
            # Audit log
            log_audit_event(
                g.db, fac_id, user_id, full_name, role, "FACILITY", fac_id, "CREATE",
                {"facility_name": fac_name, "license": license_num, "cold_chain": has_cold_chain}
            )
            g.db.commit()

            session['user_id'] = user_id
            flash(f"Facility '{fac_name}' and account '{username}' registered successfully!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f"Registration error: {str(e)}", "error")

    return render_template('register.html')

# ----------------- CORE VIEWS ----------------- #

@app.route('/')
def dashboard():
    user = g.user
    fac_id = user['facility_id'] if user and user['role'] != 'platform_admin' else None

    # Overview KPIs
    total_batches = g.db.execute("SELECT count(*) as c FROM batches WHERE status = 'active'").fetchone()['c']
    total_shortages = g.db.execute("SELECT count(*) as c FROM shortage_requests WHERE status IN ('OPEN', 'MATCHED')").fetchone()['c']
    pending_transfers = g.db.execute("SELECT count(*) as c FROM transfer_requests WHERE status IN ('PENDING_APPROVAL', 'APPROVED', 'DISPATCHED')").fetchone()['c']
    reconciled_transfers = g.db.execute("SELECT count(*) as c FROM transfer_requests WHERE status = 'RECONCILED'").fetchone()['c']
    
    # Audit status
    audit_verification = verify_ledger_integrity(g.db)

    # Active alerts
    alerts = get_alerts(g.db, facility_id=fac_id)

    # Open shortage requests
    shortages = [dict(r) for r in g.db.execute(
        """SELECT s.*, m.generic_name, m.brand_name, m.strength, m.unit_of_measure, 
                  f.name as facility_name, f.city, u.full_name as requester_name
           FROM shortage_requests s
           JOIN medicines m ON s.medicine_id = m.id
           JOIN facilities f ON s.requesting_facility_id = f.id
           JOIN users u ON s.requested_by_user_id = u.id
           WHERE s.status IN ('OPEN', 'MATCHED')
           ORDER BY CASE s.urgency WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, s.id DESC
           LIMIT 5"""
    ).fetchall()]

    # Active transfer pipeline items
    transfers = [dict(r) for r in g.db.execute(
        """SELECT t.*, m.generic_name, m.strength, m.unit_of_measure,
                  sf.name as source_name, df.name as dest_name, b.batch_number, b.expiry_date
           FROM transfer_requests t
           JOIN medicines m ON t.medicine_id = m.id
           JOIN facilities sf ON t.source_facility_id = sf.id
           JOIN facilities df ON t.dest_facility_id = df.id
           JOIN batches b ON t.batch_id = b.id
           WHERE t.status != 'RECONCILED'
           ORDER BY t.id DESC LIMIT 5"""
    ).fetchall()]

    # Top near-expiry batches facing waste
    near_expiry_batches = get_facility_inventory(g.db, facility_id=fac_id)
    near_expiry_batches = [b for b in near_expiry_batches if b['days_to_expiry'] <= 60 and b['current_quantity'] > 0][:5]

    return render_template(
        'dashboard.html',
        total_batches=total_batches,
        total_shortages=total_shortages,
        pending_transfers=pending_transfers,
        reconciled_transfers=reconciled_transfers,
        audit_verification=audit_verification,
        alerts=alerts,
        shortages=shortages,
        transfers=transfers,
        near_expiry_batches=near_expiry_batches
    )

@app.route('/inventory')
def inventory():
    user = g.user
    selected_fac = request.args.get('facility_id', type=int)
    category = request.args.get('category')
    storage_req = request.args.get('storage_req')
    medicine_id = request.args.get('medicine_id', type=int)

    # For non-admin, default filter to their own facility unless they choose all
    if selected_fac is None and user and user['role'] != 'platform_admin':
        selected_fac = user['facility_id']

    batches = get_facility_inventory(
        g.db, 
        facility_id=selected_fac if selected_fac != 0 else None,
        medicine_id=medicine_id,
        category=category,
        storage_req=storage_req
    )

    facilities = [dict(r) for r in g.db.execute("SELECT * FROM facilities ORDER BY name").fetchall()]
    medicines = [dict(r) for r in g.db.execute("SELECT * FROM medicines ORDER BY generic_name").fetchall()]
    categories = [r['therapeutic_category'] for r in g.db.execute("SELECT DISTINCT therapeutic_category FROM medicines ORDER BY therapeutic_category").fetchall()]

    return render_template(
        'inventory.html',
        batches=batches,
        facilities=facilities,
        medicines=medicines,
        categories=categories,
        selected_fac=selected_fac,
        selected_cat=category,
        selected_storage=storage_req
    )

@app.route('/inventory/add-batch', methods=['POST'])
def add_new_batch():
    try:
        facility_id = int(request.form.get('facility_id'))
        medicine_id = int(request.form.get('medicine_id'))
        batch_number = request.form.get('batch_number').strip()
        quantity = int(request.form.get('quantity'))
        expiry_date = request.form.get('expiry_date')
        storage_location = request.form.get('storage_location')
        manufacture_date = request.form.get('manufacture_date') or None

        add_batch(
            g.db, facility_id, medicine_id, batch_number, quantity, expiry_date,
            storage_location, manufacture_date, user_info=g.user
        )
        flash(f"Batch {batch_number} ({quantity} units) registered successfully into inventory!", "success")
    except Exception as e:
        flash(f"Failed to record batch: {str(e)}", "error")

    return redirect(url_for('inventory'))

@app.route('/shortages', methods=['GET', 'POST'])
def shortages():
    if request.method == 'POST':
        try:
            req_fac_id = g.user['facility_id'] if g.user and g.user['facility_id'] else int(request.form.get('facility_id'))
            medicine_id = int(request.form.get('medicine_id'))
            quantity = int(request.form.get('quantity'))
            urgency = request.form.get('urgency')
            justification = request.form.get('clinical_justification')
            needed_by = request.form.get('needed_by_date')

            request_code = f"SR-{date.today().strftime('%Y%m')}-{g.db.execute('SELECT count(*)+1 as c FROM shortage_requests').fetchone()['c']:03d}"

            cur = g.db.cursor()
            cur.execute(
                """INSERT INTO shortage_requests 
                   (request_code, requesting_facility_id, requested_by_user_id, medicine_id, required_quantity, urgency, clinical_justification, needed_by_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (request_code, req_fac_id, g.user['id'], medicine_id, quantity, urgency, justification, needed_by)
            )
            req_id = cur.lastrowid
            
            med = g.db.execute("SELECT generic_name FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
            log_audit_event(
                g.db, req_fac_id, g.user['id'], g.user['full_name'], g.user['role'],
                "SHORTAGE", request_code, "CREATE",
                {"medicine": med['generic_name'], "quantity": quantity, "urgency": urgency}
            )
            g.db.commit()

            flash(f"Shortage Request {request_code} logged! Run the Matching Engine to locate candidate donor batches.", "success")
            return redirect(url_for('shortages', match_id=req_id))
        except Exception as e:
            flash(f"Failed to create shortage request: {str(e)}", "error")

    # List all shortages
    query = """
        SELECT s.*, m.generic_name, m.brand_name, m.strength, m.unit_of_measure, m.storage_requirement,
               f.name as facility_name, f.city, f.has_cold_chain, u.full_name as requester_name
        FROM shortage_requests s
        JOIN medicines m ON s.medicine_id = m.id
        JOIN facilities f ON s.requesting_facility_id = f.id
        JOIN users u ON s.requested_by_user_id = u.id
        ORDER BY CASE s.status WHEN 'OPEN' THEN 1 WHEN 'MATCHED' THEN 2 WHEN 'IN_TRANSFER' THEN 3 ELSE 4 END,
                 CASE s.urgency WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                 s.id DESC
    """
    shortage_list = [dict(r) for r in g.db.execute(query).fetchall()]

    # If match_id query parameter is present, pre-run matching engine for that request
    active_match = None
    match_candidates = []
    match_id = request.args.get('match_id', type=int)
    if match_id:
        req_row = g.db.execute("SELECT * FROM shortage_requests WHERE id = ?", (match_id,)).fetchone()
        if req_row:
            active_match = dict(req_row)
            match_candidates = find_eligible_donors(
                g.db, active_match['medicine_id'], active_match['requesting_facility_id'], active_match['required_quantity']
            )

    medicines = [dict(r) for r in g.db.execute("SELECT * FROM medicines ORDER BY generic_name").fetchall()]
    facilities = [dict(r) for r in g.db.execute("SELECT * FROM facilities ORDER BY name").fetchall()]

    return render_template(
        'shortages.html',
        shortage_list=shortage_list,
        active_match=active_match,
        match_candidates=match_candidates,
        medicines=medicines,
        facilities=facilities
    )

@app.route('/transfers')
def transfers():
    # List all transfers
    query = """
        SELECT t.*, m.generic_name, m.brand_name, m.strength, m.unit_of_measure, m.storage_requirement,
               sf.name as source_facility_name, sf.city as source_city, sf.has_cold_chain as source_cold_chain,
               df.name as dest_facility_name, df.city as dest_city, df.has_cold_chain as dest_cold_chain,
               b.batch_number, b.expiry_date, b.current_quantity as batch_stock,
               req_u.full_name as requester_name,
               app_u.full_name as approver_name, app_u.license_or_badge as approver_badge,
               disp_u.full_name as dispatcher_name,
               recv_u.full_name as receiver_name,
               a.signature_hash as approval_sig, a.comments as approval_comments
        FROM transfer_requests t
        JOIN medicines m ON t.medicine_id = m.id
        JOIN facilities sf ON t.source_facility_id = sf.id
        JOIN facilities df ON t.dest_facility_id = df.id
        JOIN batches b ON t.batch_id = b.id
        LEFT JOIN users req_u ON t.requester_id = req_u.id
        LEFT JOIN users app_u ON t.approver_id = app_u.id
        LEFT JOIN users disp_u ON t.dispatched_by_id = disp_u.id
        LEFT JOIN users recv_u ON t.received_by_id = recv_u.id
        LEFT JOIN approvals a ON a.transfer_request_id = t.id
        ORDER BY CASE t.status 
            WHEN 'PENDING_APPROVAL' THEN 1 
            WHEN 'APPROVED' THEN 2 
            WHEN 'DISPATCHED' THEN 3 
            WHEN 'RECEIVED' THEN 4 
            WHEN 'RECONCILED' THEN 5 
            ELSE 6 END, t.id DESC
    """
    all_transfers = [dict(r) for r in g.db.execute(query).fetchall()]
    return render_template('transfers.html', transfers=all_transfers)

@app.route('/transfers/create', methods=['POST'])
def create_transfer():
    try:
        shortage_id = request.form.get('shortage_id', type=int)
        batch_id = int(request.form.get('batch_id'))
        source_fac_id = int(request.form.get('source_facility_id'))
        dest_fac_id = int(request.form.get('dest_facility_id'))
        medicine_id = int(request.form.get('medicine_id'))
        quantity = int(request.form.get('quantity'))

        transfer_id, transfer_code = create_transfer_request(
            g.db, shortage_id, source_fac_id, dest_fac_id, medicine_id, batch_id, quantity, g.user
        )
        flash(f"Transfer Request {transfer_code} ({quantity} units) submitted for Authorized Approval!", "success")
        return redirect(url_for('transfers'))
    except Exception as e:
        flash(f"Transfer creation failed: {str(e)}", "error")
        return redirect(request.referrer or url_for('shortages'))

@app.route('/transfers/<int:transfer_id>/approve', methods=['POST'])
def approve_transfer_route(transfer_id):
    # Only approver, facility_manager, or platform_admin
    if g.user['role'] not in ('approver', 'facility_manager', 'platform_admin'):
        flash("Unauthorized: Only Authorized Approvers or Pharmacy Managers may approve transfers.", "error")
        return redirect(url_for('transfers'))

    try:
        comments = request.form.get('comments')
        approve_transfer(g.db, transfer_id, g.user, comments=comments)
        flash(f"Transfer #{transfer_id} officially authorized with regulatory digital signature! Batch stock is reserved at donor facility.", "success")
    except Exception as e:
        flash(f"Approval failed: {str(e)}", "error")

    return redirect(url_for('transfers'))

@app.route('/transfers/<int:transfer_id>/dispatch', methods=['POST'])
def dispatch_transfer_route(transfer_id):
    try:
        carrier = request.form.get('carrier', 'Direct Medical Courier')
        tracking_number = request.form.get('tracking_number', f"TRK-MED-{date.today().strftime('%d%H%M')}")
        dispatch_temp = float(request.form.get('dispatch_temperature', 4.0))
        notes = request.form.get('dispatch_notes')

        dispatch_transfer(g.db, transfer_id, g.user, carrier, tracking_number, dispatch_temp, notes)
        flash(f"Transfer #{transfer_id} dispatched! Stock deducted from donor inventory. Cold chain departure temp: {dispatch_temp}°C.", "success")
    except Exception as e:
        flash(f"Dispatch failed: {str(e)}", "error")

    return redirect(url_for('transfers'))

@app.route('/transfers/<int:transfer_id>/reconcile', methods=['POST'])
def reconcile_transfer_route(transfer_id):
    try:
        received_qty = int(request.form.get('received_quantity'))
        arrival_temp = float(request.form.get('arrival_temperature', 4.2))
        storage_location = request.form.get('storage_location', 'Primary Clinic Medication Refrigerator')
        notes = request.form.get('receipt_notes')
        discrepancy_reason = request.form.get('discrepancy_reason')

        receive_and_reconcile_transfer(
            g.db, transfer_id, g.user, received_qty, arrival_temp, storage_location, notes, discrepancy_reason
        )
        flash(f"Transfer #{transfer_id} received & reconciled! Inventory batch added to recipient facility. Audit ledger updated.", "success")
    except Exception as e:
        flash(f"Reconciliation failed: {str(e)}", "error")

    return redirect(url_for('transfers'))

@app.route('/forecasting')
def forecasting():
    # Advanced Engineering Challenge view
    user = g.user
    selected_fac = request.args.get('facility_id', type=int)
    
    forecasts = calculate_facility_forecast(g.db, facility_id=selected_fac if selected_fac != 0 else None)
    redistribution_suggestions = generate_network_redistribution_suggestions(g.db)
    facilities = [dict(r) for r in g.db.execute("SELECT * FROM facilities ORDER BY name").fetchall()]

    # Summary metrics
    critical_stockouts = [f for f in forecasts if f['risk_level'] == 'CRITICAL']
    total_waste_units = sum(f['total_forecasted_waste'] for f in forecasts)

    return render_template(
        'forecasting.html',
        forecasts=forecasts,
        redistribution_suggestions=redistribution_suggestions,
        facilities=facilities,
        selected_fac=selected_fac,
        critical_count=len(critical_stockouts),
        total_waste_units=total_waste_units
    )

@app.route('/audit')
def audit():
    verification = verify_ledger_integrity(g.db)
    
    events = [dict(r) for r in g.db.execute(
        """SELECT a.*, f.name as facility_name 
           FROM audit_events a
           LEFT JOIN facilities f ON a.facility_id = f.id
           ORDER BY a.id DESC LIMIT 100"""
    ).fetchall()]

    for e in events:
        try:
            e['payload_pretty'] = json.dumps(json.loads(e['payload_json']), indent=2)
        except Exception:
            e['payload_pretty'] = e['payload_json']

    return render_template('audit.html', events=events, verification=verification)

@app.route('/audit/verify')
def audit_verify_api():
    verification = verify_ledger_integrity(g.db)
    return jsonify(verification)

@app.route('/simulation')
def simulation():
    return render_template('simulation.html')

@app.route('/simulation/run', methods=['POST'])
def run_simulation():
    action = request.form.get('action')
    if action == 'reset':
        init_db(force_reseed=True)
        flash("System reset to baseline state with fictional medicine & facility test data.", "info")
    elif action == 'run_amoxicillin_rescue':
        # Executes the full end-to-end workflow:
        # 1. Shortage exists at Northside (Fac 2) for Amoxicillin
        # 2. Match with St. Jude (Fac 1) batch AMX-2024-081 (expiring in 28 days)
        # 3. Create transfer request for 40 units
        # 4. Dr. Elena Rostova approves
        # 5. Marcus Vance dispatches
        # 6. Dr. Sarah Chen receives and reconciles 40 units
        try:
            # Check existing open shortage
            shortage = g.db.execute(
                "SELECT * FROM shortage_requests WHERE requesting_facility_id = 2 AND medicine_id = 1 AND status = 'OPEN'"
            ).fetchone()
            shortage_id = shortage['id'] if shortage else None

            # Donor batch from St. Jude
            batch = g.db.execute(
                "SELECT * FROM batches WHERE facility_id = 1 AND medicine_id = 1 AND status = 'active'"
            ).fetchone()

            requester = dict(g.db.execute("SELECT * FROM users WHERE id = 3").fetchone())
            approver = dict(g.db.execute("SELECT * FROM users WHERE id = 4").fetchone())
            dispatcher = dict(g.db.execute("SELECT * FROM users WHERE id = 2").fetchone())
            receiver = requester

            # Step 1: Create Transfer
            trx_id, trx_code = create_transfer_request(
                g.db, shortage_id, 1, 2, 1, batch['id'], 40, requester
            )

            # Step 2: Approve
            approve_transfer(g.db, trx_id, approver, "Authorized under Emergency Pediatric Stock Rescue Protocol.")

            # Step 3: Dispatch
            dispatch_transfer(g.db, trx_id, dispatcher, "North Bay MedExpress Courier", "EXP-AMX-9941", 21.5, "Standard room-temperature secure transport box.")

            # Step 4: Receive & Reconcile
            receive_and_reconcile_transfer(
                g.db, trx_id, receiver, 40, 21.2, "Northside Dispensary - Bay 1, Shelf B",
                "Received all 40 bottles intact, seals verified, expiry date verified (28 days remaining).", None
            )

            flash(f"Simulation completed successfully! Full lifecycle of {trx_code} (Requested -> Approved -> Dispatched -> Reconciled) executed with batch deduction & cryptographic ledger linkage.", "success")
        except Exception as e:
            flash(f"Simulation error: {str(e)}", "error")

    elif action == 'run_cold_chain_insulin':
        # Simulates Insulin Glargine Cold-Chain transfer from St. Jude (Fac 1) to Sunrise Urgent Care (Fac 4)
        try:
            batch = g.db.execute("SELECT * FROM batches WHERE facility_id = 1 AND medicine_id = 2 AND status = 'active'").fetchone()
            requester = dict(g.db.execute("SELECT * FROM users WHERE id = 6").fetchone()) # Sunrise manager
            approver = dict(g.db.execute("SELECT * FROM users WHERE id = 4").fetchone())
            dispatcher = dict(g.db.execute("SELECT * FROM users WHERE id = 2").fetchone())
            receiver = requester

            trx_id, trx_code = create_transfer_request(g.db, None, 1, 4, 2, batch['id'], 20, requester)
            approve_transfer(g.db, trx_id, approver, "Cold chain certified: Validated continuous refrigerated transport compliance.")
            dispatch_transfer(g.db, trx_id, dispatcher, "PolarTemp Biocourier", "POLAR-88219", 3.8, "TempTale datalogger inserted inside vacuum-insulated cooler.")
            receive_and_reconcile_transfer(
                g.db, trx_id, receiver, 20, 4.1, "Sunrise Cold Refrigerator #1 [3.5°C]",
                "Cold chain maintained continuously (Departure: 3.8°C, Arrival: 4.1°C). No temp excursions.", None
            )
            flash(f"Cold-chain transfer {trx_code} simulated with validated temperature monitoring (3.8°C -> 4.1°C)!", "success")
        except Exception as e:
            flash(f"Simulation error: {str(e)}", "error")

    return redirect(url_for('transfers'))

# ----------------- JSON API ENDPOINTS ----------------- #

@app.route('/api/matches/<int:shortage_id>')
def api_matches(shortage_id):
    req_row = g.db.execute("SELECT * FROM shortage_requests WHERE id = ?", (shortage_id,)).fetchone()
    if not req_row:
        return jsonify({"error": "Shortage not found"}), 404
    candidates = find_eligible_donors(g.db, req_row['medicine_id'], req_row['requesting_facility_id'], req_row['required_quantity'])
    return jsonify({"shortage": dict(req_row), "matches": candidates})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"Starting MedSupply Rescue on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
