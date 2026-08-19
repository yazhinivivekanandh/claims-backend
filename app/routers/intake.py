from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import one, rows, write, get_conn, utc_now, json_dumps
from ..dependencies import require_token

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}")
def get_patient_details(patient_id: str):
    patient = get_patient(patient_id)
    policy = one("SELECT * FROM policies WHERE patient_id = ?", (patient_id,))
    return {
        "patient_id": patient["patient_id"],
        "name": patient["name"],
        "admission_id": patient["admission_id"],
        "admission_date": patient["admission_date"],
        "discharge_date": patient["discharge_date"],
        "room_category": patient["room_category"],
        "insurer": patient["insurer"],
        "policy_number": patient["policy_number"],
        "status": patient["status"],
        "policy": {
            "policy_number": policy["policy_number"],
            "approved_limit": policy["approved_limit"],
            "approved_stay_days": policy["approved_stay_days"],
            "active_from": policy["active_from"],
            "active_to": policy["active_to"],
        } if policy else None,
    }


DATASETS = ["admissions", "policies", "emr_logs", "billing_ledger", "insurer_checklist"]

TRANSITIONS = {
    "intake_validated": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "INTAKE_RECEIVED": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "INTAKE_VALIDATED": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "INTAKE": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "PATIENT_STATE_CREATE": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "CREATE_PATIENT_STATE": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "ADMISSION_RECEIVED": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "PRE_AUTHORIZATION_PENDING": ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
    "extension_review": ("DAILY_STAY_OPERATIONS", "MIDSTAY_EXTENSION_REVIEW", "DISCHARGE_MONITORING"),
    "EXTENSION_REVIEW": ("DAILY_STAY_OPERATIONS", "MIDSTAY_EXTENSION_REVIEW", "DISCHARGE_MONITORING"),
    "discharge_trigger": (None, "DISCHARGE_REVIEW", "CLAIM_ASSEMBLY"),
    "DISCHARGE_TRIGGER": (None, "DISCHARGE_REVIEW", "CLAIM_ASSEMBLY"),
    "claim_readiness": ("DISCHARGE_REVIEW", "CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY"),
    "CLAIM_READINESS": ("DISCHARGE_REVIEW", "CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY"),
    "fhir_assembly": ("CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY", "CLAIM_SUBMITTED"),
    "FHIR_ASSEMBLY": ("CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY", "CLAIM_SUBMITTED"),
    "query_received": (None, "QUERY_RECEIVED", "QUERY_HANDLING"),
    "QUERY_RECEIVED": (None, "QUERY_RECEIVED", "QUERY_HANDLING"),
    "query_response_ready": ("QUERY_RECEIVED", "FACTUAL_RESPONSE_READY", "QUERY_HANDLING"),
    "QUERY_RESPONSE_READY": ("QUERY_RECEIVED", "FACTUAL_RESPONSE_READY", "QUERY_HANDLING"),
    "query_escalated": ("QUERY_RECEIVED", "URGENT_CLINICAL_REVIEW", "QUERY_HANDLING"),
    "QUERY_ESCALATED": ("QUERY_RECEIVED", "URGENT_CLINICAL_REVIEW", "QUERY_HANDLING"),
}


