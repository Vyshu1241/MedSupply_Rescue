"""
MedSupply Rescue - Predictive Forecasting & Stock Redistribution Engine
Addresses the Advanced Engineering Challenge:
- Forecasts stock shortages using historical consumption trends and supplier lead times
- Quantifies expiry-related medicine waste risks
- Generates proactive inter-facility redistribution proposals for authorized review
"""
import math
from datetime import date, datetime, timedelta
from database.db import get_db_connection
from services.inventory import log_audit_event

def calculate_facility_forecast(conn, facility_id=None, medicine_id=None):
    """
    Computes statistical consumption run-rate, Days of Supply (DOS),
    projected stockout dates, and batch-level expiry waste risks.
    """
    cursor = conn.cursor()
    today = date.today()

    query = """
        SELECT m.id as medicine_id, m.generic_name, m.brand_name, m.strength, 
               m.dosage_form, m.unit_of_measure, m.storage_requirement,
               m.min_safety_stock_default, m.standard_lead_time_days,
               f.id as facility_id, f.name as facility_name, f.facility_type, f.has_cold_chain
        FROM facilities f
        CROSS JOIN medicines m
        WHERE 1=1
    """
    params = []
    if facility_id:
        query += " AND f.id = ?"
        params.append(facility_id)
    if medicine_id:
        query += " AND m.id = ?"
        params.append(medicine_id)

    pairs = cursor.execute(query, params).fetchall()
    forecasts = []

    for p in pairs:
        fac_id = p['facility_id']
        med_id = p['medicine_id']

        # Get active stock for this facility & medicine
        batches = cursor.execute(
            """SELECT id, batch_number, current_quantity, reserved_quantity, expiry_date, storage_location
               FROM batches 
               WHERE facility_id = ? AND medicine_id = ? AND status = 'active'
               ORDER BY expiry_date ASC""",
            (fac_id, med_id)
        ).fetchall()

        total_current_stock = sum(b['current_quantity'] for b in batches)
        total_reserved = sum(b['reserved_quantity'] for b in batches)
        available_stock = max(0, total_current_stock - total_reserved)

        # Get historical consumption for 7, 14, 30 days
        hist_7 = cursor.execute(
            """SELECT AVG(quantity_dispensed) as avg_burn, SUM(quantity_dispensed) as total_qty
               FROM daily_consumption
               WHERE facility_id = ? AND medicine_id = ? AND consumption_date >= date('now', '-7 days')""",
            (fac_id, med_id)
        ).fetchone()

        hist_14 = cursor.execute(
            """SELECT AVG(quantity_dispensed) as avg_burn
               FROM daily_consumption
               WHERE facility_id = ? AND medicine_id = ? AND consumption_date >= date('now', '-14 days')""",
            (fac_id, med_id)
        ).fetchone()

        hist_30 = cursor.execute(
            """SELECT AVG(quantity_dispensed) as avg_burn, COUNT(*) as days_recorded
               FROM daily_consumption
               WHERE facility_id = ? AND medicine_id = ? AND consumption_date >= date('now', '-30 days')""",
            (fac_id, med_id)
        ).fetchone()

        avg_7 = float(hist_7['avg_burn']) if hist_7 and hist_7['avg_burn'] is not None else 0.0
        avg_14 = float(hist_14['avg_burn']) if hist_14 and hist_14['avg_burn'] is not None else 0.0
        avg_30 = float(hist_30['avg_burn']) if hist_30 and hist_30['avg_burn'] is not None else 0.0

        # Weighted daily consumption rate (emphasis on recent trends)
        if avg_7 > 0 or avg_14 > 0 or avg_30 > 0:
            daily_burn_rate = round((avg_7 * 0.50) + (avg_14 * 0.30) + (avg_30 * 0.20), 2)
            if daily_burn_rate <= 0:
                daily_burn_rate = max(0.5, avg_30)
        else:
            daily_burn_rate = 1.0  # fallback assumption for low-movement stock

        # Days of Supply (DOS)
        if daily_burn_rate > 0:
            days_of_supply = round(available_stock / daily_burn_rate, 1)
        else:
            days_of_supply = 999.0

        lead_time = p['standard_lead_time_days']
        safety_stock = p['min_safety_stock_default']

        # Shortage prediction classification
        if available_stock <= 0:
            stockout_status = "STOCKOUT"
            risk_level = "CRITICAL"
            days_until_stockout = 0
            stockout_date = today.isoformat()
        elif days_of_supply < lead_time:
            stockout_status = "IMMINENT_STOCKOUT"
            risk_level = "CRITICAL"
            days_until_stockout = math.floor(days_of_supply)
            stockout_date = (today + timedelta(days=days_until_stockout)).isoformat()
        elif days_of_supply < (lead_time * 1.5):
            stockout_status = "LOW_SUPPLY_RISK"
            risk_level = "WARNING"
            days_until_stockout = math.floor(days_of_supply)
            stockout_date = (today + timedelta(days=days_until_stockout)).isoformat()
        else:
            stockout_status = "SUFFICIENT"
            risk_level = "HEALTHY"
            days_until_stockout = math.floor(days_of_supply)
            stockout_date = (today + timedelta(days=min(365, days_until_stockout))).isoformat()

        # Batch-level Expiry Waste Risk Analysis
        # If a batch expires before the facility can consume it at current burn rate:
        total_forecasted_waste = 0
        batch_waste_details = []
        cumulative_consumed = 0

        for b in batches:
            exp_date = datetime.strptime(b['expiry_date'], "%Y-%m-%d").date()
            days_left = max(0, (exp_date - today).days)
            b_avail = max(0, b['current_quantity'] - b['reserved_quantity'])

            # How many units facility can consume between today and this batch's expiry
            potential_consumption_by_expiry = daily_burn_rate * days_left
            
            # If batch has more than can be consumed
            if b_avail > potential_consumption_by_expiry:
                waste_units = int(b_avail - potential_consumption_by_expiry)
                if waste_units > 0:
                    total_forecasted_waste += waste_units
                    batch_waste_details.append({
                        "batch_id": b['id'],
                        "batch_number": b['batch_number'],
                        "expiry_date": b['expiry_date'],
                        "days_left": days_left,
                        "current_qty": b['current_quantity'],
                        "waste_units": waste_units
                    })

        forecasts.append({
            "facility_id": fac_id,
            "facility_name": p['facility_name'],
            "facility_type": p['facility_type'],
            "has_cold_chain": p['has_cold_chain'],
            "medicine_id": med_id,
            "generic_name": p['generic_name'],
            "brand_name": p['brand_name'],
            "strength": p['strength'],
            "unit": p['unit_of_measure'],
            "storage_requirement": p['storage_requirement'],
            "lead_time_days": lead_time,
            "safety_stock": safety_stock,
            "current_stock": total_current_stock,
            "available_stock": available_stock,
            "daily_burn_rate": daily_burn_rate,
            "days_of_supply": days_of_supply,
            "stockout_status": stockout_status,
            "risk_level": risk_level,
            "days_until_stockout": days_until_stockout,
            "stockout_date": stockout_date,
            "total_forecasted_waste": total_forecasted_waste,
            "batch_waste_details": batch_waste_details
        })

    return forecasts

