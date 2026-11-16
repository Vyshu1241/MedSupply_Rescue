"""
MedSupply Rescue - Intelligent Facility Stock Matching Engine
Matches shortage requests against potential donor facilities, prioritizing stock
nearing expiry that would otherwise go to waste.
"""
from datetime import date, datetime
from database.db import get_db_connection

def find_eligible_donors(conn, medicine_id, requesting_facility_id, required_quantity):
    """
    Finds and ranks candidate batches from other facilities that can fulfill the shortage.
    Prioritizes batches facing expiry-related waste at the donor facility.
    """
    cursor = conn.cursor()
    today = date.today()

    # Get medicine and requesting facility
    med = cursor.execute("SELECT * FROM medicines WHERE id = ?", (medicine_id,)).fetchone()
    if not med:
        return []
    req_fac = cursor.execute("SELECT * FROM facilities WHERE id = ?", (requesting_facility_id,)).fetchone()
    
    is_cold_chain = 1 if "Cold Chain" in med['storage_requirement'] or "2-8°C" in med['storage_requirement'] else 0

    # Query candidate active batches
    batches_query = """
        SELECT b.*, f.name as facility_name, f.facility_type, f.city, f.region, f.has_cold_chain,
               f.contact_phone, f.contact_email
        FROM batches b
        JOIN facilities f ON b.facility_id = f.id
        WHERE b.medicine_id = ? 
          AND b.facility_id != ?
          AND b.status = 'active'
          AND b.expiry_date > ?
          AND (b.current_quantity - b.reserved_quantity) > 0
        ORDER BY b.expiry_date ASC
    """
    rows = cursor.execute(batches_query, (medicine_id, requesting_facility_id, today.isoformat())).fetchall()
    
    matches = []

    for r in rows:
        b = dict(r)
        avail_qty = b['current_quantity'] - b['reserved_quantity']
        exp_date = datetime.strptime(b['expiry_date'], "%Y-%m-%d").date()
        days_to_expiry = (exp_date - today).days

        # Cold chain compliance check
        cold_chain_compatible = True
        disqualification_reason = None
        if is_cold_chain:
            if not b['has_cold_chain']:
                cold_chain_compatible = False
                disqualification_reason = "Donor facility lacks certified cold chain storage"
            elif not req_fac['has_cold_chain']:
                cold_chain_compatible = False
                disqualification_reason = "Requesting facility lacks certified cold chain storage"

        # Calculate donor historical consumption rate
        burn_stats = cursor.execute(
            """SELECT AVG(quantity_dispensed) as avg_burn, SUM(quantity_dispensed) as total_30d
               FROM daily_consumption 
               WHERE facility_id = ? AND medicine_id = ? 
                 AND consumption_date >= date('now', '-30 days')""",
            (b['facility_id'], medicine_id)
        ).fetchone()

        avg_daily_burn = float(burn_stats['avg_burn']) if burn_stats and burn_stats['avg_burn'] is not None else 1.0
        
        # Calculate projected donor consumption before batch expiry
        projected_donor_need = avg_daily_burn * days_to_expiry
        
        # Total stock of this medicine at donor facility
        donor_total_stock = cursor.execute(
            """SELECT SUM(current_quantity - reserved_quantity) as total_avail
               FROM batches 
               WHERE facility_id = ? AND medicine_id = ? AND status = 'active'""",
            (b['facility_id'], medicine_id)
        ).fetchone()['total_avail'] or avail_qty

        # Waste risk calculation: stock exceeding projected need before expiry
        waste_risk_units = max(0, int(avail_qty - projected_donor_need))
        has_waste_risk = waste_risk_units > 0

        # Safety threshold check
        safety_threshold = med['min_safety_stock_default']
        safe_donor_surplus = max(0, donor_total_stock - safety_threshold)
        transferrable_qty = min(avail_qty, required_quantity)

        # SCORING ALGORITHM (0 - 100)
        score = 0.0
        match_tags = []

        if not cold_chain_compatible:
            score = 0
            match_tags.append("INELIGIBLE: Cold Chain Violation")
            recommendation_note = f"DISQUALIFIED: {disqualification_reason}. Cold chain storage is legally required for {med['generic_name']}."
        else:
            # 1. Expiry Waste Prevention Score (0 - 45 pts)
            # High priority to save medicine before it spoils!
            if days_to_expiry <= 30:
                score += 45
                match_tags.append("Urgent Expiry Rescue (<30d)")
            elif days_to_expiry <= 60:
                score += 35
                match_tags.append("Near-Expiry Surplus (<60d)")
            elif days_to_expiry <= 90:
                score += 25
                match_tags.append("Expiring in <90d")
            else:
                score += 15
                match_tags.append("Fresh Stock")

            if has_waste_risk:
                score += 10
                match_tags.append(f"Prevents ~{waste_risk_units} Units Waste")

            # 2. Quantity Fulfillment Score (0 - 25 pts)
            coverage_ratio = min(1.0, avail_qty / float(required_quantity))
            score += (coverage_ratio * 25)
            if coverage_ratio >= 1.0:
                match_tags.append("100% Demand Covered")
            else:
                match_tags.append(f"Partial ({int(coverage_ratio*100)}%) Coverage")

            # 3. Donor Safety Margin Score (0 - 15 pts)
            if safe_donor_surplus >= transferrable_qty:
                score += 15
                match_tags.append("Zero Impact on Donor Safety")
            elif safe_donor_surplus > 0:
                score += 8
                match_tags.append("Moderate Donor Surplus")
            else:
                score += 3
                match_tags.append("Dips into Donor Reserve")

            # 4. Proximity / Regional Affinity (0 - 10 pts)
            if b['region'] == req_fac['region']:
                score += 10
                match_tags.append(f"Same Region ({b['region']})")
            elif b['city'] == req_fac['city']:
                score += 8
                match_tags.append("Same City")
            else:
                score += 4
                match_tags.append(f"Cross-Region ({b['region']})")

            # Human-readable recommendation note
            if has_waste_risk:
                recommendation_note = f"RECOMMENDED: Donor facility consumes ~{avg_daily_burn:.1f} units/day. This batch expires in {days_to_expiry} days, leaving ~{waste_risk_units} units at risk of expiration waste. Transferring {transferrable_qty} units directly prevents spoilage."
            elif safe_donor_surplus >= transferrable_qty:
                recommendation_note = f"SUITABLE: Donor holds healthy safety surplus ({donor_total_stock} total units, threshold {safety_threshold}) and can safely spare {transferrable_qty} units."
            else:
                recommendation_note = f"CONDITIONAL: Donor can provide {transferrable_qty} units, but remaining stock will fall close to safety threshold."

        score = min(100.0, round(score, 1))

        matches.append({
            "batch_id": b['id'],
            "batch_number": b['batch_number'],
            "facility_id": b['facility_id'],
            "facility_name": b['facility_name'],
            "facility_type": b['facility_type'],
            "facility_location": f"{b['city']}, {b['region']}",
            "contact_email": b['contact_email'],
            "contact_phone": b['contact_phone'],
            "has_cold_chain": b['has_cold_chain'],
            "expiry_date": b['expiry_date'],
            "days_to_expiry": days_to_expiry,
            "available_quantity": avail_qty,
            "transferrable_quantity": transferrable_qty,
            "waste_risk_units": waste_risk_units,
            "avg_daily_burn": round(avg_daily_burn, 1),
            "match_score": score,
            "match_tags": match_tags,
            "eligible": cold_chain_compatible,
            "disqualification_reason": disqualification_reason,
            "recommendation_note": recommendation_note
        })

    # Sort descending by match score
    matches.sort(key=lambda x: (x['eligible'], x['match_score']), reverse=True)
    return matches
