from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import rows, one, write, utc_now, json_dumps
from ..dependencies import require_token
from .intake import get_patient

router = APIRouter(dependencies=[Depends(require_token)])

ALLERGY_MED_MAP = {
    "cephalosporin": ["ceftriaxone", "cefuroxime", "cefixime", "cefepime", "cefpodoxime"],
    "penicillin": ["amoxicillin", "ampicillin", "piperacillin", "amoxiclav"],
    "sulfa": ["sulfamethoxazole", "sulfasalazine", "co-trimoxazole"],
    "nsaid": ["ibuprofen", "diclofenac", "naproxen", "ketorolac"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "ofloxacin"],
}


def _medication_terms():
    return [term for terms in ALLERGY_MED_MAP.values() for term in terms]


@router.get("/patients/{patient_id}/emr")
def emr_log_query(patient_id: str):
    get_patient(patient_id)
    notes = rows(
        "SELECT note_id, note_date, source, section, text FROM emr_notes WHERE patient_id = ? ORDER BY note_date, note_id",
        (patient_id,),
    )
    return {
        "patient_id": patient_id,
        "notes": [
            {
                "note_id": n["note_id"],
                "note_date": n["note_date"],
                "section": n["section"],
                "text": n["text"],
            }
            for n in notes
        ],
    }


class SectionsBody(BaseModel):
    note_ids: Optional[list[str]] = None


@router.post("/patients/{patient_id}/clinical-sections")
def clinical_section_mapper(patient_id: str, body: Optional[SectionsBody] = None):
    get_patient(patient_id)
    if body and body.note_ids:
        placeholders = ",".join("?" for _ in body.note_ids)
        notes = rows(
            f"SELECT note_id, note_date, section, is_clinical, text FROM emr_notes "
            f"WHERE patient_id = ? AND note_id IN ({placeholders}) ORDER BY note_date, note_id",
            (patient_id, *body.note_ids),
        )
    else:
        notes = rows(
            "SELECT note_id, note_date, section, is_clinical, text FROM emr_notes WHERE patient_id = ? ORDER BY note_date, note_id",
            (patient_id,),
        )
    if not notes:
        raise HTTPException(status_code=404, detail="No EMR notes found for patient")
    clinical = [n for n in notes if n["is_clinical"]]
    non_clinical = [n for n in notes if not n["is_clinical"]]
    if not clinical and non_clinical:
        rejected = [n["note_id"] for n in non_clinical]
        return {
            "patient_id": patient_id,
            "sections": [],
            "pending_confirmations": [],
            "non_clinical_rejected": rejected,
            "error": {
                "code": "NON_CLINICAL_SOURCE_REJECTED",
                "message": f"Rejected non-clinical source logs {', '.join(rejected)}; no clinical text to map.",
            },
        }
    sections: dict[str, list[dict]] = {}
    for n in clinical:
        section = n["section"] or "hospital_course"
        sections.setdefault(section, []).append(
            {"statement": n["text"], "citation": n["note_id"]}
        )
    ordered = ["diagnosis", "procedure", "hospital_course", "condition_at_discharge", "follow_up"]
    section_list = []
    for key in ordered:
        if key in sections:
            section_list.append({"section": key, "statements": sections[key]})
    for key, value in sections.items():
        if key not in ordered:
            section_list.append({"section": key, "statements": value})
    pending = []
    patient = one("SELECT pending_confirmation FROM patients WHERE patient_id = ?", (patient_id,))
    if patient and patient["pending_confirmation"]:
        pending.append(patient["pending_confirmation"])
    write(
        "INSERT OR REPLACE INTO summaries (patient_id, draft_sections, status, updated_at) VALUES (?, ?, ?, ?)",
        (patient_id, json_dumps(section_list), "DRAFT", utc_now()),
    )
    return {
        "patient_id": patient_id,
        "sections": section_list,
        "pending_confirmations": pending,
        "non_clinical_rejected": [n["note_id"] for n in non_clinical],
        "error": None,
    }


@router.post("/patients/{patient_id}/allergy-scan")
def allergy_conflict_scanner(patient_id: str, as_of: Optional[str] = None):
    patient = get_patient(patient_id)
    if as_of:
        allergies = rows(
            "SELECT allergen, severity, source_note_id FROM allergies WHERE patient_id = ? AND recorded_date <= ?",
            (patient_id, as_of[:10]),
        )
    else:
        allergies = rows("SELECT allergen, severity, source_note_id FROM allergies WHERE patient_id = ?", (patient_id,))
    med_terms = _medication_terms()
    active = rows(
        "SELECT text FROM emr_notes WHERE patient_id = ? AND section IN ('treatment','condition_at_discharge','procedure','hospital_course','diagnosis')",
        (patient_id,),
    )
    med_text = " ".join(n["text"] for n in active)
    conflicts = []
    recorded_allergies = []
    for a in allergies:
        allergen = a["allergen"]
        recorded_allergies.append({"allergen": allergen, "severity": a["severity"], "source_note_id": a["source_note_id"]})
        if allergen.lower() in ("no known drug allergies", "none"):
            continue
        matched_meds = []
        lowered = allergen.lower()
        for key, terms in ALLERGY_MED_MAP.items():
            if key in lowered:
                matched_meds = [t for t in terms if t in med_text.lower()]
                break
        if not matched_meds and allergen.lower() in med_text.lower():
            matched_meds = [allergen]
        if matched_meds:
            conflicts.append({
                "allergen": allergen,
                "severity": a["severity"],
                "conflicting_medication": matched_meds,
                "source_note_id": a["source_note_id"],
            })
    result = "BLOCKED" if any(c["severity"] in ("severe", "moderate") for c in conflicts) else "CLEAR"
    return {
        "patient_id": patient_id,
        "recorded_allergies": recorded_allergies,
        "active_medications": [n["text"] for n in active],
        "conflicts": conflicts,
        "result": result,
    }


@router.get("/patients/{patient_id}/clinical-justification")
def clinical_justification_extractor(patient_id: str, topic: str = "continuation_of_care", from_date: Optional[str] = None):
    get_patient(patient_id)
    if topic not in ("continuation_of_care", "payer_query"):
        raise HTTPException(status_code=422, detail="topic must be continuation_of_care or payer_query")
    if topic == "continuation_of_care":
        keywords = ["continue", "observe", "reassess", "repeat", "monitor", "tomorrow"]
        notes = rows("SELECT note_id, note_date, text FROM emr_notes WHERE patient_id = ?", (patient_id,))
        matches = []
        for n in notes:
            lowered = n["text"].lower()
            if any(k in lowered for k in keywords):
                matches.append(n)
    else:
        matches = rows(
            "SELECT e.note_id, e.note_date, e.text FROM emr_notes e "
            "JOIN nhcx_queries q ON instr(q.source_ids, e.note_id) > 0 "
            "WHERE q.patient_id = ? ORDER BY e.note_date",
            (patient_id,),
        )
    evidence = []
    for n in matches:
        if from_date and n["note_date"] < from_date:
            continue
        evidence.append({
            "log_id": n["note_id"],
            "note_date": n["note_date"],
            "excerpt": n["text"],
            "verbatim": True,
        })
    return {"patient_id": patient_id, "topic": topic, "evidence": evidence}
