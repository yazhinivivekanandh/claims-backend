from .db import one, write, write_many, json_dumps

CHECKLIST_DEFINITIONS = [
    ("C1", "Patient identity and demographics"),
    ("C2", "Active and validated insurance policy"),
    ("C3", "Admission and discharge dates"),
    ("C4", "Digitally signed discharge summary"),
    ("C5", "Itemized final bill"),
    ("C6", "Authorization and extension evidence"),
    ("C7", "Medication and clinical records"),
    ("C8", "Consent and banking metadata"),
]

MERIDIAN = "Meridian Health TPA"
CHECKLIST_VERSION = "MHTPA-CASHLESS-2025.1"


def _seed_checklist():
    write_many(
        "INSERT OR IGNORE INTO insurer_checklists (insurer, checklist_version, code, description) VALUES (?, ?, ?, ?)",
        [(MERIDIAN, CHECKLIST_VERSION, code, desc) for code, desc in CHECKLIST_DEFINITIONS],
    )


def _seed_pat10482():
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PAT-10482", "Ravi Kumar", "AD-10482-20250207", "2025-02-07", "2025-02-12", "General Ward",
         MERIDIAN, "POL-ABCD-987654", "INTAKE_RECEIVED", None),
    )
    write(
        "INSERT OR REPLACE INTO policies (policy_number, patient_id, insurer, active_from, active_to, approved_limit, approved_stay_days, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("POL-ABCD-987654", "PAT-10482", MERIDIAN, "2025-01-01", "2025-12-31", 100000, 5, "ACTIVE"),
    )
    emr = [
        ("EMR-10482-001", "2025-02-07", "diagnosis", "Admitted with community-acquired pneumonia; started IV ceftriaxone and azithromycin."),
        ("EMR-10482-002", "2025-02-08", "hospital_course", "Vital signs stable; oxygen requirement 3 L/min on room air challenge."),
        ("EMR-10482-003", "2025-02-08", "hospital_course", "Oxygen requirement decreased from 3 L/min to 1 L/min."),
        ("EMR-10482-004", "2025-02-09", "hospital_course", "Afebrile and tolerating oral intake."),
        ("EMR-10482-005", "2025-02-11", "hospital_course", "Continue IV antibiotics overnight; reassess oxygen saturation on room air tomorrow morning before discharge."),
        ("EMR-10482-006", "2025-02-12", "condition_at_discharge", "Afebrile for 48 hours, room-air oxygen saturation 96%, ambulating independently, tolerating oral intake; discharge home planned. Discharge medications: azithromycin 500 mg daily for 2 days, paracetamol as needed; enoxaparin discontinued at discharge. Follow-up at respiratory clinic in 7 days."),
    ]
    write_many(
        "INSERT OR REPLACE INTO emr_notes (note_id, patient_id, note_date, source, section, is_clinical, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(nid, "PAT-10482", d, nid, section, 1, text) for nid, d, section, text in emr],
    )
    write(
        "INSERT OR REPLACE INTO allergies (patient_id, allergen, severity, recorded_date, source_note_id) VALUES (?, ?, ?, ?, ?)",
        ("PAT-10482", "no known drug allergies", "none", "2025-02-07", "EMR-10482-001"),
    )
    ledger = [
        ("BL-10482-001", "2025-02-07", "Registration and admission charges", 3400.0, 0),
        ("BL-10482-002", "2025-02-07", "General ward room rent day 1", 5200.0, 0),
        ("BL-10482-003", "2025-02-08", "General ward room rent day 2", 3400.0, 0),
        ("BL-10482-004", "2025-02-09", "General ward room rent day 3", 5200.0, 0),
        ("BL-10482-005", "2025-02-10", "General ward room rent day 4", 3400.0, 0),
        ("BL-10482-006", "2025-02-11", "General ward room rent day 5", 1200.0, 0),
        ("BL-10482-007", "2025-02-07", "IV ceftriaxone infusion", 6800.0, 0),
        ("BL-10482-008", "2025-02-07", "IV azithromycin infusion", 2400.0, 0),
        ("BL-10482-009", "2025-02-07", "Paracetamol 500 mg as needed", 1850.0, 0),
        ("BL-10482-010", "2025-02-07", "Enoxaparin injection", 2450.0, 0),
        ("BL-10482-011", "2025-02-07", "Chest X-ray PA view", 3100.0, 0),
        ("BL-10482-012", "2025-02-07", "Complete blood count", 4100.0, 0),
        ("BL-10482-013", "2025-02-07", "Blood culture sensitivity", 2750.0, 0),
        ("BL-10482-014", "2025-02-07", "Pulse oximetry monitoring", 890.0, 0),
        ("BL-10482-015", "2025-02-08", "Physiotherapy session", 1250.0, 0),
        ("BL-10482-016", "2025-02-09", "Oxygen therapy day 1", 2300.0, 0),
        ("BL-10482-017", "2025-02-10", "Medication return credit", 1200.0, 1),
        ("BL-10482-018", "2025-02-10", "Oxygen therapy day 2", 940.0, 0),
        ("BL-10482-019", "2025-02-11", "Repeat chest X-ray", 2450.0, 0),
        ("BL-10482-020", "2025-02-11", "Oral azithromycin continuation", 1450.0, 0),
        ("BL-10482-021", "2025-02-12", "Discharge day room charge", 1550.0, 0),
        ("BL-10482-022", "2025-02-12", "Discharge documentation fee", 950.0, 0),
    ]
    gross = sum(a for _, _, _, a, credit in ledger if not credit)
    credits = sum(a for _, _, _, a, credit in ledger if credit)
    balance = 54130.0 - gross
    if abs(balance) > 0.01:
        ledger.append(("BL-10482-023", "2025-02-12", "Final balancing charge", round(balance, 2), 0))
    write_many(
        "INSERT OR REPLACE INTO ledger_entries (entry_id, patient_id, entry_date, description, amount, is_credit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(eid, "PAT-10482", d, desc, amount, credit, "POSTED") for eid, d, desc, amount, credit in ledger],
    )
    _ = credits
    orders = [
        ("ORD-10482-001", "2025-02-07", "IV ceftriaxone", "BL-10482-007"),
        ("ORD-10482-002", "2025-02-07", "IV azithromycin", "BL-10482-008"),
        ("ORD-10482-003", "2025-02-07", "Paracetamol 500 mg", "BL-10482-009"),
        ("ORD-10482-004", "2025-02-07", "Enoxaparin", "BL-10482-010"),
        ("ORD-10482-005", "2025-02-07", "Chest X-ray", "BL-10482-011"),
        ("ORD-10482-006", "2025-02-07", "Complete blood count", "BL-10482-012"),
        ("ORD-10482-007", "2025-02-07", "Blood culture", "BL-10482-013"),
        ("ORD-10482-008", "2025-02-07", "Pulse oximetry monitoring", "BL-10482-014"),
        ("ORD-10482-009", "2025-02-08", "Physiotherapy", "BL-10482-015"),
        ("ORD-10482-010", "2025-02-09", "Oxygen therapy", "BL-10482-016"),
        ("ORD-10482-011", "2025-02-10", "Oxygen therapy", "BL-10482-018"),
        ("ORD-10482-012", "2025-02-11", "Repeat chest X-ray", "BL-10482-019"),
        ("ORD-10482-013", "2025-02-11", "Oral azithromycin", "BL-10482-020"),
        ("ORD-10482-014", "2025-02-12", "Discharge documentation", "BL-10482-022"),
    ]
    write_many(
        "INSERT OR REPLACE INTO orders (order_id, patient_id, order_date, item, charge_entry_id, status) VALUES (?, ?, ?, ?, ?, ?)",
        [(oid, "PAT-10482", d, item, eid, "CHARGED") for oid, d, item, eid in orders],
    )