def get_patient(patient_id: str):
    patient = one("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    return patient


def blocking_conditions(patient_id: str) -> list[str]:
    patient = get_patient(patient_id)
    reasons: list[str] = []
    allergies = rows(
        "SELECT allergen, severity, recorded_date FROM allergies WHERE patient_id = ?",
        (patient_id,),
    )
    for a in allergies:
        severity = (a["severity"] or "").lower()
        recorded = (a["recorded_date"] or "")[:10]
        discharge = (patient["discharge_date"] or "")[:10]
        if severity in ("severe", "moderate") and (not discharge or recorded <= discharge):
            reasons.append(f"Critical allergy conflict: {a['allergen']}")
            break
    if patient["pending_confirmation"]:
        reasons.append(patient["pending_confirmation"])
    return reasons


def _state_for(patient_id: str):
    return one("SELECT * FROM state_records WHERE patient_id = ?", (patient_id,))


def _next_seq(table: str, column: str) -> int:
    row = one(f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1")
    if row is None:
        return 1
    try:
        return int(str(row[0]).rsplit("-", 1)[-1]) + 1
    except ValueError:
        return 1


class StateAdvanceBody(BaseModel):
    event: Optional[str] = None
    metadata: Optional[dict] = None


class AuditBody(BaseModel):
    patient_id: str
    action: str
    source_ids: Optional[list[str]] = None


class PolicyValidateBody(BaseModel):
    policy_number: str
    patient_id: Optional[str] = None


class RegistryBody(BaseModel):
    datasets: Optional[list[str]] = None


@router.post("/patients/{patient_id}/registry")
def register_datasets(patient_id: str, body: Optional[RegistryBody] = None):
    get_patient(patient_id)
    datasets = sorted(set((body.datasets if body else None) or DATASETS))
    indexed_records = {}
    if "admissions" in datasets:
        indexed_records["admissions"] = 1
    if "policies" in datasets:
        indexed_records["policies"] = 1
    if "emr_logs" in datasets:
        indexed_records["emr_logs"] = len(rows("SELECT note_id FROM emr_notes WHERE patient_id = ?", (patient_id,)))
    if "billing_ledger" in datasets:
        indexed_records["billing_ledger"] = len(rows("SELECT entry_id FROM ledger_entries WHERE patient_id = ?", (patient_id,)))
    if "insurer_checklist" in datasets:
        indexed_records["insurer_checklist"] = len(rows(
            "SELECT code FROM insurer_checklists WHERE insurer = (SELECT insurer FROM patients WHERE patient_id = ?)",
            (patient_id,),
        ))
    missing = []
    policy = one("SELECT * FROM policies WHERE patient_id = ?", (patient_id,))
    if policy is None:
        missing.append("policy")
    write(
        "INSERT OR REPLACE INTO registry (patient_id, datasets, indexed_records, missing_join_keys, registered_at) VALUES (?, ?, ?, ?, ?)",
        (patient_id, json_dumps(datasets), json_dumps(indexed_records), json_dumps(missing), utc_now()),
    )
    return {
        "patient_id": patient_id,
        "status": "registered",
        "datasets": datasets,
        "indexed_records": indexed_records,
        "missing_join_keys": missing,
    }


@router.post("/patients/{patient_id}/state/reset")
def reset_state(patient_id: str):
    get_patient(patient_id)
    write("DELETE FROM state_records WHERE patient_id = ?", (patient_id,))
    return {"patient_id": patient_id, "current_state": "INTAKE_RECEIVED", "reset": True}


@router.post("/patients/{patient_id}/state/advance")
def advance_state(patient_id: str, body: Optional[StateAdvanceBody] = None):
    get_patient(patient_id)
    event = body.event if body else None
    current = _state_for(patient_id)
    current_state = current["current_state"] if current else "INTAKE_RECEIVED"

    STATE_FLOW = [
        ("INTAKE_RECEIVED", "INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS"),
        ("INTAKE_VALIDATED", "DAILY_STAY_OPERATIONS", "DAILY_STAY_OPERATIONS"),
        ("DAILY_STAY_OPERATIONS", "MIDSTAY_EXTENSION_REVIEW", "DISCHARGE_MONITORING"),
        ("MIDSTAY_EXTENSION_REVIEW", "DISCHARGE_MONITORING", "DISCHARGE_MONITORING"),
        ("DISCHARGE_REVIEW", "CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY"),
        ("CLAIM_READINESS_CHECK", "FHIR_ASSEMBLY", "CLAIM_SUBMITTED"),
        ("QUERY_RECEIVED", "FACTUAL_RESPONSE_READY", "QUERY_HANDLING"),
        ("FACTUAL_RESPONSE_READY", "FACTUAL_RESPONSE_READY", "QUERY_HANDLING"),
    ]

    if event in TRANSITIONS:
        expected_from, to_state, next_state = TRANSITIONS[event]
        if expected_from and current_state != expected_from:
            return {
                "patient_id": patient_id,
                "transition_id": None,
                "event": event,
                "current_state": current_state,
                "next_state": None,
                "blocking": False,
                "blocking_reasons": [],
                "note": f"Already at '{current_state}', cannot transition with event '{event}'",
            }
    else:
        matched = False
        for from_s, to_s, nxt_s in STATE_FLOW:
            if current_state == from_s:
                to_state = to_s
                next_state = nxt_s
                matched = True
                break
        if not matched:
            to_state = current_state
            next_state = current_state

    reasons = blocking_conditions(patient_id)
    blocking = len(reasons) > 0
    if blocking and (event or "").upper() in ("DISCHARGE_TRIGGER", "CLAIM_READINESS", "FHIR_ASSEMBLY"):
        return {
            "patient_id": patient_id,
            "transition_id": None,
            "event": event,
            "current_state": current_state,
            "next_state": None,
            "blocking": True,
            "blocking_reasons": reasons,
        }
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        seq = _next_seq("state_records", "patient_id")
        transition_id = f"ST-{patient_id}-{seq:03d}"
        conn.execute(
            "INSERT INTO state_records (patient_id, current_state, next_state, blocking, transition_event, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(patient_id) DO UPDATE SET current_state=excluded.current_state, next_state=excluded.next_state, "
            "blocking=excluded.blocking, transition_event=excluded.transition_event, created_at=excluded.created_at",
            (patient_id, to_state, next_state, int(blocking), event, utc_now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "patient_id": patient_id,
        "transition_id": transition_id,
        "event": event,
        "current_state": to_state,
        "next_state": next_state,
        "blocking": blocking,
        "blocking_reasons": reasons,
    }


@router.post("/audit-trails")
def create_audit(body: AuditBody):
    get_patient(body.patient_id)
    seq = _next_seq("audit_trails", "audit_id")
    audit_id = f"AUD-{body.patient_id}-{seq:03d}"
    source_ids = body.source_ids or []
    write(
        "INSERT INTO audit_trails (audit_id, patient_id, action, source_ids, created_at) VALUES (?, ?, ?, ?, ?)",
        (audit_id, body.patient_id, body.action, json_dumps(source_ids), utc_now()),
    )
    return {
        "audit_id": audit_id,
        "patient_id": body.patient_id,
        "action": body.action,
        "source_ids": source_ids,
        "created_at": utc_now(),
    }


@router.get("/audit-trails/{patient_id}")
def list_audits(patient_id: str):
    get_patient(patient_id)
    audits = rows(
        "SELECT audit_id, patient_id, action, source_ids, created_at FROM audit_trails WHERE patient_id = ? ORDER BY created_at",
        (patient_id,),
    )
    return {"patient_id": patient_id, "audits": [dict(a) for a in audits]}


@router.post("/policies/validate")
def validate_policy(body: PolicyValidateBody):
    policy = one("SELECT * FROM policies WHERE policy_number = ?", (body.policy_number,))
    if policy is None:
        return {
            "policy_number": body.policy_number,
            "patient_id": body.patient_id,
            "valid": False,
            "result": "FAIL",
            "errors": ["Policy number not found"],
        }
    if body.patient_id and policy["patient_id"] != body.patient_id:
        return {
            "policy_number": body.policy_number,
            "patient_id": body.patient_id,
            "valid": False,
            "result": "FAIL",
            "errors": ["Policy is not linked to the supplied patient"],
        }
    return {
        "policy_number": policy["policy_number"],
        "patient_id": policy["patient_id"],
        "valid": True,
        "result": "PASS",
        "errors": [],
        "coverage_active_from": policy["active_from"],
        "coverage_active_to": policy["active_to"],
        "approved_limit": policy["approved_limit"],
        "approved_stay_days": policy["approved_stay_days"],
    }


@router.get("/patients/{patient_id}/stay-threshold")
def stay_threshold(patient_id: str, evaluation_date: Optional[str] = None):
    patient = get_patient(patient_id)
    policy = one("SELECT * FROM policies WHERE patient_id = ?", (patient_id,))
    approved_days = policy["approved_stay_days"] if policy else 0
    admission = datetime.strptime(patient["admission_date"], "%Y-%m-%d").date()
    eval_date = date.today()
    if evaluation_date:
        try:
            eval_date = datetime.strptime(evaluation_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            eval_date = date.today()
    active_days = max(0, (eval_date - admission).days)
    utilization = round(active_days / approved_days * 100) if approved_days else 0
    status = "extension_review_reached" if utilization >= 75 else "below_extension_threshold"
    return {
        "patient_id": patient_id,
        "admission_date": patient["admission_date"],
        "approved_stay_days": approved_days,
        "evaluation_date": eval_date.isoformat(),
        "active_stay_days": active_days,
        "utilization_percent": utilization,
        "threshold_status": status,
    }
