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
        # Check if empty
        row = cursor.execute("SELECT count(*) as count FROM facilities").fetchone()
        if row['count'] == 0:
            seed_data(conn)
    
    conn.close()

def seed_data(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    
    # Clear tables
    for table in [
        'audit_events', 'approvals', 'transfer_requests', 'shortage_requests',
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

    conn.commit()
    print("Database initialized and successfully seeded with realistic healthcare scenarios!")

if __name__ == '__main__':
    init_db(force_reseed=True)