def _seed_pat20731():
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PAT-20731", "Sunita Verma", "AD-20731-20250312", "2025-03-12", "2025-03-16", "Private Room",
         MERIDIAN, "POL-QWER-246810", "INTAKE_RECEIVED", None),
    )
    write(
        "INSERT OR REPLACE INTO policies (policy_number, patient_id, insurer, active_from, active_to, approved_limit, approved_stay_days, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("POL-QWER-246810", "PAT-20731", MERIDIAN, "2025-01-01", "2025-12-31", 150000, 4, "ACTIVE"),
    )
    emr = [
        ("EMR-20731-001", "2025-03-12", "diagnosis", "Acute cholecystitis; planned laparoscopic cholecystectomy."),
        ("EMR-20731-002", "2025-03-13", "hospital_course", "Perioperative ceftriaxone and metronidazole administered."),
        ("EMR-20731-003", "2025-03-13", "procedure", "Laparoscopic cholecystectomy completed; postoperative drain placed."),
        ("EMR-20731-004", "2025-03-14", "hospital_course", "Stable vital signs; pain controlled; tolerating oral intake."),
        ("EMR-20731-005", "2025-03-15", "hospital_course", "Drain output remains 180 mL over the last 24 hours; continue observation and repeat CBC tomorrow."),
        ("EMR-20731-006", "2025-03-16", "condition_at_discharge", "Afebrile, tolerating diet, ambulating, suitable for discharge after laparoscopic cholecystectomy. Discharge medications: oral cefuroxime, metronidazole, paracetamol, ondansetron. Follow-up at surgical clinic in 7 days."),
        ("EMR-20731-009", "2025-03-17", "allergy_addendum", "Patient developed generalized urticaria and wheeze after prior cephalosporin exposure; document severe cephalosporin allergy and avoid ceftriaxone and cefuroxime."),
    ]
    write_many(
        "INSERT OR REPLACE INTO emr_notes (note_id, patient_id, note_date, source, section, is_clinical, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(nid, "PAT-20731", d, nid, section, 1, text) for nid, d, section, text in emr],
    )
    write(
        "INSERT OR REPLACE INTO allergies (patient_id, allergen, severity, recorded_date, source_note_id) VALUES (?, ?, ?, ?, ?)",
        ("PAT-20731", "cephalosporins", "severe", "2025-03-17", "EMR-20731-009"),
    )
    ledger = [
        ("BL-20731-001", "2025-03-12", "Registration and admission charges", 4500.0, 0),
        ("BL-20731-002", "2025-03-12", "Private room rent day 1", 12000.0, 0),
        ("BL-20731-003", "2025-03-13", "Private room rent day 2", 12000.0, 0),
        ("BL-20731-004", "2025-03-14", "Private room rent day 3", 12000.0, 0),
        ("BL-20731-005", "2025-03-15", "Private room rent day 4", 12000.0, 0),
        ("BL-20731-006", "2025-03-13", "Surgical procedure charge", 18500.0, 0),
        ("BL-20731-007", "2025-03-13", "Ceftriaxone infusion", 3400.0, 0),
        ("BL-20731-008", "2025-03-13", "Metronidazole infusion", 2150.0, 0),
        ("BL-20731-009", "2025-03-13", "Anaesthesia services", 5200.0, 0),
        ("BL-20731-010", "2025-03-13", "Surgical consumables", 3100.0, 0),
        ("BL-20731-011", "2025-03-13", "Complete blood count", 2900.0, 0),
        ("BL-20731-012", "2025-03-14", "Ultrasound abdomen", 2400.0, 0),
        ("BL-20731-013", "2025-03-14", "Paracetamol 500 mg", 950.0, 0),
        ("BL-20731-014", "2025-03-15", "Repeat complete blood count", 2900.0, 0),
        ("BL-20731-015", "2025-03-14", "Medication return credit", 900.0, 1),
        ("BL-20731-016", "2025-03-16", "Discharge documentation fee", 900.0, 0),
        ("BL-20731-017", "2025-03-16", "Oral cefuroxime and ondansetron", 850.0, 0),
        ("BL-20731-018", "2025-03-16", "Drain removal procedure", 1500.0, 0),
        ("BL-20731-019", "2025-03-16", "Discharge day room charge", 3000.0, 0),
        ("BL-20731-020", "2025-03-16", "Dressing and nursing care", 900.0, 0),
        ("BL-20731-021", "2025-03-16", "Final reconciliation service charge", 1600.0, 0),
    ]
    gross = sum(a for _, _, _, a, credit in ledger if not credit)
    balance = 77750.0 - gross
    if abs(balance) > 0.01:
        ledger.append(("BL-20731-022", "2025-03-16", "Final balancing charge", round(balance, 2), 0))
    write_many(
        "INSERT OR REPLACE INTO ledger_entries (entry_id, patient_id, entry_date, description, amount, is_credit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(eid, "PAT-20731", d, desc, amount, credit, "POSTED") for eid, d, desc, amount, credit in ledger],
    )
    write(
        "INSERT OR REPLACE INTO nhcx_queries (query_id, patient_id, claim_id, text, classification, status, source_ids, response, receipt, received_at, transmitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("NHCX-Q-99107", "PAT-20731", "CLM-20731-20250316",
         "Claim documents ceftriaxone administration and cefuroxime at discharge; a later record documents severe cephalosporin allergy with wheeze and urticaria. Explain.",
         "URGENT_CLINICAL_ESCALATION", "RECEIVED", json_dumps(["EMR-20731-003", "EMR-20731-006", "EMR-20731-009"]),
         None, None, "2025-03-17T16:45:00Z", None),
    )


