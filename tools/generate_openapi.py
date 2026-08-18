"""Generate Yoxa-compatible connector OpenAPI files (one operation per file).

Run: python tools/generate_openapi.py
Output: yoxa/openapi/*.openapi.yml
The servers[0].url is a placeholder origin. Replace it with the real public
HTTPS origin after deployment, then re-run this script with --origin.
"""

import argparse
import sys
from pathlib import Path

ORIGIN_PLACEHOLDER = "https://claims-backend.example.invalid"

BASE = Path(__file__).resolve().parent.parent / "yoxa" / "openapi"

HEADER = "# Generated connector document for Yoxa API Configuration."


def indent(block: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in block.splitlines())


def relativeize(block: str, spaces: int) -> str:
    out = []
    for line in block.splitlines():
        if line.strip():
            stripped = line[spaces:] if len(line) >= spaces and not line[:spaces].strip() else line
            out.append(stripped)
        else:
            out.append("")
    return "\n".join(out)


def build_parameters(params: list[dict]) -> str:
    if not params:
        return ""
    lines = ["parameters:"]
    for p in params:
        loc = p["in"]
        lines.append(f"  - name: {p['name']}")
        lines.append(f"    in: {loc}")
        if loc == "path":
            lines.append("    required: true")
        elif loc == "query":
            lines.append(f"    required: {str(p.get('required', False)).lower()}")
        lines.append("    schema:")
        lines.append(f"      type: {p.get('type', 'string')}")
        if "enum" in p:
            lines.append(f"      enum: {p['enum']}")
        if "desc" in p:
            lines.append(f"    description: {p['desc']}")
    return "\n".join(lines) + "\n"


def build_request_body(body: str, required: bool) -> str:
    if body is None:
        return ""
    req = "true" if required else "false"
    return (
        f"requestBody:\n"
        f"  required: {req}\n"
        f"  content:\n"
        f"    application/json:\n"
        f"      schema:\n"
        f"{body}"
    )


def build_file(op: dict, origin: str, *, no_auth: bool = False) -> str:
    params = build_parameters(op.get("params", []))
    request_body = build_request_body(op.get("request_body"), op.get("request_body_required", False))
    lines = [
        HEADER,
        "openapi: 3.1.0",
        "info:",
        f"  title: {op['title']}",
        "  version: 0.1.0",
        "servers:",
        f"  - url: {origin}",
        "paths:",
        f"  /api{op['path']}:",
        f"    {op['method']}:",
        f"      operationId: {op['opid']}",
        f"      summary: \"{op['summary']}\"",
        f"      description: \"{op['desc']}\"",
    ]
    if not no_auth:
        lines.append("      security:")
        lines.append("        - clientApiBearer: []")
    if params:
        lines.append(indent(params.rstrip("\n"), 6))
    if request_body:
        lines.append(indent(request_body.rstrip("\n"), 6))
    lines += [
        "      responses:",
        "        '200':",
        f"          description: {op.get('response_desc', 'Successful response')}",
        "          content:",
        "            application/json:",
        "              schema:",
        indent(relativeize(op["response_200"], 12).rstrip("\n"), 16),
    ]
    if not no_auth:
        lines += [
            "components:",
            "  securitySchemes:",
            "    clientApiBearer:",
            "      type: http",
            "      scheme: bearer",
        ]
    return "\n".join(lines) + "\n"


PATIENT_PATH = [{"name": "patient_id", "in": "path", "desc": "Patient identifier, e.g. PAT-10482."}]

