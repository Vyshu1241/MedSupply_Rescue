"""
MedSupply Rescue - Database Initialization and Seed Data
"""
import sqlite3
import os
import hashlib
import json
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'medsupply.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_audit_block(prev_hash, timestamp, entity_type, entity_id, action, payload_json):
    content = f"{prev_hash}|{timestamp}|{entity_type}|{entity_id}|{action}|{payload_json}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def ensure_demo_inventory(conn):
    """Keep enough sample batches at each demo facility to exercise inventory paging."""
    cursor = conn.cursor()
    if cursor.execute(
        "SELECT 1 FROM batches WHERE batch_number = 'AMX-2024-012'"
    ).fetchone() is None:
        return

    today = datetime.now().date()
    batches = [
        (1, 5, "ALB-2026-101", 36, 180, "Respiratory Cabinet A"),
        (1, 7, "OND-2026-102", 90, 240, "General Pharmacy Shelf 2"),
        (1, 8, "AZI-2026-103", 48, 210, "Main Pharmacy Bay 2"),
        (1, 1, "AMX-2026-104", 110, 150, "Main Pharmacy Bay 4 - Bin 15"),
        (1, 2, "INS-2026-105", 72, 190, "Cold Storage Refrigerator #3 [4.1°C]"),
        (1, 3, "EPI-2026-106", 32, 270, "Emergency Crash Cart Stock D"),
        (1, 8, "AZI-2026-107", 54, 300, "Main Pharmacy Bay 3"),
        (1, 7, "OND-2026-108", 72, 330, "Main Pharmacy Shelf 3"),
        (1, 1, "AMX-2026-109", 88, 125, "Main Pharmacy Bay 5"),
        (1, 2, "INS-2026-110", 40, 240, "Cold Storage Refrigerator #4 [3.9°C]"),
        (1, 4, "CEF-2026-111", 90, 400, "Inpatient Pharmacy Shelf 2A"),
        (1, 5, "ALB-2026-112", 52, 200, "Respiratory Cabinet B"),
        (1, 3, "EPI-2026-113", 24, 180, "Emergency Crash Cart Stock E"),
        (1, 6, "RAB-2026-114", 7, 300, "Cold Storage Refrigerator #5 [4.0°C]"),
        (1, 8, "AZI-2026-115", 64, 420, "Main Pharmacy Bay 6"),

        (2, 3, "EPI-2026-201", 14, 150, "Emergency Kit Cabinet"),
        (2, 4, "CEF-2026-202", 44, 220, "Clinic Main Room - Bay 5"),
        (2, 6, "RAB-2026-203", 8, 170, "Med Refrigerator Unit [3.7°C]"),
        (2, 8, "AZI-2026-204", 28, 260, "General Supply Room - Shelf 2"),
        (2, 1, "AMX-2026-205", 1, 200, "Clinic Main Room - Bay 4"),
        (2, 2, "INS-2026-206", 12, 210, "Med Refrigerator Unit [4.2°C]"),
        (2, 4, "CEF-2026-207", 32, 320, "Clinic Main Room - Bay 6"),
        (2, 5, "ALB-2026-208", 26, 230, "Pediatric Cart 3"),
        (2, 7, "OND-2026-209", 34, 290, "General Supply Room - Shelf 3"),
        (2, 8, "AZI-2026-210", 20, 330, "General Supply Room - Shelf 4"),
        (2, 1, "AMX-2026-211", 1, 180, "Clinic Main Room - Bay 7"),
        (2, 2, "INS-2026-212", 16, 280, "Med Refrigerator Unit [3.8°C]"),
        (2, 3, "EPI-2026-213", 10, 250, "Emergency Kit Cabinet 2"),
        (2, 5, "ALB-2026-214", 18, 310, "Pediatric Cart 4"),
        (2, 4, "CEF-2026-215", 38, 390, "Clinic Main Room - Bay 8"),
        (2, 1, "AMX-2026-216", 1, 350, "Clinic Main Room - Bay 9"),

        (3, 1, "AMX-2026-301", 18, 190, "Rural Dispensary Cabinet 2"),
        (3, 4, "CEF-2026-302", 20, 240, "Dispensary Shelf 4"),
        (3, 5, "ALB-2026-303", 12, 160, "Respiratory Supply Cabinet"),
        (3, 7, "OND-2026-304", 30, 280, "Dispensary Cabinet 4"),
        (3, 8, "AZI-2026-305", 22, 200, "Dispensary Cabinet 5"),
        (3, 3, "EPI-2026-306", 6, 125, "Emergency Kit Cabinet 2"),
        (3, 4, "CEF-2026-307", 16, 360, "Dispensary Shelf 5"),
        (3, 5, "ALB-2026-308", 10, 310, "Respiratory Supply Cabinet 2"),
        (3, 8, "AZI-2026-309", 18, 330, "Dispensary Cabinet 6"),
        (3, 7, "OND-2026-310", 24, 290, "Dispensary Cabinet 7"),
        (3, 1, "AMX-2026-311", 14, 180, "Rural Dispensary Cabinet 3"),
        (3, 4, "CEF-2026-312", 18, 390, "Dispensary Shelf 6"),
        (3, 5, "ALB-2026-313", 8, 220, "Respiratory Supply Cabinet 3"),
        (3, 3, "EPI-2026-314", 4, 250, "Emergency Kit Cabinet 3"),
        (3, 1, "AMX-2026-315", 16, 350, "Rural Dispensary Cabinet 4"),
        (3, 4, "CEF-2026-316", 12, 420, "Dispensary Shelf 7"),
        (3, 7, "OND-2026-317", 20, 370, "Dispensary Cabinet 8"),

        (4, 4, "CEF-2026-401", 40, 260, "Urgent Care Pharmacy Shelf 2"),
        (4, 5, "ALB-2026-402", 24, 190, "Respiratory Cabinet B"),
        (4, 6, "RAB-2026-403", 10, 210, "Cold Refrigerator [3.9°C]"),
        (4, 7, "OND-2026-404", 45, 320, "General Supply Room - Shelf 1"),
        (4, 8, "AZI-2026-405", 30, 240, "Urgent Care Pharmacy Shelf 3"),
        (4, 1, "AMX-2026-406", 55, 170, "Urgent Care Pharmacy Shelf 4"),
        (4, 3, "EPI-2026-407", 18, 300, "Resuscitation Suite - Cabinet 2"),
        (4, 4, "CEF-2026-408", 36, 400, "Urgent Care Pharmacy Shelf 5"),
        (4, 8, "AZI-2026-409", 26, 330, "Urgent Care Pharmacy Shelf 6"),
        (4, 7, "OND-2026-410", 36, 290, "General Supply Room - Shelf 2"),
        (4, 1, "AMX-2026-411", 48, 180, "Urgent Care Pharmacy Shelf 7"),
        (4, 4, "CEF-2026-412", 30, 390, "Urgent Care Pharmacy Shelf 8"),
        (4, 2, "INS-2026-413", 22, 280, "Cold Refrigerator #2 [4.0°C]"),
        (4, 3, "EPI-2026-414", 14, 250, "Resuscitation Suite - Cabinet 3"),
        (4, 5, "ALB-2026-415", 20, 310, "Respiratory Cabinet C"),
        (4, 6, "RAB-2026-416", 8, 350, "Cold Refrigerator #3 [3.8°C]"),
        (4, 8, "AZI-2026-417", 24, 420, "Urgent Care Pharmacy Shelf 9"),

        (5, 1, "AMX-2026-501", 240, 260, "Central Warehouse Bay 4"),
        (5, 3, "EPI-2026-502", 70, 220, "Emergency Supply Vault"),
        (5, 5, "ALB-2026-503", 120, 310, "Respiratory Stock Bay 2"),
        (5, 7, "OND-2026-504", 160, 280, "Central Warehouse Bay 6"),
        (5, 8, "AZI-2026-505", 100, 350, "Central Warehouse Bay 7"),
        (5, 2, "INS-2026-506", 220, 320, "Central Cold Vault #4 [3.4°C]"),
        (5, 4, "CEF-2026-507", 300, 420, "Central Warehouse Bay 10"),
        (5, 6, "RAB-2026-508", 36, 240, "Central Cold Vault #2 [3.1°C]"),
        (5, 4, "CEF-2026-509", 260, 390, "Central Warehouse Bay 11"),
        (5, 2, "INS-2026-510", 180, 280, "Central Cold Vault #5 [3.6°C]"),
        (5, 1, "AMX-2026-511", 200, 180, "Central Warehouse Bay 12"),
        (5, 3, "EPI-2026-512", 56, 250, "Emergency Supply Vault 2"),
        (5, 5, "ALB-2026-513", 90, 310, "Respiratory Stock Bay 3"),
        (5, 8, "AZI-2026-514", 84, 330, "Central Warehouse Bay 13"),
        (5, 7, "OND-2026-515", 120, 290, "Central Warehouse Bay 14"),
        (5, 6, "RAB-2026-516", 28, 350, "Central Cold Vault #6 [3.2°C]"),
        (5, 4, "CEF-2026-517", 240, 420, "Central Warehouse Bay 15"),
    ]

    for facility_id, medicine_id, batch_number, quantity, expiry_days, location in batches:
        if cursor.execute(
            "SELECT 1 FROM batches WHERE batch_number = ?", (batch_number,)
        ).fetchone():
            continue
        cursor.execute(
            """INSERT INTO batches (
                   medicine_id, facility_id, batch_number, initial_quantity,
                   current_quantity, reserved_quantity, manufacture_date,
                   expiry_date, storage_location, status
               ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, 'active')""",
            (
                medicine_id, facility_id, batch_number, quantity, quantity,
                (today - timedelta(days=90)).isoformat(),
                (today + timedelta(days=expiry_days)).isoformat(), location
            )
        )

    for batch_number, previous_quantity in (
        ("AMX-2026-205", 24),
        ("AMX-2026-211", 30),
        ("AMX-2026-216", 22),
    ):
        cursor.execute(
            """UPDATE batches
               SET initial_quantity = 1, current_quantity = 1
               WHERE batch_number = ? AND initial_quantity = ?
                 AND current_quantity = ? AND reserved_quantity = 0""",
            (batch_number, previous_quantity, previous_quantity)
        )

