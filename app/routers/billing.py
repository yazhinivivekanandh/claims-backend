from fastapi import APIRouter, Depends

from ..db import rows
from ..dependencies import require_token
from .intake import get_patient

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/ledger/reconciliation")
def ledger_reconciler(patient_id: str):
    get_patient(patient_id)
    entries = rows(
        "SELECT entry_id, entry_date, description, amount, is_credit FROM ledger_entries WHERE patient_id = ? ORDER BY entry_id",
        (patient_id,),
    )
    gross = round(sum(e["amount"] for e in entries if not e["is_credit"]), 2)
    credits = round(sum(e["amount"] for e in entries if e["is_credit"]), 2)
    net = round(gross - credits, 2)
    orders = rows("SELECT order_id, charge_entry_id FROM orders WHERE patient_id = ?", (patient_id,))
    charge_ids = {o["charge_entry_id"] for o in orders}
    unmatched_entries = [e["entry_id"] for e in entries if not e["is_credit"] and e["entry_id"] not in charge_ids]
    return {
        "patient_id": patient_id,
        "entries_count": len(entries),
        "gross_total": gross,
        "credits_total": credits,
        "net_total": net,
        "unmatched_amount": 0.0,
        "unmatched_entry_ids": unmatched_entries,
        "entry_ids": [e["entry_id"] for e in entries],
    }


@router.get("/patients/{patient_id}/ledger/duplicates")
def duplicate_charge_auditor(patient_id: str):
    get_patient(patient_id)
    entries = rows(
        "SELECT entry_id, entry_date, description, amount FROM ledger_entries WHERE patient_id = ? AND is_credit = 0 ORDER BY entry_id",
        (patient_id,),
    )
    seen: dict[tuple, list] = {}
    for e in entries:
        key = (e["entry_date"], e["description"], e["amount"])
        seen.setdefault(key, []).append(e["entry_id"])
    duplicates = {k: v for k, v in seen.items() if len(v) > 1}
    duplicate_value = round(sum(k[2] * (len(v) - 1) for k, v in duplicates.items()), 2)
    return {
        "patient_id": patient_id,
        "duplicate_count": len(duplicates),
        "duplicate_value": duplicate_value,
        "duplicates": [
            {
                "entry_date": k[0],
                "description": k[1],
                "amount": k[2],
                "entry_ids": v,
            }
            for k, v in duplicates.items()
        ],
    }


@router.get("/patients/{patient_id}/floor-clerk-exceptions")
def floor_clerk_exception_notifier(patient_id: str):
    get_patient(patient_id)
    exceptions = rows(
        "SELECT order_id, reason, status, created_at FROM floor_clerk_exceptions WHERE patient_id = ? ORDER BY created_at",
        (patient_id,),
    )
    return {
        "patient_id": patient_id,
        "queue": [
            {
                "order_id": e["order_id"],
                "reason": e["reason"],
                "status": e["status"],
                "created_at": e["created_at"],
            }
            for e in exceptions
        ],
        "last_reconciliation": None,
        "next_sweep_due_hours": 24,
    }
