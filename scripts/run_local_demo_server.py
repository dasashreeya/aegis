import asyncio
import threading
import time
import uvicorn
from fastapi import FastAPI
from app.main import app as fastapi_app
from app.dependencies import get_orchestrator
from app.models import DecisionInput
from app.agents.replay import ForkRequest

def start_server():
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8080, log_level="warning")

def seed_data():
    orchestrator = get_orchestrator()

    # 1. Gene Lokken nH Predict Case (Flagged)
    d1 = orchestrator.run(DecisionInput(
        source="Benefits Engine",
        subject="Gene Lokken (Case 2048)",
        requested_service="Post-acute skilled nursing care",
        original_decision="denied",
        policy_id="CMS-SNF-100",
        facts={
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 19,
            "requested_days": 7,
        }
    ))
    print(f"Seeded d1 (nH Predict): {d1.id} -> {d1.status}")

    # 2. Cigna PxDx Bulk Denial Incident (Flagged)
    d2 = orchestrator.run(DecisionInput(
        source="Cigna PxDx Batch",
        subject="Patient #4812",
        requested_service="Diagnostic Mammogram & Ultrasound",
        original_decision="denied",
        policy_id="CMS-SNF-100",
        facts={
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 5,
            "requested_days": 1,
        }
    ))
    print(f"Seeded d2 (Cigna PxDx): {d2.id} -> {d2.status}")

    # 3. Control Case #1: Non-skilled Custodial Care (Upheld - GREEN)
    d3 = orchestrator.run(DecisionInput(
        source="Claims Engine",
        subject="Control Case A (Custodial)",
        requested_service="Long-term Custodial Assistance",
        original_decision="denied",
        policy_id="CMS-SNF-100",
        facts={
            "medically_necessary": True,
            "skilled_care_required": False,  # Non-skilled care -> denial supported!
            "benefit_days_used": 10,
            "requested_days": 30,
        }
    ))
    print(f"Seeded d3 (Control A): {d3.id} -> {d3.status}")

    # 4. Control Case #2: Benefit Period Exhausted (Upheld - GREEN)
    d4 = orchestrator.run(DecisionInput(
        source="Claims Engine",
        subject="Control Case B (Exhausted)",
        requested_service="Skilled Nursing Extension",
        original_decision="denied",
        policy_id="CMS-SNF-100",
        facts={
            "medically_necessary": True,
            "skilled_care_required": True,
            "benefit_days_used": 100,  # Full 100 days exhausted!
            "requested_days": 10,
        }
    ))
    print(f"Seeded d4 (Control B): {d4.id} -> {d4.status}")

    # 5. Fork of Gene Lokken decision (Upheld - GREEN)
    forked = orchestrator.run_fork(d1.id, ForkRequest(original_decision="approved", note="corrected source decision"))
    if forked:
        print(f"Seeded forked (Replayed): {forked.id} -> {forked.status}")

    print("\nClean decision queue seeded successfully!")
    print(f"Total decisions in queue: {len(orchestrator.store.list())}")
    for d in orchestrator.store.list():
        print(f"  [{d.status.upper():<8}] {d.id} | {d.subject} | {d.requested_service}")

if __name__ == "__main__":
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(2)
    print("Server running on http://127.0.0.1:8080")
    seed_data()
    
    while True:
        time.sleep(1)
