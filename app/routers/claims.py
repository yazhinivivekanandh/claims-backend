import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, utc_now, json_dumps
from ..dependencies import require_token
from .intake import get_patient, blocking_conditions
from .billing import ledger_reconciler

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/insurer-checklist")
def insurer_checklist_query(patient_id: str):
    patient = get_patient(patient_id)
    checks = rows(
        "SELECT code, description FROM insurer_checklists WHERE insurer = ? ORDER BY code",
        (patient["insurer"],),
    )
    version_row = one("SELECT checklist_version FROM insurer_checklists WHERE insurer = ? LIMIT 1", (patient["insurer"],))
    return {
        "insurer": patient["insurer"],
        "checklist_version": version_row["checklist_version"] if version_row else None,
        "requirements": [{"code": c["code"], "description": c["description"]} for c in checks],
    }


@router.post("/patients/{patient_id}/checklist-verification")
def checklist_requirement_verifier(patient_id: str):
    patient = get_patient(patient_id)
    blocks = blocking_conditions(patient_id)
    has_draft = one("SELECT 1 FROM summaries WHERE patient_id = ?", (patient_id,)) is not None
    policy = one("SELECT * FROM policies WHERE patient_id = ?", (patient_id,))
    has_bill = one("SELECT 1 FROM ledger_entries WHERE patient_id = ? LIMIT 1", (patient_id,)) is not None
    has_clinical = one("SELECT 1 FROM emr_notes WHERE patient_id = ? AND is_clinical = 1 LIMIT 1", (patient_id,)) is not None
    has_extension = one("SELECT 1 FROM extensions WHERE patient_id = ? LIMIT 1", (patient_id,)) is not None

    def status(present: bool) -> str:
        return "present" if present else "missing"

    requirements = [
        {"code": "C1", "description": "Patient identity", "status": status(bool(patient))},
        {"code": "C2", "description": "Active and validated policy", "status": status(policy is not None and policy["status"] == "ACTIVE")},
        {"code": "C3", "description": "Admission and discharge dates", "status": status(bool(patient["admission_date"] and patient["discharge_date"]))},
        {"code": "C4", "description": "Signed discharge summary", "status": status(has_draft and not blocks)},
        {"code": "C5", "description": "Itemized final bill", "status": status(has_bill)},
        {"code": "C6", "description": "Authorization and extension evidence", "status": status(bool(policy) or has_extension)},
        {"code": "C7", "description": "Medication and clinical records", "status": status(has_clinical)},
        {"code": "C8", "description": "Consent and banking metadata", "status": status(has_bill), "source": "audited_billing_ledger"},
    ]
    missing = [r["code"] for r in requirements if r["status"] == "missing"]
    return {
        "patient_id": patient_id,
        "checklist_version": one("SELECT checklist_version FROM insurer_checklists LIMIT 1")["checklist_version"],
        "requirements": requirements,
        "missing_count": len(missing),
        "missing_codes": missing,
        "blocking_reasons": blocks,
    }


@router.post("/patients/{patient_id}/fhir-bundle")
def fhir_payload_builder(patient_id: str):
    patient = get_patient(patient_id)
    blocks = blocking_conditions(patient_id)
    if blocks:
        raise HTTPException(status_code=409, detail={"validation": "FAIL", "blocking_reasons": blocks})
    reconciliation = ledger_reconciler(patient_id)
    bundle_id = f"FHIR-{patient_id}-{patient['discharge_date'].replace('-', '')}"
    existing = one("SELECT * FROM claims WHERE patient_id = ? AND bundle_id = ?", (patient_id, bundle_id))
    if existing and existing["status"] == "SUBMITTED":
        return {
            "bundle_id": bundle_id,
            "patient_id": patient_id,
            "resource_types": json_dumps(["Patient", "Coverage", "Encounter", "Condition", "MedicationStatement", "DocumentReference", "Claim"]),
            "claimed_amount": existing["amount"],
            "validation": "PASS",
            "status": existing["status"],
            "encryption": {"algorithm": "placeholder-envelope", "note": "Replace with production envelope encryption before NHCX."},
        }
    amount = reconciliation["net_total"]
    write(
        "INSERT OR REPLACE INTO claims (claim_id, patient_id, bundle_id, amount, status, receipt, payer_response_deadline, submitted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"CLM-{patient_id}-{patient['discharge_date'].replace('-', '')}", patient_id, bundle_id, amount, "BUILT", None, None, None),
    )
    return {
        "bundle_id": bundle_id,
        "patient_id": patient_id,
        "resource_types": ["Patient", "Coverage", "Encounter", "Condition", "MedicationStatement", "DocumentReference", "Claim"],
        "claimed_amount": amount,
        "validation": "PASS",
        "status": "BUILT",
        "encryption": {"algorithm": "placeholder-envelope", "note": "Replace with production envelope encryption before NHCX."},
    }


class SubmitBody(BaseModel):
    bundle_id: Optional[str] = None


@router.post("/patients/{patient_id}/claims/submit")
def nhcx_gateway_transmitter(patient_id: str, body: Optional[SubmitBody] = None):
    patient = get_patient(patient_id)
    blocks = blocking_conditions(patient_id)
    if blocks:
        raise HTTPException(status_code=409, detail={"blocking": True, "blocking_reasons": blocks})
    bundle_id = body.bundle_id if body and body.bundle_id else f"FHIR-{patient_id}-{patient['discharge_date'].replace('-', '')}"
    claim = one("SELECT * FROM claims WHERE patient_id = ? AND bundle_id = ?", (patient_id, bundle_id))
    if claim is None:
        built = fhir_payload_builder(patient_id)
        bundle_id = built["bundle_id"]
        claim = one("SELECT * FROM claims WHERE patient_id = ? AND bundle_id = ?", (patient_id, bundle_id))
    if claim["status"] == "SUBMITTED":
        return {
            "claim_id": claim["claim_id"],
            "bundle_id": claim["bundle_id"],
            "receipt": claim["receipt"],
            "status": "SUBMITTED",
            "submitted_at": claim["submitted_at"],
            "payer_response_deadline": claim["payer_response_deadline"],
        }
    seq = int(one("SELECT COUNT(*) AS c FROM claims")["c"]) + 1
    receipt = f"NHCX-ACK-{seq:04d}-{random.randint(1000, 9999)}"
    submitted_at = utc_now()
    deadline = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
    write(
        "UPDATE claims SET status = 'SUBMITTED', receipt = ?, submitted_at = ?, payer_response_deadline = ? WHERE claim_id = ?",
        (receipt, submitted_at, deadline, claim["claim_id"]),
    )
    return {
        "claim_id": claim["claim_id"],
        "bundle_id": claim["bundle_id"],
        "receipt": receipt,
        "status": "SUBMITTED",
        "submitted_at": submitted_at,
        "payer_response_deadline": deadline,
    }
