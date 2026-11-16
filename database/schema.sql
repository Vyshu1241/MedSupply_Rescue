-- MedSupply Rescue Database Schema
-- Facility-to-Facility Medicine Stock Visibility & Transfer Coordination

PRAGMA foreign_keys = ON;

-- 1. Facilities
CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    facility_type TEXT NOT NULL, -- 'Hospital', 'Community Clinic', 'Urgent Care', 'Regional Pharmacy', 'Dispensary'
    license_number TEXT NOT NULL UNIQUE,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    region TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    has_cold_chain INTEGER DEFAULT 1, -- 1 = Yes, 0 = No
    latitude REAL,
    longitude REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. Users
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL, -- 'platform_admin', 'facility_manager', 'approver', 'staff'
    facility_id INTEGER REFERENCES facilities(id),
    email TEXT NOT NULL,
    license_or_badge TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Medicine Catalogue
CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generic_name TEXT NOT NULL,
    brand_name TEXT,
    ndc_or_code TEXT UNIQUE NOT NULL,
    therapeutic_category TEXT NOT NULL, -- 'Antibiotics', 'Insulin & Diabetes', 'Emergency & Critical Care', 'Cardiovascular', 'Respiratory'
    dosage_form TEXT NOT NULL, -- 'Tablet', 'Vial', 'Oral Suspension', 'Inhaler', 'Ampoule', 'Prefilled Syringe'
    strength TEXT NOT NULL,
    unit_of_measure TEXT NOT NULL, -- 'Vials', 'Boxes of 30', 'Bottles (100ml)', 'Ampoules'
    storage_requirement TEXT NOT NULL, -- 'Cold Chain (2-8°C)', 'Room Temperature (15-25°C)', 'Frozen (-20°C)', 'Secure/Controlled Room'
    min_safety_stock_default INTEGER DEFAULT 20,
    standard_lead_time_days INTEGER DEFAULT 7,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. Medicine Batches (Batch-level Inventory)
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    batch_number TEXT NOT NULL,
    initial_quantity INTEGER NOT NULL,
    current_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER DEFAULT 0,
    manufacture_date DATE,
    expiry_date DATE NOT NULL,
    storage_location TEXT, -- e.g. 'Cold Storage Refrigerator #2', 'Main Aisle Shelf 3B'
    status TEXT DEFAULT 'active', -- 'active', 'reserved', 'quarantined', 'expired', 'transferred_out'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 5. Historical Daily Consumption (For Forecasting Challenge)
CREATE TABLE IF NOT EXISTS daily_consumption (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    consumption_date DATE NOT NULL,
    quantity_dispensed INTEGER NOT NULL,
    stock_end_of_day INTEGER NOT NULL
);

-- 6. Shortage Requests
CREATE TABLE IF NOT EXISTS shortage_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_code TEXT UNIQUE NOT NULL,
    requesting_facility_id INTEGER NOT NULL REFERENCES facilities(id),
    requested_by_user_id INTEGER NOT NULL REFERENCES users(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    required_quantity INTEGER NOT NULL,
    urgency TEXT NOT NULL, -- 'CRITICAL' (<24h), 'HIGH' (<72h), 'MEDIUM' (<7d), 'LOW' (<14d)
    clinical_justification TEXT NOT NULL,
    status TEXT DEFAULT 'OPEN', -- 'OPEN', 'MATCHED', 'IN_TRANSFER', 'FULFILLED', 'CANCELLED'
    needed_by_date DATE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 7. Transfer Requests (State Machine Workflow)
CREATE TABLE IF NOT EXISTS transfer_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_code TEXT UNIQUE NOT NULL,
    shortage_request_id INTEGER REFERENCES shortage_requests(id),
    source_facility_id INTEGER NOT NULL REFERENCES facilities(id),
    dest_facility_id INTEGER NOT NULL REFERENCES facilities(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    quantity INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL', 
    -- 'PENDING_APPROVAL' -> 'APPROVED' -> 'DISPATCHED' -> 'RECEIVED' -> 'RECONCILED' / 'REJECTED' / 'CANCELLED'
    requester_id INTEGER REFERENCES users(id),
    approver_id INTEGER REFERENCES users(id),
    dispatched_by_id INTEGER REFERENCES users(id),
    received_by_id INTEGER REFERENCES users(id),
    cold_chain_required INTEGER DEFAULT 0,
    dispatch_temperature REAL,
    arrival_temperature REAL,
    tracking_number TEXT,
    carrier TEXT,
    dispatch_notes TEXT,
    receipt_notes TEXT,
    received_quantity INTEGER,
    discrepancy_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME,
    dispatched_at DATETIME,
    received_at DATETIME,
    completed_at DATETIME
);

-- 8. Approvals Record
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_request_id INTEGER NOT NULL REFERENCES transfer_requests(id),
    approver_id INTEGER NOT NULL REFERENCES users(id),
    approval_status TEXT NOT NULL, -- 'APPROVED', 'REJECTED'
    signature_hash TEXT NOT NULL,
    regulatory_check_passed INTEGER DEFAULT 1,
    cold_chain_certified INTEGER DEFAULT 1,
    comments TEXT,
    approved_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 9. Stock Movement Log (Inventory Ledgers)
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    movement_type TEXT NOT NULL, -- 'INITIAL_LOAD', 'DISPENSE', 'TRANSFER_OUT', 'TRANSFER_IN', 'ADJUSTMENT', 'RESERVATION'
    quantity_delta INTEGER NOT NULL,
    reference_id TEXT,
    performed_by_id INTEGER REFERENCES users(id),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 10. Immutable Audit Trail (Tamper-Evident SHA-256 Hash Chain)
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT UNIQUE NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    facility_id INTEGER REFERENCES facilities(id),
    user_id INTEGER REFERENCES users(id),
    user_name TEXT NOT NULL,
    user_role TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- 'BATCH', 'TRANSFER', 'SHORTAGE', 'STOCK', 'APPROVAL', 'SYSTEM'
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL, -- 'CREATE', 'UPDATE', 'APPROVE', 'DISPATCH', 'RECEIVE', 'RECONCILE', 'ADJUST'
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    current_hash TEXT NOT NULL
);

-- 11. Automated Redistribution Recommendations (AI/Forecasting Module)
CREATE TABLE IF NOT EXISTS redistribution_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_facility_id INTEGER NOT NULL REFERENCES facilities(id),
    dest_facility_id INTEGER NOT NULL REFERENCES facilities(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    suggested_quantity INTEGER NOT NULL,
    source_expiry_date DATE NOT NULL,
    days_to_expiry INTEGER NOT NULL,
    forecasted_waste_units INTEGER NOT NULL,
    dest_days_of_supply REAL NOT NULL,
    priority_score REAL NOT NULL,
    status TEXT DEFAULT 'PROPOSED', -- 'PROPOSED', 'ACCEPTED', 'DISMISSED'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for high-speed queries
CREATE INDEX IF NOT EXISTS idx_batches_med_fac ON batches(medicine_id, facility_id, status);
CREATE INDEX IF NOT EXISTS idx_batches_expiry ON batches(expiry_date);
CREATE INDEX IF NOT EXISTS idx_transfers_status ON transfer_requests(status);
CREATE INDEX IF NOT EXISTS idx_shortages_status ON shortage_requests(status);
CREATE INDEX IF NOT EXISTS idx_consumption_date ON daily_consumption(facility_id, medicine_id, consumption_date);
