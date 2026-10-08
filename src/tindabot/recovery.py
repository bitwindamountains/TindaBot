"""Redacted delivery inspection and optimistic recovery snapshots."""

import hashlib
import json

ERRORS = {
    "lease_expired": "The worker lost its delivery lease. Check the provider before retrying.",
    "meta_credentials": "Check the Messenger credentials and resume automation when ready.",
    "smtp_credentials": "Check the seller email credentials before retrying.",
    "sheet_headers": "Restore the required seller Sheet headers before retrying.",
    "sheet_duplicate_order": "Reconcile duplicate order rows in the seller Sheet first.",
    "missing_delivery_target": "The delivery target is missing. Inspect the related order first.",
}
SAFE_CODES = set(ERRORS) | {
    "meta_connect",
    "meta_transport_unknown",
    "meta_throttled",
    "meta_server_unknown",
    "meta_transient",
    "meta_rejected",
    "smtp_delivery_unknown",
}


def revision(job):
    fields = [job.id, job.status, job.attempts, job.next_attempt, job.lease_token, job.error]
    return hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def inspect_job(job):
    code = job.error if job.error in SAFE_CODES else "delivery_error"
    return {
        "id": job.id,
        "destination": job.destination
        if job.destination in {"messenger", "sheets", "email"}
        else "other",
        "status": job.status,
        "attempts": job.attempts,
        "created_at": job.created_at,
        "order_id": job.order_id,
        "revision": revision(job),
        "error_code": code,
        "guidance": ERRORS.get(
            code, "Check the provider result and configuration before deciding whether to retry."
        ),
    }