def generate_network_redistribution_suggestions(conn):
    """
    Cross-analyzes all facilities:
    Pairs facilities with impending expiry waste to facilities facing stockouts.
    Returns ranked redistribution opportunities for authorized decision-makers.
    """
    cursor = conn.cursor()
    all_forecasts = calculate_facility_forecast(conn)

    # Group into potential donors (forecasted waste > 0) and potential receivers (low DOS or stockout)
    donors = [f for f in all_forecasts if f['total_forecasted_waste'] > 0 and len(f['batch_waste_details']) > 0]
    receivers = [f for f in all_forecasts if f['stockout_status'] in ('STOCKOUT', 'IMMINENT_STOCKOUT', 'LOW_SUPPLY_RISK')]

    recommendations = []

    for donor in donors:
        for receiver in receivers:
            if donor['medicine_id'] == receiver['medicine_id'] and donor['facility_id'] != receiver['facility_id']:
                # Cold chain compatibility check
                is_cold_chain = "Cold Chain" in donor['storage_requirement'] or "2-8°C" in donor['storage_requirement']
                if is_cold_chain and (not donor['has_cold_chain'] or not receiver['has_cold_chain']):
                    continue # Incompatible storage

                # First waste-risk batch
                top_waste_batch = donor['batch_waste_details'][0]
                waste_qty = top_waste_batch['waste_units']

                # Receiver shortfall = safety_stock + (daily_burn * lead_time) - available_stock
                receiver_deficit = max(
                    15,
                    int((receiver['daily_burn_rate'] * receiver['lead_time_days'] * 1.5) - receiver['available_stock'])
                )
                
                transfer_qty = min(waste_qty, receiver_deficit)
                if transfer_qty <= 0:
                    transfer_qty = min(waste_qty, donor['available_stock'])

                if transfer_qty > 0:
                    days_to_expiry = top_waste_batch['days_left']
                    # Priority calculation: higher urgency for shorter expiry & severe receiver deficit
                    urgency_mult = 2.0 if days_to_expiry <= 30 else (1.5 if days_to_expiry <= 60 else 1.0)
                    severity_mult = 2.0 if receiver['stockout_status'] == 'STOCKOUT' else (1.5 if receiver['stockout_status'] == 'IMMINENT_STOCKOUT' else 1.1)
                    priority_score = round(urgency_mult * severity_mult * math.log(transfer_qty + 1) * 10, 1)

                    rec = {
                        "source_facility_id": donor['facility_id'],
                        "source_facility_name": donor['facility_name'],
                        "dest_facility_id": receiver['facility_id'],
                        "dest_facility_name": receiver['facility_name'],
                        "medicine_id": donor['medicine_id'],
                        "medicine_name": f"{donor['generic_name']} ({donor['strength']})",
                        "unit": donor['unit'],
                        "batch_id": top_waste_batch['batch_id'],
                        "batch_number": top_waste_batch['batch_number'],
                        "source_expiry_date": top_waste_batch['expiry_date'],
                        "days_to_expiry": days_to_expiry,
                        "suggested_quantity": transfer_qty,
                        "forecasted_waste_units": waste_qty,
                        "dest_current_stock": receiver['available_stock'],
                        "dest_days_of_supply": receiver['days_of_supply'],
                        "dest_stockout_date": receiver['stockout_date'],
                        "priority_score": priority_score,
                        "impact_summary": f"Redistributes {transfer_qty} {donor['unit']} of {donor['generic_name']} that would otherwise expire in {days_to_expiry} days at {donor['facility_name']} to prevent stockout at {receiver['facility_name']} (current supply: {receiver['days_of_supply']} days)."
                    }
                    recommendations.append(rec)

    recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
    return recommendations