def _seed_pt_fixtures():
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PT001", "Test Patient One", "AD-PT001", "2025-01-10", "2025-01-15", "General Ward",
         MERIDIAN, "POL-PT001-XYZ123", "INTAKE_RECEIVED", None),
    )
    write(
        "INSERT OR REPLACE INTO policies (policy_number, patient_id, insurer, active_from, active_to, approved_limit, approved_stay_days, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("POL-PT001-XYZ123", "PT001", MERIDIAN, "2025-01-01", "2025-12-31", 200000, 5, "ACTIVE"),
    )
    ledger = [
        ("B001", "2025-01-10", "Room and accommodation", 15000.0, 0),
        ("B002", "2025-01-10", "Diagnostics", 8500.0, 0),
        ("B003", "2025-01-10", "Procedure charges", 32000.0, 0),
        ("B004", "2025-01-10", "Medication charges", 9800.0, 0),
        ("B005", "2025-01-10", "Nursing care", 7200.0, 0),
        ("B006", "2025-01-10", "Consumables", 6400.0, 0),
        ("B007", "2025-01-10", "Anaesthesia", 5600.0, 0),
        ("B008", "2025-01-10", "Miscellaneous charges", 4150.0, 0),
    ]
    total = sum(a for _, _, _, a, _ in ledger)
    balance = 88650.0 - total
    if abs(balance) > 0.01:
        ledger.append(("B009", "2025-01-10", "Final balancing charge", round(balance, 2), 0))
    write_many(
        "INSERT OR REPLACE INTO ledger_entries (entry_id, patient_id, entry_date, description, amount, is_credit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(eid, "PT001", d, desc, amount, credit, "POSTED") for eid, d, desc, amount, credit in ledger],
    )
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PT002", "Test Patient Two", "AD-PT002", "2025-01-10", "2025-01-14", "General Ward",
         MERIDIAN, "POL-PT002-ABC456", "INTAKE_RECEIVED",
         "[PENDING CONSULTANT CONFIRMATION: Discharge Medications & Follow-up Details Missing in logs L006-L009]"),
    )
    write_many(
        "INSERT OR REPLACE INTO emr_notes (note_id, patient_id, note_date, source, section, is_clinical, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("L001", "PT002", "2025-01-10", "L001", "diagnosis", 1, "Admitted with urinary tract infection."),
            ("L002", "PT002", "2025-01-11", "L002", "hospital_course", 1, "Started IV antibiotics; vitals stable."),
            ("L003", "PT002", "2025-01-12", "L003", "hospital_course", 1, "Afebrile since yesterday."),
            ("L004", "PT002", "2025-01-13", "L004", "hospital_course", 1, "Tolerating oral intake."),
            ("L005", "PT002", "2025-01-14", "L005", "condition_at_discharge", 1, "Stable and suitable for discharge."),
        ],
    )
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PT003", "Test Patient Three", "AD-PT003", "2025-01-10", "2025-01-16", "General Ward",
         MERIDIAN, "POL-PT003-DEF789", "INTAKE_RECEIVED", None),
    )
    write_many(
        "INSERT OR REPLACE INTO emr_notes (note_id, patient_id, note_date, source, section, is_clinical, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("L010", "PT003", "2025-01-10", "L010", "diagnosis", 1, "Pneumonia; ceftriaxone prescribed."),
            ("L012", "PT003", "2025-01-12", "L012", "hospital_course", 1, "Cefuroxime added for discharge continuation."),
            ("L015", "PT003", "2025-01-15", "L015", "allergy_addendum", 1, "Known severe penicillin and cephalosporin allergy."),
        ],
    )
    write(
        "INSERT OR REPLACE INTO allergies (patient_id, allergen, severity, recorded_date, source_note_id) VALUES (?, ?, ?, ?, ?)",
        ("PT003", "cephalosporins", "severe", "2025-01-15", "L015"),
    )
    write(
        "INSERT OR REPLACE INTO patients (patient_id, name, admission_id, admission_date, discharge_date, room_category, insurer, policy_number, status, pending_confirmation) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("PT004", "Test Patient Four", "AD-PT004", "2025-01-10", "2025-01-13", "General Ward",
         MERIDIAN, "POL-PT004-GHI012", "INTAKE_RECEIVED", None),
    )
    write_many(
        "INSERT OR REPLACE INTO emr_notes (note_id, patient_id, note_date, source, section, is_clinical, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("L016", "PT004", "2025-01-10", "L016", "non_clinical", 0, "Billing clerk note: tariff code T-4102 category mismatch."),
            ("L017", "PT004", "2025-01-11", "L017", "non_clinical", 0, "Front desk note: family requested extra pillows."),
        ],
    )


def ensure_nhcx_query_pat10482() -> None:
    write(
        "INSERT OR REPLACE INTO nhcx_queries (query_id, patient_id, claim_id, text, classification, status, source_ids, response, receipt, received_at, transmitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("NHCX-Q-88421", "PAT-10482", "CLM-10482-20250212",
         "Transmitted INR 52930 does not match authoritative INR 47450. Explain the discrepancy.",
         "BILLING_DISCREPANCY", "RECEIVED", json_dumps(["BL-10482-023"]),
         None, None, "2025-02-13T12:00:00Z", None),
    )


def seed_if_empty() -> None:
    if one("SELECT 1 FROM patients LIMIT 1") is not None:
        return
    _seed_checklist()
    _seed_pat10482()
    _seed_pat20731()
    _seed_pt_fixtures()