OPS = [
    {
        "file": "dataset-ingestion-registry",
        "title": "Dataset Ingestion Registry",
        "opid": "registerPatientDatasets",
        "method": "post",
        "path": "/patients/{patient_id}/registry",
        "summary": "Register the five CSV datasets for a patient",
        "desc": "Indexes the admissions, policies, EMR, billing ledger and insurer checklist datasets for a patient and reports missing join keys.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              status:\n                type: string\n                enum: [registered]\n"
            "              datasets:\n                type: array\n                items:\n                  type: string\n"
            "              indexed_records:\n                type: object\n                additionalProperties:\n                  type: integer\n"
            "              missing_join_keys:\n                type: array\n                items:\n                  type: string\n"
            "            required: [patient_id, status, datasets, indexed_records, missing_join_keys]\n"
        ),
    },
    {
        "file": "process-state-machine-router",
        "title": "Process State Machine Router",
        "opid": "advancePatientState",
        "method": "post",
        "path": "/patients/{patient_id}/state/advance",
        "summary": "Advance the patient's workflow state",
        "desc": "Advances the ordered workflow state for a patient. Events: intake_validated, extension_review, discharge_trigger, claim_readiness, fhir_assembly, query_received, query_response_ready, query_escalated. Returns 409 when the transition is blocked by a safety gate or invalid state order.",
        "params": PATIENT_PATH,
        "request_body": (
            "              type: object\n"
            "              required: [event]\n"
            "              properties:\n"
            "                event:\n                  type: string\n"
            "                metadata:\n                  type: [\"object\", \"null\"]\n"
        ),
        "request_body_required": True,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              transition_id:\n                type: string\n"
            "              event:\n                type: string\n"
            "              current_state:\n                type: string\n"
            "              next_state:\n                type: string\n"
            "              blocking:\n                type: boolean\n"
            "              blocking_reasons:\n                type: array\n                items:\n                  type: string\n"
            "            required: [patient_id, transition_id, event, current_state, next_state, blocking, blocking_reasons]\n"
        ),
    },
    {
        "file": "action-execution-auditor",
        "title": "Action Execution Auditor",
        "opid": "createAuditTrail",
        "method": "post",
        "path": "/audit-trails",
        "summary": "Record an audited agent action",
        "desc": "Records an agent action with timestamp and source record identifiers and returns the audit id.",
        "params": [],
        "request_body": (
            "              type: object\n"
            "              required: [patient_id, action]\n"
            "              properties:\n"
            "                patient_id:\n                  type: string\n"
            "                action:\n                  type: string\n"
            "                source_ids:\n                  type: [\"array\", \"null\"]\n"
            "                  items:\n                    type: string\n"
        ),
        "request_body_required": True,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              audit_id:\n                type: string\n"
            "              patient_id:\n                type: string\n"
            "              action:\n                type: string\n"
            "              source_ids:\n                type: array\n                items:\n                  type: string\n"
            "              created_at:\n                type: string\n"
            "            required: [audit_id, patient_id, action, source_ids, created_at]\n"
        ),
    },
    {
        "file": "policy-eligibility-validator",
        "title": "Policy Eligibility Validator",
        "opid": "validatePolicyEligibility",
        "method": "post",
        "path": "/policies/validate",
        "summary": "Validate a policy number for eligibility",
        "desc": "Checks a policy number against the standard format and the supplied patient, returning PASS or FAIL with coverage metadata.",
        "params": [],
        "request_body": (
            "              type: object\n"
            "              required: [policy_number]\n"
            "              properties:\n"
            "                policy_number:\n                  type: string\n"
            "                patient_id:\n                  type: [\"string\", \"null\"]\n"
        ),
        "request_body_required": True,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              policy_number:\n                type: string\n"
            "              patient_id:\n                type: [\"string\", \"null\"]\n"
            "              valid:\n                type: boolean\n"
            "              result:\n                type: string\n                enum: [PASS, FAIL]\n"
            "              errors:\n                type: array\n                items:\n                  type: string\n"
            "              coverage_active_from:\n                type: [\"string\", \"null\"]\n"
            "              coverage_active_to:\n                type: [\"string\", \"null\"]\n"
            "              approved_limit:\n                type: [\"number\", \"null\"]\n"
            "              approved_stay_days:\n                type: [\"integer\", \"null\"]\n"
            "            required: [policy_number, valid, result, errors]\n"
        ),
    },
    {
        "file": "stay-threshold-tracker",
        "title": "Stay Threshold Tracker",
        "opid": "getStayThreshold",
        "method": "get",
        "path": "/patients/{patient_id}/stay-threshold",
        "summary": "Calculate active stay against approved stay days",
        "desc": "Computes active inpatient days and utilization percentage against approved_stay_days as of an optional evaluation date.",
        "params": PATIENT_PATH + [
            {"name": "evaluation_date", "in": "query", "required": False, "type": "string", "desc": "Evaluation date YYYY-MM-DD. Defaults to today."},
        ],
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              admission_date:\n                type: string\n"
            "              approved_stay_days:\n                type: integer\n"
            "              evaluation_date:\n                type: string\n"
            "              active_stay_days:\n                type: integer\n"
            "              utilization_percent:\n                type: integer\n"
            "              threshold_status:\n                type: string\n"
            "                enum: [below_extension_threshold, extension_review_reached]\n"
            "            required: [patient_id, admission_date, approved_stay_days, evaluation_date, active_stay_days, utilization_percent, threshold_status]\n"
        ),
    },
    {
        "file": "emr-log-query",
        "title": "EMR Log Query",
        "opid": "getEmrLogs",
        "method": "get",
        "path": "/patients/{patient_id}/emr",
        "summary": "Retrieve chronological EMR notes",
        "desc": "Returns patient-specific EMR notes ordered chronologically with source identifiers.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              notes:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    note_id:\n                      type: string\n"
            "                    note_date:\n                      type: string\n"
            "                    section:\n                      type: string\n"
            "                    text:\n                      type: string\n"
            "                  required: [note_id, note_date, section, text]\n"
            "            required: [patient_id, notes]\n"
        ),
    },
    {
        "file": "clinical-section-mapper",
        "title": "Clinical Section Mapper",
        "opid": "mapClinicalSections",
        "method": "post",
        "path": "/patients/{patient_id}/clinical-sections",
        "summary": "Map explicit EMR text into structured summary sections",
        "desc": "Maps explicit clinician text into discharge-summary sections with citations and rejects non-clinical sources. A discharge summary draft is persisted.",
        "params": PATIENT_PATH,
        "request_body": (
            "              type: object\n"
            "              properties:\n"
            "                note_ids:\n                  type: [\"array\", \"null\"]\n"
            "                  items:\n                    type: string\n"
        ),
        "request_body_required": False,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              sections:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    section:\n                      type: string\n"
            "                    statements:\n                      type: array\n"
            "                      items:\n                        type: object\n"
            "                        properties:\n"
            "                          statement:\n                            type: string\n"
            "                          citation:\n                            type: string\n"
            "                        required: [statement, citation]\n"
            "                  required: [section, statements]\n"
            "              pending_confirmations:\n                type: array\n                items:\n                  type: string\n"
            "              non_clinical_rejected:\n                type: array\n                items:\n                  type: string\n"
            "              error:\n                type: [\"object\", \"null\"]\n"
            "                properties:\n"
            "                  code:\n                    type: string\n"
            "                  message:\n                    type: string\n"
            "            required: [patient_id, sections, pending_confirmations, non_clinical_rejected, error]\n"
        ),
    },
    {
        "file": "allergy-conflict-scanner",
        "title": "Allergy Conflict Scanner",
        "opid": "scanAllergyConflicts",
        "method": "post",
        "path": "/patients/{patient_id}/allergy-scan",
        "summary": "Scan medication-allergy conflicts",
        "desc": "Cross-references recorded allergies against active and discharge medications using drug-class matching, returning CLEAR or BLOCKED.",
        "params": PATIENT_PATH + [
            {"name": "as_of", "in": "query", "required": False, "type": "string", "desc": "Only consider allergies recorded on or before this date YYYY-MM-DD."},
        ],
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              recorded_allergies:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    allergen:\n                      type: string\n"
            "                    severity:\n                      type: string\n"
            "                    source_note_id:\n                      type: string\n"
            "              active_medications:\n                type: array\n                items:\n                  type: string\n"
            "              conflicts:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    allergen:\n                      type: string\n"
            "                    severity:\n                      type: string\n"
            "                    conflicting_medication:\n                      type: array\n"
            "                      items:\n                        type: string\n"
            "                    source_note_id:\n                      type: string\n"
            "              result:\n                type: string\n                enum: [CLEAR, BLOCKED]\n"
            "            required: [patient_id, recorded_allergies, active_medications, conflicts, result]\n"
        ),
    },
    {
        "file": "ledger-reconciler",
        "title": "Ledger Reconciler",
        "opid": "reconcileLedger",
        "method": "get",
        "path": "/patients/{patient_id}/ledger/reconciliation",
        "summary": "Reconcile the patient ledger",
        "desc": "Calculates gross, credits and net totals from exact ledger entries and reports unmatched charges.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              entries_count:\n                type: integer\n"
            "              gross_total:\n                type: number\n"
            "              credits_total:\n                type: number\n"
            "              net_total:\n                type: number\n"
            "              unmatched_amount:\n                type: number\n"
            "              unmatched_entry_ids:\n                type: array\n                items:\n                  type: string\n"
            "              entry_ids:\n                type: array\n                items:\n                  type: string\n"
            "            required: [patient_id, entries_count, gross_total, credits_total, net_total, unmatched_amount, unmatched_entry_ids, entry_ids]\n"
        ),
    },
    {
        "file": "duplicate-charge-auditor",
        "title": "Duplicate Charge Auditor",
        "opid": "auditDuplicateCharges",
        "method": "get",
        "path": "/patients/{patient_id}/ledger/duplicates",
        "summary": "Detect same-day duplicate charges",
        "desc": "Finds duplicate same-day billing entries for the same patient, item and charge context.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              duplicate_count:\n                type: integer\n"
            "              duplicate_value:\n                type: number\n"
            "              duplicates:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    entry_date:\n                      type: string\n"
            "                    description:\n                      type: string\n"
            "                    amount:\n                      type: number\n"
            "                    entry_ids:\n                      type: array\n"
            "                      items:\n                        type: string\n"
            "            required: [patient_id, duplicate_count, duplicate_value, duplicates]\n"
        ),
    },
    {
        "file": "floor-clerk-exception-notifier",
        "title": "Floor Clerk Exception Notifier",
        "opid": "getFloorClerkExceptions",
        "method": "get",
        "path": "/patients/{patient_id}/floor-clerk-exceptions",
        "summary": "List unmatched order exceptions",
        "desc": "Returns the unmatched order-to-charge exceptions queued for the floor clerk.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              queue:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    order_id:\n                      type: string\n"
            "                    reason:\n                      type: string\n"
            "                    status:\n                      type: string\n"
            "                    created_at:\n                      type: string\n"
            "              last_reconciliation:\n                type: [\"string\", \"null\"]\n"
            "              next_sweep_due_hours:\n                type: integer\n"
            "            required: [patient_id, queue, last_reconciliation, next_sweep_due_hours]\n"
        ),
    },
    {
        "file": "clinical-justification-extractor",
        "title": "Clinical Justification Extractor",
        "opid": "extractClinicalJustification",
        "method": "get",
        "path": "/patients/{patient_id}/clinical-justification",
        "summary": "Extract verbatim physician passages",
        "desc": "Extracts explicit, date-matched continuation-of-care or payer-query evidence verbatim with exact log identifiers.",
        "params": PATIENT_PATH + [
            {"name": "topic", "in": "query", "required": False, "type": "string", "enum": "[continuation_of_care, payer_query]", "desc": "Extraction topic. Defaults to continuation_of_care."},
            {"name": "from_date", "in": "query", "required": False, "type": "string", "desc": "Only evidence on or after this date YYYY-MM-DD."},
        ],
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              topic:\n                type: string\n"
            "              evidence:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    log_id:\n                      type: string\n"
            "                    note_date:\n                      type: string\n"
            "                    excerpt:\n                      type: string\n"
            "                    verbatim:\n                      type: boolean\n"
            "                  required: [log_id, note_date, excerpt, verbatim]\n"
            "            required: [patient_id, topic, evidence]\n"
        ),
    },
    {
        "file": "checklist-requirement-verifier",
        "title": "Checklist Requirement Verifier",
        "opid": "verifyChecklistRequirements",
        "method": "post",
        "path": "/patients/{patient_id}/checklist-verification",
        "summary": "Verify insurer requirements C1-C8",
        "desc": "Checks the eight insurer requirements C1-C8 against available records. C8 is sourced from the audited billing ledger. Returns blocking reasons when a safety gate is active.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              checklist_version:\n                type: string\n"
            "              requirements:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    code:\n                      type: string\n"
            "                    description:\n                      type: string\n"
            "                    status:\n                      type: string\n"
            "                      enum: [present, missing]\n"
            "                    source:\n                      type: string\n"
            "              missing_count:\n                type: integer\n"
            "              missing_codes:\n                type: array\n                items:\n                  type: string\n"
            "              blocking_reasons:\n                type: array\n                items:\n                  type: string\n"
            "            required: [patient_id, checklist_version, requirements, missing_count, missing_codes, blocking_reasons]\n"
        ),
    },
    {
        "file": "insurer-checklist-query",
        "title": "Insurer Checklist Query",
        "opid": "getInsurerChecklist",
        "method": "get",
        "path": "/patients/{patient_id}/insurer-checklist",
        "summary": "Retrieve insurer checklist requirements",
        "desc": "Returns the insurer checklist version and the C1-C8 requirement definitions for the patient's insurer.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              insurer:\n                type: string\n"
            "              checklist_version:\n                type: [\"string\", \"null\"]\n"
            "              requirements:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    code:\n                      type: string\n"
            "                    description:\n                      type: string\n"
            "                  required: [code, description]\n"
            "            required: [insurer, checklist_version, requirements]\n"
        ),
    },
    {
        "file": "payer-query-classifier",
        "title": "Payer Query Classifier",
        "opid": "listPayerQueries",
        "method": "get",
        "path": "/patients/{patient_id}/nhcx-queries",
        "summary": "List inbound payer queries with classification",
        "desc": "Returns inbound NHCX payer queries for the patient with their classification (factual, clinical, or urgent clinical escalation) and status.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              patient_id:\n                type: string\n"
            "              queries:\n                type: array\n"
            "                items:\n                  type: object\n"
            "                  properties:\n"
            "                    query_id:\n                      type: string\n"
            "                    claim_id:\n                      type: [\"string\", \"null\"]\n"
            "                    text:\n                      type: string\n"
            "                    classification:\n                      type: string\n"
            "                      enum: [FACTUAL, CLINICAL, URGENT_CLINICAL_ESCALATION]\n"
            "                    status:\n                      type: string\n"
            "                    received_at:\n                      type: string\n"
            "                    transmitted_at:\n                      type: [\"string\", \"null\"]\n"
            "                  required: [query_id, text, classification, status, received_at]\n"
            "            required: [patient_id, queries]\n"
        ),
    },
    {
        "file": "nhcx-query-gateway",
        "title": "NHCX Query Gateway",
        "opid": "respondToPayerQuery",
        "method": "post",
        "path": "/patients/{patient_id}/nhcx-queries/{query_id}/respond",
        "summary": "Transmit a governed payer query response",
        "desc": "Transmits a factual or approved clinical response through NHCX, or blocks/escalates when the query is an urgent clinical escalation.",
        "params": PATIENT_PATH + [
            {"name": "query_id", "in": "path", "desc": "NHCX query identifier, e.g. NHCX-Q-99107."},
        ],
        "request_body": (
            "              type: object\n"
            "              properties:\n"
            "                response_payload:\n                  type: [\"object\", \"null\"]\n"
        ),
        "request_body_required": False,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              query_id:\n                type: string\n"
            "              patient_id:\n                type: string\n"
            "              disposition:\n                type: string\n"
            "                enum: [RESOLVED, ESCALATED, BLOCKED]\n"
            "              receipt:\n                type: [\"string\", \"null\"]\n"
            "              transmitted_at:\n                type: [\"string\", \"null\"]\n"
            "              blocked_reason:\n                type: [\"string\", \"null\"]\n"
            "            required: [query_id, patient_id, disposition, receipt, transmitted_at, blocked_reason]\n"
        ),
    },
    {
        "file": "fhir-payload-builder",
        "title": "FHIR Payload Builder",
        "opid": "buildFhirBundle",
        "method": "post",
        "path": "/patients/{patient_id}/fhir-bundle",
        "summary": "Build the encrypted FHIR R4 claim bundle",
        "desc": "Compiles the approved claim records into an HL7 FHIR R4 claim bundle metadata record. Returns 409 when a blocking safety gate is active. Encryption is a marked placeholder envelope.",
        "params": PATIENT_PATH,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              bundle_id:\n                type: string\n"
            "              patient_id:\n                type: string\n"
            "              resource_types:\n                type: array\n                items:\n                  type: string\n"
            "              claimed_amount:\n                type: number\n"
            "              validation:\n                type: string\n"
            "                enum: [PASS]\n"
            "              status:\n                type: string\n"
            "                enum: [BUILT, SUBMITTED]\n"
            "              encryption:\n                type: object\n"
            "                properties:\n"
            "                  algorithm:\n                    type: string\n"
            "                  note:\n                    type: string\n"
            "            required: [bundle_id, patient_id, resource_types, claimed_amount, validation, status, encryption]\n"
        ),
    },
    {
        "file": "nhcx-gateway-transmitter",
        "title": "NHCX Gateway Transmitter",
        "opid": "submitClaim",
        "method": "post",
        "path": "/patients/{patient_id}/claims/submit",
        "summary": "Submit the claim through NHCX",
        "desc": "Validates and submits the approved FHIR claim bundle through NHCX and returns the transmission receipt and payer response deadline. Returns 409 when a blocking safety gate is active.",
        "params": PATIENT_PATH,
        "request_body": (
            "              type: object\n"
            "              properties:\n"
            "                bundle_id:\n                  type: [\"string\", \"null\"]\n"
        ),
        "request_body_required": False,
        "response_200": (
            "            type: object\n"
            "            properties:\n"
            "              claim_id:\n                type: string\n"
            "              bundle_id:\n                type: string\n"
            "              receipt:\n                type: string\n"
            "              status:\n                type: string\n"
            "                enum: [SUBMITTED]\n"
            "              submitted_at:\n                type: string\n"
            "              payer_response_deadline:\n                type: string\n"
            "            required: [claim_id, bundle_id, receipt, status, submitted_at, payer_response_deadline]\n"
        ),
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default=ORIGIN_PLACEHOLDER, help="Public HTTPS origin, e.g. https://my-api.example")
    parser.add_argument("--no-auth", action="store_true", help="Omit Bearer security scheme (for local dev; re-add at deployment)")
    args = parser.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    for op in OPS:
        content = build_file(op, args.origin, no_auth=args.no_auth)
        out = BASE / f"{op['file']}.openapi.yml"
        out.write_text(content, encoding="utf-8")
        print(f"wrote {out.relative_to(BASE.parent.parent)}")
    print(f"\n{len(OPS)} files written to {BASE}. Origin used: {args.origin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
