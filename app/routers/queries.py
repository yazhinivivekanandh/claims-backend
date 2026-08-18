import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, utc_now, json_dumps
from ..dependencies import require_token
from .intake import get_patient

router = APIRouter(dependencies=[Depends(require_token)])


@router.get("/patients/{patient_id}/nhcx-queries")
def payer_query_classifier(patient_id: str):
    get_patient(patient_id)
    queries = rows(
        "SELECT query_id, claim_id, text, classification, status, received_at, transmitted_at FROM nhcx_queries WHERE patient_id = ? ORDER BY received_at",
        (patient_id,),
    )
    return {
        "patient_id": patient_id,
        "queries": [
            {
                "query_id": q["query_id"],
                "claim_id": q["claim_id"],
                "text": q["text"],
                "classification": q["classification"],
                "status": q["status"],
                "received_at": q["received_at"],
                "transmitted_at": q["transmitted_at"],
            }
            for q in queries
        ],
    }


class RespondBody(BaseModel):
    response_payload: Optional[dict] = None


@router.post("/patients/{patient_id}/nhcx-queries/{query_id}/respond")
def nhcx_query_gateway(patient_id: str, query_id: str, body: Optional[RespondBody] = None):
    get_patient(patient_id)
    query = one(
        "SELECT * FROM nhcx_queries WHERE patient_id = ? AND query_id = ?",
        (patient_id, query_id),
    )
    if query is None:
        raise HTTPException(status_code=404, detail=f"Unknown query {query_id} for patient {patient_id}")
    classification = query["classification"]
    if classification == "URGENT_CLINICAL_ESCALATION":
        write(
            "UPDATE nhcx_queries SET status = 'ESCALATED', transmitted_at = NULL WHERE query_id = ?",
            (query_id,),
        )
        return {
            "query_id": query_id,
            "patient_id": patient_id,
            "disposition": "ESCALATED",
            "receipt": None,
            "transmitted_at": None,
            "blocked_reason": "Urgent clinical escalation: no response is transmitted until therapeutic reconciliation is completed by the medical director.",
        }
    if classification == "CLINICAL" and not (body and body.response_payload):
        return {
            "query_id": query_id,
            "patient_id": patient_id,
            "disposition": "BLOCKED",
            "receipt": None,
            "transmitted_at": None,
            "blocked_reason": "Clinical query requires a consultant-approved response payload before transmission.",
        }
    seq = int(one("SELECT COUNT(*) AS c FROM nhcx_queries")["c"]) + 1
    receipt = f"NHCX-RESP-{query_id}-{random.randint(1000, 9999)}"
    transmitted_at = utc_now()
    write(
        "UPDATE nhcx_queries SET status = 'RESOLVED', response = ?, receipt = ?, transmitted_at = ? WHERE query_id = ?",
        (json_dumps(body.response_payload if body and body.response_payload else {}), receipt, transmitted_at, query_id),
    )
    return {
        "query_id": query_id,
        "patient_id": patient_id,
        "disposition": "RESOLVED",
        "receipt": receipt,
        "transmitted_at": transmitted_at,
        "blocked_reason": None,
    }
