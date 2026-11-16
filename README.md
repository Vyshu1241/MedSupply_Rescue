MedSupply Rescue 
Facility-to-Facility Medicine Stock Visibility & Traceable Transfer Coordination System

[![Status: Production-Ready Prototype](https://img.shields.io/badge/Status-Verified_Prototype-teal.svg)](http://127.0.0.1:5001)
[![Ledger: Cryptographically Secure](https://img.shields.io/badge/Audit_Ledger-SHA--256_Verified-emerald.svg)](#immutable-style-audit-ledger)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](#)



Real-World Problem & Mission
Healthcare clinics often face critical stockouts of essential life-saving medicines (e.g. pediatric antibiotics, emergency epinephrine, insulin), while neighboring regional hospitals or distribution centers hold surplus batches of the same medicines that are approaching expiration and at risk of destruction.

MedSupply Rescue coordinates facility-to-facility stock visibility and lawful, traceable transfers, directly preventing medication spoilage and saving lives.

 Key Features & Capabilities

1. Multi-Facility & Role-Based Access Control
- rimary Personas:
  - `staff` (Clinic / Pharmacy Staff): Reports shortages, receives deliveries, reconciles stock.
  - `facility_manager` (Facility Inventory Manager): Manages batch inventory, dispatches shipments with tracking numbers.
  - `approver` (Authorized Regulatory Approver / Chief Pharmacist): Legally evaluates transfer safety, verifies cold-chain compliance, and digitally authorizes transfers.
  - `platform_admin` (Platform Administrator): Network-wide oversight, system audit verification, and simulation runners.
- **Fast 1-Click Role Switcher:** Switch instantly between personas in the application header without re-entering passwords.

2. Batch-Level Traceability & Provenance
- Tracks individual lot/batch numbers, national drug codes (NDC), strengths, and dosage forms.
- Monitors storage condition compliance: **Cold Chain (2-8°C)** vs **Room Temperature (15-25°C)**.
- Real-time countdown to expiry with automated urgency badges (Critical: <30d, Warning: <60d, Watch: <90d).

 3. Shortage Request & Intelligent Matching Engine
- Clinics submit shortage demands with clinical urgency (`CRITICAL` <24h, `HIGH` <72h, `MEDIUM` <7d).
- Matching Algorithm (`services/matching.py`):
  - Identifies eligible donor facilities possessing unreserved stock.
  - Expiry Rescue Priority:** Prioritizes donor batches that are approaching expiration and will go to waste based on the donor's historical daily consumption rate.
  - cold-Chain Safety Gate:** Rejects matches if either donor or recipient facility lacks certified refrigerated cold chain infrastructure.
  - Computes composite Match Score (0–100%) and generates human-readable clinical recommendations.

4. End-to-End Chain-of-Custody Transfer Workflow
```
[REQUESTED] ──> [MATCHED] ──> [APPROVED] ──> [DISPATCHED] ──> [RECEIVED & RECONCILED]
```
Approved: Approver signs off with a cryptographic SHA-256 digital signature; stock is immediately reserved in donor batch to prevent double-allocation.
Dispatched: Donor facility logs carrier, tracking number, and calibrated departure temperature (e.g. 4.0°C). Stock is deducted from donor inventory.
Received & Reconciled: Recipient facility inputs received count, arrival temperature, and records any discrepancy (e.g., damaged vial in transit). Inventory is added to recipient facility.

5. Advanced Engineering Challenge: Predictive Forecasting & Waste Prevention
   Historical Consumption Tracking:** Uses 30-day daily dispense logs to calculate weighted moving average burn rates ($0.50 \times 7d + 0.30 \times 14d + 0.20 \times 30d$).
- Days of Supply (DOS) vs Wholesaler Lead Times:** Detects mathematical stockout points before they occur.
- Expiry Waste Risk Detection:** Flags batches where $Available Stock > (Days to Expiry \times Daily Burn Rate)$.
- Proactive Redistribution Proposals:** Cross-analyzes network to generate automated proposals pairing expiring surplus at Donor facilities directly to needy clinics facing imminent stockouts.

6. Immutable-Style Tamper-Evident Audit Ledger
- Every state transition, batch load, approval, dispatch, and reconciliation is recorded as a linked cryptographic block.
- Each block stores `timestamp`, `facility_id`, `actor`, `entity_type`, `action`, `payload_json`, `previous_hash`, and `current_hash` (SHA-256).
- **On-Demand Ledger Verification:** Live button and API (`/audit/verify`) traverses from genesis block to the tip, recalculating all hashes to guarantee zero unauthorized alterations.



🖥️ User Roles & Demo Accounts

All demo accounts use password: `Rescue2026!` (or use the 1-click switcher in the header):

| Persona | Name | Role | Facility | Key Action |
|---|---|---|---|---|
| **Clinic Staff** | Dr. Sarah Chen | `staff` | Northside Community Clinic | Logs pediatric shortages, receives & reconciles batches |
| **Inventory Manager** | Marcus Vance | `facility_manager` | St. Jude Regional Medical Center | Manages hospital batches, dispatches couriers |
| **Authorized Approver** | Dr. Elena Rostova | `approver` | Regional Regulatory Authority | Signs off on legal & cold-chain transfer compliance |
| **Platform Admin** | Alex Mercer | `platform_admin` | Central Logistics HQ | Full system visibility, audit verification |
| **Rural Staff** | Nurse David Miller | `staff` | Valley Hope Rural Dispensary | Rural dispensary operations (no cold chain) |

---

Running the Project

Prerequisites
- Python 3.9+
- Flask & Werkzeug (`pip install -r requirements.txt`)

Starting the Web Application
```bash
python3 app.py
```
Open [http://127.0.0.1:5001](http://127.0.0.1:5001) in your browser.

### Running the Automated Test Suite
```bash
python3 test_system.py
```
Tests:
- Database seeding and schema constraints
- Batch inventory and threshold alert calculation
- Intelligent matching engine scoring and cold chain disqualifications
- Complete transfer lifecycle with stock reservation and deduction
- Cryptographic SHA-256 ledger block verification
- Days of Supply forecasting and automated redistribution proposals
- Flask HTTP routes



 Safety, Ethics & Limitations
> [!IMPORTANT]
> Regulatory Disclaimer:MedSupply Rescue is an inventory coordination and supply visibility prototype, not a clinical decision support system or prescribing tool. All inter-facility transfers must comply with applicable state and federal pharmaceutical distribution regulations and must be authorized by licensed healthcare personnel.
