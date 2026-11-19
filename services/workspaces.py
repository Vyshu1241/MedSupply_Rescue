"""Read-only data views used by personal workspaces."""
from services.forecasting import calculate_facility_forecast
from services.inventory import get_facility_inventory

WORKSPACE_VIEWS = {
    'expiry_watchlist': 'Expiry watchlist',
    'inventory': 'Batch inventory',
    'shortages': 'Shortage requests',
    'transfers': 'Transfer pipeline',
    'forecasting': 'Forecasts'
}

WORKSPACE_COLUMNS = {
    'expiry_watchlist': [
        ('Facility', 'facility_name'),
        ('Medicine', 'generic_name'),
        ('Strength', 'strength'),
        ('Batch', 'batch_number'),
        ('Available', 'available_quantity'),
        ('Expiry date', 'expiry_date'),
        ('Days left', 'days_to_expiry'),
        ('Status', 'expiry_status')
    ],
    'inventory': [
        ('Facility', 'facility_name'),
        ('Medicine', 'generic_name'),
        ('Strength', 'strength'),
        ('Batch', 'batch_number'),
        ('Available', 'available_quantity'),
        ('Reserved', 'reserved_quantity'),
        ('Expiry date', 'expiry_date'),
        ('Storage location', 'storage_location')
    ],
    'shortages': [
        ('Request', 'request_code'),
        ('Facility', 'facility_name'),
        ('Medicine', 'generic_name'),
        ('Strength', 'strength'),
        ('Quantity needed', 'required_quantity'),
        ('Urgency', 'urgency'),
        ('Status', 'status'),
        ('Needed by', 'needed_by_date')
    ],
    'transfers': [
        ('Transfer', 'transfer_code'),
        ('Medicine', 'generic_name'),
        ('Source', 'source_facility'),
        ('Destination', 'dest_facility'),
        ('Quantity', 'quantity'),
        ('Status', 'status'),
        ('Created', 'created_at')
    ],
    'forecasting': [
        ('Facility', 'facility_name'),
        ('Medicine', 'generic_name'),
        ('Available stock', 'available_stock'),
        ('Burn rate / day', 'daily_burn_rate'),
        ('Days of supply', 'days_of_supply'),
        ('Lead time', 'lead_time_days'),
        ('Risk', 'stockout_status'),
        ('Expiry waste risk', 'total_forecasted_waste')
    ]
}


def get_workspace_view(conn, view_type, user):
    """Return column definitions and live records for a supported saved view."""
    if view_type not in WORKSPACE_VIEWS:
        raise ValueError(f"Unsupported workspace view: {view_type}")

    if view_type in ('expiry_watchlist', 'inventory'):
        facility_id = None
        if user and user.get('role') != 'platform_admin':
            facility_id = user.get('facility_id')
        records = get_facility_inventory(conn, facility_id=facility_id)

        if view_type == 'expiry_watchlist':
            records = [
                row for row in records
                if row['status'] == 'active'
                and row['current_quantity'] > 0
                and 0 <= row['days_to_expiry'] <= 60
            ]
    elif view_type == 'shortages':
        records = [
            dict(row) for row in conn.execute(
                """SELECT s.request_code, f.name AS facility_name, m.generic_name,
                          m.strength, s.required_quantity, s.urgency, s.status,
                          s.needed_by_date
                   FROM shortage_requests s
                   JOIN facilities f ON f.id = s.requesting_facility_id
                   JOIN medicines m ON m.id = s.medicine_id
                   ORDER BY CASE s.urgency
                       WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                       WHEN 'MEDIUM' THEN 3 ELSE 4 END, s.id DESC"""
            ).fetchall()
        ]
    elif view_type == 'transfers':
        records = [
            dict(row) for row in conn.execute(
                """SELECT t.transfer_code, m.generic_name, sf.name AS source_facility,
                          df.name AS dest_facility, t.quantity, t.status, t.created_at
                   FROM transfer_requests t
                   JOIN medicines m ON m.id = t.medicine_id
                   JOIN facilities sf ON sf.id = t.source_facility_id
                   JOIN facilities df ON df.id = t.dest_facility_id
                   ORDER BY t.id DESC"""
            ).fetchall()
        ]
    else:
        records = calculate_facility_forecast(conn)

    return {
        'columns': [
            {'label': label, 'key': key}
            for label, key in WORKSPACE_COLUMNS[view_type]
        ],
        'records': records
    }
