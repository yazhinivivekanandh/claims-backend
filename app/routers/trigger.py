import uuid
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

YOXA_TRIGGER_URL = "https://yoxa.ai/api/v1/public/workflow-deployments/de17ed08-72c9-4a24-a6ef-8dae3c21e41e/trigger"
YOXA_SECRET = "yoxa_dep_K8v39mWOC3vtZEVZ5C94Yik0DnjMcXQF5A3Z9LFz9mw"


class TriggerBody(BaseModel):
    patient_id: str


@router.post("/trigger")
async def trigger_workflow(body: TriggerBody):
    headers = {
        "X-Yoxa-Deployment-Secret": YOXA_SECRET,
        "Idempotency-Key": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    payload = {"trigger_text": body.patient_id}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(YOXA_TRIGGER_URL, json=payload, headers=headers)

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Yoxa error: {resp.text}")

    return {"status": "triggered", "patient_id": body.patient_id, "yoxa_response": resp.json()}