def ensure_demo_transfer_pipeline(conn):
    """Seed each transfer state through the same services used by application actions."""
    cursor = conn.cursor()
    if cursor.execute("SELECT 1 FROM transfer_requests LIMIT 1").fetchone():
        return

    from services.inventory import (
        create_transfer_request, approve_transfer, dispatch_transfer,
        receive_and_reconcile_transfer
    )

    users = {
        row['id']: dict(row)
        for row in cursor.execute("SELECT * FROM users").fetchall()
    }

    def batch_id(batch_number):
        row = cursor.execute(
            "SELECT id FROM batches WHERE batch_number = ?", (batch_number,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Missing demo batch required for transfer: {batch_number}")
        return row['id']

    create_transfer_request(
        conn, 1, 1, 2, 1, batch_id("AMX-2024-081"), 30, users[3]
    )

    approved_id, _ = create_transfer_request(
        conn, 2, 1, 3, 3, batch_id("EPI-2024-009"), 10, users[5]
    )
    approve_transfer(
        conn, approved_id, users[4],
        "Demo approval: authorized for the Valley Hope emergency shortage."
    )

    dispatched_id, _ = create_transfer_request(
        conn, None, 1, 4, 4, batch_id("CEF-2024-301"), 16, users[6]
    )
    approve_transfer(
        conn, dispatched_id, users[4],
        "Demo approval: ambient transport requirements verified."
    )
    dispatch_transfer(
        conn, dispatched_id, users[2], "Regional Medical Courier",
        "DEMO-CEF-4102", 21.5, "Sealed ambient shipment; temperature monitor attached."
    )

    reconciled_id, _ = create_transfer_request(
        conn, None, 1, 4, 7, batch_id("OND-2026-102"), 12, users[6]
    )
    approve_transfer(
        conn, reconciled_id, users[4],
        "Demo approval: quantity and ambient storage verified."
    )
    dispatch_transfer(
        conn, reconciled_id, users[2], "Regional Medical Courier",
        "DEMO-OND-4103", 21.2, "Sealed ambient shipment."
    )
    receive_and_reconcile_transfer(
        conn, reconciled_id, users[6], 12, 21.4,
        "Main Clinic Medication Room - Bay 2",
        "Demo receipt: all units received and batch details verified."
    )

def init_db(force_reseed=False):
    db_exists = os.path.exists(DB_PATH)
    conn = get_db_connection()
    cursor = conn.cursor()

    if force_reseed or not db_exists or cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facilities'").fetchone() is None:
        with open(SCHEMA_PATH, 'r') as f:
            cursor.executescript(f.read())
        conn.commit()
        seed_data(conn)
    else:
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS saved_workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 50),
                view_type TEXT NOT NULL CHECK (
                    view_type IN ('expiry_watchlist', 'inventory', 'shortages', 'transfers', 'forecasting')
                ),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (owner_user_id, name COLLATE NOCASE)
            )"""
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_saved_workspaces_owner ON saved_workspaces(owner_user_id, id)"
        )
        ensure_demo_inventory(conn)
        conn.commit()

        # Check if empty
        row = cursor.execute("SELECT count(*) as count FROM facilities").fetchone()
        if row['count'] == 0:
            seed_data(conn)
        else:
            ensure_demo_transfer_pipeline(conn)
            conn.commit()
    
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    
    # Clear tables
    for table in [
        'saved_workspaces', 'audit_events', 'approvals', 'transfer_requests', 'shortage_requests',
        'stock_movements', 'daily_consumption', 'batches', 'medicines',
        'users', 'facilities', 'redistribution_recommendations'
    ]:
        cursor.execute(f"DELETE FROM {table}")

    cursor.execute("PRAGMA foreign_keys = ON")

    # 1. Facilities
    facilities = [
        (1, "St. Jude Regional Medical Center", "Hospital", "HOSP-REG-8472", "450 Medical Heights Blvd", "Metro City", "Central", "inventory@stjude-health.org", "+1 (555) 234-5670", 1, 37.7749, -122.4194),
        (2, "Northside Community Clinic", "Community Clinic", "CLIN-COMM-1093", "1200 North Willow St", "North Hills", "North", "pharmacy@northside-clinic.org", "+1 (555) 987-6543", 1, 37.8044, -122.2712),
        (3, "Valley Hope Rural Dispensary", "Dispensary", "DISP-RURL-0481", "88 Country Ridge Rd", "Oakdale Valley", "East", "care@valleyhope-rx.org", "+1 (555) 432-8765", 0, 37.9577, -121.9552),
        (4, "Sunrise Urgent Care Center", "Urgent Care", "URG-CARE-3329", "740 Sunrise Parkway", "Metro City", "South", "supplies@sunrise-urgent.com", "+1 (555) 345-6789", 1, 37.6879, -122.4702),
        (5, "Metro Central Distribution Pharmacy", "Regional Pharmacy", "PHAR-DIST-9901", "10 Logistics Way", "Metro City", "Central", "logistics@metropharm-hub.gov", "+1 (555) 111-2233", 1, 37.7338, -122.3847),
    ]
    cursor.executemany(
        """INSERT INTO facilities (id, name, facility_type, license_number, address, city, region, contact_email, contact_phone, has_cold_chain, latitude, longitude)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        facilities
    )

    # 2. Users (Role-based accounts)
    # Default password for all demo users is 'Rescue2026!'
    pwd_hash = generate_password_hash("Rescue2026!", method="pbkdf2:sha256")
    users = [
        (1, "admin", pwd_hash, "Alex Mercer", "platform_admin", None, "alex.mercer@medsupply-network.org", "LIC-SYS-001"),
        (2, "stjude_mgr", pwd_hash, "Marcus Vance", "facility_manager", 1, "marcus.vance@stjude-health.org", "PHARM-LIC-4491"),
        (3, "northside_staff", pwd_hash, "Dr. Sarah Chen", "staff", 2, "sarah.chen@northside-clinic.org", "MD-LIC-9812"),
        (4, "approver_elena", pwd_hash, "Dr. Elena Rostova", "approver", 5, "elena.rostova@regulator-health.gov", "REG-OFFICER-771"),
        (5, "valley_staff", pwd_hash, "Nurse David Miller", "staff", 3, "david.miller@valleyhope-rx.org", "RN-LIC-3291"),
        (6, "sunrise_mgr", pwd_hash, "Rachel Gomez", "facility_manager", 4, "rachel.gomez@sunrise-urgent.com", "PHARM-LIC-6512"),
    ]
    cursor.executemany(
        """INSERT INTO users (id, username, password_hash, full_name, role, facility_id, email, license_or_badge)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        users
    )

    # 3. Medicines
    medicines = [
        (1, "Amoxicillin / Clavulanate", "Augmentin", "NDC-0029-6085-39", "Antibiotics", "Oral Suspension", "250mg/5mL (100mL)", "Bottles", "Room Temperature (15-25°C)", 30, 5),
        (2, "Insulin Glargine (rDNA origin)", "Lantus SoloStar", "NDC-0088-2219-05", "Insulin & Diabetes", "Prefilled Syringe", "100 U/mL (3mL)", "Boxes of 5", "Cold Chain (2-8°C)", 25, 7),
        (3, "Epinephrine Auto-Injector", "EpiPen Adult", "NDC-49502-500-02", "Emergency & Critical Care", "Injection", "0.3mg (0.3mL)", "Boxes of 2", "Room Temperature (15-25°C)", 15, 10),
        (4, "Ceftriaxone Sodium", "Rocephin", "NDC-0004-1965-02", "Antibiotics", "Vial", "1g Powder for Reconstitution", "Vials", "Room Temperature (15-25°C)", 40, 6),
        (5, "Albuterol Sulfate Inhalation Aerosol", "ProAir HFA", "NDC-59310-579-22", "Respiratory", "Inhaler", "90mcg/actuation (8.5g)", "Inhalers", "Room Temperature (15-25°C)", 20, 8),
        (6, "Human Rabies Immune Globulin", "HyperRAB", "NDC-13533-618-10", "Emergency & Critical Care", "Vial", "300 IU/mL (1mL)", "Vials", "Cold Chain (2-8°C)", 10, 14),
        (7, "Ondansetron Hydrochloride", "Zofran ODT", "NDC-0173-0569-00", "Critical Care", "Tablet", "4mg Orally Disintegrating", "Boxes of 30", "Room Temperature (15-25°C)", 35, 4),
        (8, "Azithromycin Dihydrate", "Zithromax", "NDC-0069-3060-75", "Antibiotics", "Tablet", "250mg", "Boxes of 6", "Room Temperature (15-25°C)", 25, 5),
    ]
    cursor.executemany(
        """INSERT INTO medicines (id, generic_name, brand_name, ndc_or_code, therapeutic_category, dosage_form, strength, unit_of_measure, storage_requirement, min_safety_stock_default, standard_lead_time_days)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        medicines
    )

    # 4. Batches
    # Today's date reference
    today = datetime.now().date()
    
    # We create a realistic spread:
    # - St. Jude (Fac 1) has excess Amoxicillin expiring in 28 days! (Ideal candidate for transfer)
    # - St. Jude (Fac 1) has Insulin expiring in 45 days (Cold chain)
    # - Northside (Fac 2) has critically low Amoxicillin (only 4 bottles left) and high demand!
    # - Valley Hope (Fac 3) needs Epinephrine (only 2 boxes left, 2 weeks lead time)
    # - Sunrise (Fac 4) has stable inventory
    # - Metro Dist Hub (Fac 5) has reserve stock
    batches = [
        # Fac 1: St. Jude Hospital
        (1, 1, 1, "AMX-2024-081", 300, 185, 0, (today - timedelta(days=150)).isoformat(), (today + timedelta(days=28)).isoformat(), "Main Pharmacy Bay 4 - Bin 12", "active"),
        (2, 2, 1, "INS-2024-114", 150, 92, 0, (today - timedelta(days=90)).isoformat(), (today + timedelta(days=45)).isoformat(), "Cold Storage Refrigerator #1 [3.8°C]", "active"),
        (3, 3, 1, "EPI-2024-009", 80, 55, 0, (today - timedelta(days=120)).isoformat(), (today + timedelta(days=210)).isoformat(), "Emergency Crash Cart Stock C", "active"),
        (4, 4, 1, "CEF-2024-301", 200, 140, 0, (today - timedelta(days=60)).isoformat(), (today + timedelta(days=320)).isoformat(), "Inpatient Pharmacy Shelf 1A", "active"),
        (5, 6, 1, "RAB-2024-002", 20, 14, 0, (today - timedelta(days=40)).isoformat(), (today + timedelta(days=85)).isoformat(), "Cold Storage Refrigerator #2 [4.1°C]", "active"),

        # Fac 2: Northside Community Clinic (Shortage of Amoxicillin!)
        (6, 1, 2, "AMX-2024-012", 100, 4, 0, (today - timedelta(days=180)).isoformat(), (today + timedelta(days=15)).isoformat(), "Clinic Dispensary Aisle 1", "active"),
        (7, 2, 2, "INS-2024-040", 40, 18, 0, (today - timedelta(days=100)).isoformat(), (today + timedelta(days=120)).isoformat(), "Med Refrigerator Unit [4.0°C]", "active"),
        (8, 5, 2, "ALB-2024-220", 60, 42, 0, (today - timedelta(days=80)).isoformat(), (today + timedelta(days=240)).isoformat(), "Pediatric Cart 2", "active"),
        (9, 7, 2, "OND-2024-501", 80, 65, 0, (today - timedelta(days=45)).isoformat(), (today + timedelta(days=360)).isoformat(), "General Supply Room", "active"),

        # Fac 3: Valley Hope Rural Dispensary (No cold chain, shortage of Epinephrine!)
        (10, 1, 3, "AMX-2024-099", 50, 22, 0, (today - timedelta(days=70)).isoformat(), (today + timedelta(days=140)).isoformat(), "Rural Dispensary Cabinet 1", "active"),
        (11, 3, 3, "EPI-2023-882", 25, 2, 0, (today - timedelta(days=300)).isoformat(), (today + timedelta(days=20)).isoformat(), "Urgent Box - Desk", "active"),
        (12, 8, 3, "AZI-2024-118", 40, 31, 0, (today - timedelta(days=30)).isoformat(), (today + timedelta(days=400)).isoformat(), "Dispensary Cabinet 3", "active"),

        # Fac 4: Sunrise Urgent Care
        (13, 1, 4, "AMX-2024-055", 120, 75, 0, (today - timedelta(days=90)).isoformat(), (today + timedelta(days=180)).isoformat(), "Urgent Care Pharmacy", "active"),
        (14, 2, 4, "INS-2024-092", 50, 34, 0, (today - timedelta(days=60)).isoformat(), (today + timedelta(days=95)).isoformat(), "Cold Refrigerator [3.5°C]", "active"),
        (15, 3, 4, "EPI-2024-015", 30, 20, 0, (today - timedelta(days=50)).isoformat(), (today + timedelta(days=280)).isoformat(), "Resuscitation Suite", "active"),

        # Fac 5: Metro Central Hub (High safety stock)
        (16, 2, 5, "INS-2024-001", 500, 380, 0, (today - timedelta(days=30)).isoformat(), (today + timedelta(days=260)).isoformat(), "Central Cold Vault #3 [3.0°C]", "active"),
        (17, 4, 5, "CEF-2024-100", 600, 520, 0, (today - timedelta(days=20)).isoformat(), (today + timedelta(days=450)).isoformat(), "Central Warehouse Bay 9", "active"),
        (18, 6, 5, "RAB-2024-009", 50, 42, 0, (today - timedelta(days=15)).isoformat(), (today + timedelta(days=180)).isoformat(), "Central Cold Vault #1 [2.5°C]", "active"),
    ]
    cursor.executemany(
        """INSERT INTO batches (id, medicine_id, facility_id, batch_number, initial_quantity, current_quantity, reserved_quantity, manufacture_date, expiry_date, storage_location, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        batches
    )
    ensure_demo_inventory(conn)

    # 5. Historical Consumption (30 days of daily dispense data for forecasting)
    # St. Jude consumes ~3-5 bottles of Amoxicillin/day, but has 185 bottles expiring in 28 days -> Expiry waste risk: ~70 bottles!
    # Northside consumes ~6-9 bottles of Amoxicillin/day, current stock is 4 -> Stockout in < 1 day!
    consumption_records = []
    base_date = today - timedelta(days=30)
    import random
    random.seed(42)

    # St. Jude Amoxicillin (Fac 1, Med 1)
    for i in range(30):
        c_date = (base_date + timedelta(days=i)).isoformat()
        qty = random.randint(3, 5)
        consumption_records.append((1, 1, c_date, qty, 220 - (i * 2)))

    # St. Jude Insulin (Fac 1, Med 2)
    for i in range(30):
        c_date = (base_date + timedelta(days=i)).isoformat()
        qty = random.randint(1, 2)
        consumption_records.append((1, 2, c_date, qty, 110 - i))

    # Northside Amoxicillin (Fac 2, Med 1) - High consumption
    for i in range(30):
        c_date = (base_date + timedelta(days=i)).isoformat()
        qty = random.randint(6, 10)
        consumption_records.append((2, 1, c_date, qty, max(4, 90 - (i * 3))))

    # Northside Insulin (Fac 2, Med 2)
    for i in range(30):
        c_date = (base_date + timedelta(days=i)).isoformat()
        qty = random.randint(2, 4)
        consumption_records.append((2, 2, c_date, qty, 35 - i))

    # Valley Hope Epinephrine (Fac 3, Med 3)
    for i in range(30):
        c_date = (base_date + timedelta(days=i)).isoformat()
        qty = 1 if i % 4 == 0 else 0
        consumption_records.append((3, 3, c_date, qty, max(2, 10 - (i // 4))))

    cursor.executemany(
        """INSERT INTO daily_consumption (facility_id, medicine_id, consumption_date, quantity_dispensed, stock_end_of_day)
           VALUES (?, ?, ?, ?, ?)""",
        consumption_records
    )

    # 6. Active Shortage Request
    # Northside requesting 40 bottles of Amoxicillin (Urgency: CRITICAL)
    shortage_code = "SR-2024-001"
    cursor.execute(
        """INSERT INTO shortage_requests (id, request_code, requesting_facility_id, requested_by_user_id, medicine_id, required_quantity, urgency, clinical_justification, status, needed_by_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, shortage_code, 2, 3, 1, 40, "CRITICAL", 
         "Outbreak of pediatric streptococcal pharyngitis in North District. Facility current stock is down to 4 bottles (under 24h supply). Commercial wholesaler backordered 14 days.",
         "OPEN", (today + timedelta(days=2)).isoformat(), datetime.now().isoformat())
    )

    # Valley Hope requesting 10 Epinephrine units
    cursor.execute(
        """INSERT INTO shortage_requests (id, request_code, requesting_facility_id, requested_by_user_id, medicine_id, required_quantity, urgency, clinical_justification, status, needed_by_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (2, "SR-2024-002", 3, 5, 3, 10, "HIGH",
         "Rural dispensary emergency anaphylaxis kits expiring this month. High seasonal bee sting risks during harvest. Primary supplier delivery delayed.",
         "OPEN", (today + timedelta(days=4)).isoformat(), (datetime.now() - timedelta(hours=5)).isoformat())
    )

    # 7. Initial Immutable Audit Chain (Genesis block + seed events)
    genesis_timestamp = (datetime.now() - timedelta(days=1)).isoformat()
    genesis_payload = json.dumps({"description": "MedSupply Rescue Ledger Initialized with Verified Master Catalogue"}, sort_keys=True)
    genesis_hash = hash_audit_block("0"*64, genesis_timestamp, "SYSTEM", "0", "INIT", genesis_payload)

    cursor.execute(
        """INSERT INTO audit_events (id, event_uuid, timestamp, facility_id, user_id, user_name, user_role, entity_type, entity_id, action, payload_json, previous_hash, current_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, "evt-00000001", genesis_timestamp, 5, 1, "Alex Mercer", "platform_admin", "SYSTEM", "0", "INIT", genesis_payload, "0"*64, genesis_hash)
    )

    # Event 2: Shortage Request Logged
    evt2_time = datetime.now().isoformat()
    evt2_payload = json.dumps({
        "facility": "Northside Community Clinic",
        "medicine": "Amoxicillin / Clavulanate",
        "quantity": 40,
        "shortage_code": shortage_code,
        "urgency": "CRITICAL"
    }, sort_keys=True)
    evt2_hash = hash_audit_block(genesis_hash, evt2_time, "SHORTAGE", shortage_code, "CREATE", evt2_payload)
    cursor.execute(
        """INSERT INTO audit_events (id, event_uuid, timestamp, facility_id, user_id, user_name, user_role, entity_type, entity_id, action, payload_json, previous_hash, current_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (2, "evt-00000002", evt2_time, 2, 3, "Dr. Sarah Chen", "staff", "SHORTAGE", shortage_code, "CREATE", evt2_payload, genesis_hash, evt2_hash)
    )

    ensure_demo_transfer_pipeline(conn)
    conn.commit()
    print("Database initialized and successfully seeded with realistic healthcare scenarios!")

if __name__ == '__main__':
    init_db(force_reseed=True)
