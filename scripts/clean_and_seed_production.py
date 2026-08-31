import google.auth
from google.cloud import firestore
import httpx
import os

def clean_and_seed():
    project_id = "project-f230e9c2-3257-4981-86f"
    db = firestore.Client(project=project_id)

    print("Cleaning old test decisions from Firestore...")
    decisions_ref = db.collection("decisions")
    ledger_ref = db.collection("ledger")

    # Delete all existing decisions and ledger entries
    batch = db.batch()
    count = 0
    for doc in decisions_ref.stream():
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    batch.commit()

    batch = db.batch()
    count = 0
    for doc in ledger_ref.stream():
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    batch.commit()

    print("Firestore cleaned! Seeding 6 production decisions...")

    prod_url = "https://aegis-708478134642.us-central1.run.app/api/v1/decisions"

    # 1. Gene Lokken Case 2048 (Flagged)
    r1 = httpx.post(prod_url, json={
        "source": "Benefits Engine",
        "subject": "Case 2048 (Gene Lokken)",
        "requested_service": "Post-acute skilled nursing care",
        "original_decision": "denied",
        "policy_id": "CMS-SNF-100",
        "facts": {
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 19,
            "requested_days": 7
        }
    }, timeout=60.0)
    d1 = r1.json()
    print(f"Seeded 1 (Flagged): {d1['id']} -> {d1['status']}")

    # 2. Cigna PxDx Bulk Denial Incident (Flagged)
    r2 = httpx.post(prod_url, json={
        "source": "Cigna PxDx Batch",
        "subject": "Patient #4812",
        "requested_service": "Diagnostic Mammogram & Ultrasound",
        "original_decision": "denied",
        "policy_id": "CMS-SNF-100",
        "facts": {
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 5,
            "requested_days": 1
        }
    }, timeout=60.0)
    d2 = r2.json()
    print(f"Seeded 2 (Flagged): {d2['id']} -> {d2['status']}")

    # 3. Case 7781 (Flagged - Exceeds Benefit Days)
    r3 = httpx.post(prod_url, json={
        "source": "Pub/Sub stream",
        "subject": "Case 7781",
        "requested_service": "Extended SNF stay",
        "original_decision": "approved",
        "policy_id": "CMS-SNF-100",
        "facts": {
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 95,
            "requested_days": 10
        }
    }, timeout=60.0)
    d3 = r3.json()
    print(f"Seeded 3 (Flagged): {d3['id']} -> {d3['status']}")

    # 4. Control Case A (Upheld - Custodial Care Only)
    r4 = httpx.post(prod_url, json={
        "source": "Claims Engine",
        "subject": "Control Case A (Custodial Care)",
        "requested_service": "Long-term Custodial Assistance",
        "original_decision": "denied",
        "policy_id": "CMS-SNF-100",
        "facts": {
            "medically_necessary": True,
            "skilled_care_required": False, # Denial supported!
            "benefit_days_used": 10,
            "requested_days": 30
        }
    }, timeout=60.0)
    d4 = r4.json()
    print(f"Seeded 4 (Upheld): {d4['id']} -> {d4['status']}")

    # 5. Control Case B (Upheld - Exhausted Benefits)
    r5 = httpx.post(prod_url, json={
        "source": "Claims Engine",
        "subject": "Control Case B (Exhausted Benefits)",
        "requested_service": "Skilled Nursing Extension",
        "original_decision": "denied",
        "policy_id": "CMS-SNF-100",
        "facts": {
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 100, # Denial supported!
            "requested_days": 10
        }
    }, timeout=60.0)
    d5 = r5.json()
    print(f"Seeded 5 (Upheld): {d5['id']} -> {d5['status']}")

    # 6. Forked Case 2048 (Upheld)
    r6 = httpx.post(f"https://aegis-708478134642.us-central1.run.app/api/v1/decisions/{d1['id']}/fork", json={
        "original_decision": "approved",
        "note": "corrected source decision"
    }, timeout=60.0)
    d6 = r6.json()
    print(f"Seeded 6 (Upheld/Forked): {d6['id']} -> {d6['status']}")

    print("\nProduction Firestore cleaned and seeded successfully!")

if __name__ == "__main__":
    clean_and_seed()
