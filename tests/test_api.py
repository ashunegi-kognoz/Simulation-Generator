"""End-to-end API test against an offline SQLite database with the mock provider.

Exercises the whole Part 3 surface in one flow (kept as a single async test so the
async engine stays bound to one event loop):

  create (+ idempotent re-create)  ->  run job to completion  ->  create session
  ->  fetch posture-stripped decisions  ->  submit letter allocations
  ->  verify letter->posture resolution in storage  ->  fingerprint + debrief
  ->  tenant isolation

No network and no API key: LLM_PROVIDER=mock.
"""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

# --- point the whole stack at a temporary SQLite database BEFORE the engine exists ---
_DB_FILE = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_DB_FILE.close()
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["MOCK_FORCE_REBALANCE"] = "0"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.name}"

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import (  # noqa: E402
    Base,
    dispose_engine,
    get_engine,
    get_sessionmaker,
    reset_engine_for_tests,
)
from app.llm.call import reset_semaphore_for_tests  # noqa: E402
from app.models import AllocationRecord, DecisionRecord, Session, Tenant  # noqa: E402
from app.services import session_service  # noqa: E402

# import app.models side effects already registered the tables via app.db.Base

DISPLAY_SEED = 12345


def _sim_input(tenant_id: str) -> dict:
    return {
        "simulation_name": "Offline Flow",
        "company_name": "Apex Horizon Group",
        "business_context": "regional logistics under margin pressure " * 3,
        "subject_matter": "supply chain resilience",
        "participant_count": 2,
        "tenant_id": tenant_id,
        "rounds": [
            {
                "index": 1,
                "round_type": "individual",
                "decision_count": 2,
                "dimensions": ["MOVE", "HOLD"],
            }
        ],
        "role_overview": [
            {
                "role_title": "Regional Director",
                "function": "Operations",
                "entity": "AHG Logistics",
                "reporting_line": "COO",
                "scope": "South region",
                "seniority_band": "exec",
            }
        ],
        "kpi_critical_tradeoff": [
            {"metric": "OTIF", "target": "95%", "competing_pressure": "freight cost"}
        ],
    }


@pytest.mark.asyncio
async def test_full_offline_flow() -> None:
    # Fresh engine bound to this loop + clean schema.
    get_settings.cache_clear()
    reset_engine_for_tests()
    reset_semaphore_for_tests()

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = get_sessionmaker()
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    async with sessionmaker() as s:
        s.add(Tenant(id=tenant_a, name="Tenant A"))
        s.add(Tenant(id=tenant_b, name="Tenant B"))
        await s.commit()

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    headers_a = {"X-Tenant-Id": str(tenant_a)}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1) create (idempotent key)
        body = _sim_input(str(tenant_a))
        r = await client.post(
            "/simulations", json=body, headers={**headers_a, "Idempotency-Key": "key-1"}
        )
        assert r.status_code == 202, r.text
        sim_id = r.json()["simulation_id"]

        # 2) idempotent re-create -> same simulation
        r2 = await client.post(
            "/simulations", json=body, headers={**headers_a, "Idempotency-Key": "key-1"}
        )
        assert r2.status_code == 202
        assert r2.json()["simulation_id"] == sim_id

        # 3) run the queued job to completion
        r = await client.post(f"/simulations/{sim_id}/run", headers=headers_a)
        assert r.status_code == 200, r.text
        status = r.json()
        assert status["jobs_handled"] == 1
        assert status["status"] == "ready", status

        # 4) create a participant session with a pinned shuffle seed
        r = await client.post(
            "/sessions",
            json={"simulation_id": sim_id, "participant_ref": "p1", "display_seed": DISPLAY_SEED},
            headers=headers_a,
        )
        assert r.status_code == 201, r.text
        session_id = r.json()["session_id"]

        # 5) fetch decisions -> must be posture-stripped (letters only, neutral labels)
        r = await client.get(f"/sessions/{session_id}", headers=headers_a)
        assert r.status_code == 200, r.text
        decisions = r.json()["decisions"]
        assert len(decisions) == 2
        for d in decisions:
            letters = [o["letter"] for o in d["options"]]
            assert letters == ["A", "B", "C", "D"]
            for o in d["options"]:
                assert "posture" not in o  # no leak
                assert o["label"] == f"Option {o['letter']}"  # neutral label, not "Protect option"
                assert o["content"]

        # 6) compute expected letter->posture maps from storage, submit letters, verify resolution
        async with sessionmaker() as s:
            recs = (
                await s.execute(
                    select(DecisionRecord)
                    .where(
                        DecisionRecord.owner_id == "p1",
                        DecisionRecord.owner_type == "participant",
                    )
                    .order_by(DecisionRecord.decision_number)
                )
            ).scalars().all()
            assert len(recs) == 2
            expected: dict[int, dict[str, int]] = {}
            for rec in recs:
                _, position_map = session_service.shuffle_options(
                    rec.decision_jsonb["options"], DISPLAY_SEED, rec.decision_number
                )
                letter_units = {"A": 40, "B": 30, "C": 20, "D": 10}
                expected[rec.decision_number] = {
                    position_map[letter]: units for letter, units in letter_units.items()
                }

        payload = {
            "allocations": [
                {"decision_number": n, "units": {"A": 40, "B": 30, "C": 20, "D": 10}}
                for n in expected
            ]
        }
        r = await client.post(
            f"/sessions/{session_id}/allocations", json=payload, headers=headers_a
        )
        assert r.status_code == 200, r.text
        assert r.json()["submitted"] == 2

        async with sessionmaker() as s:
            stored = (
                await s.execute(
                    select(AllocationRecord).where(
                        AllocationRecord.session_id == uuid.UUID(session_id)
                    )
                )
            ).scalars().all()
            by_decision = {a.decision_number: a.units_jsonb for a in stored}
            assert by_decision == expected  # letters resolved to the correct postures
            for units in by_decision.values():
                assert sum(units.values()) == 100
                assert set(units) == {"Protect", "Enable", "Hybrid", "Defer"}

        # 7) debrief -> fingerprint persisted + grounded debrief
        r = await client.get(f"/sessions/{session_id}/debrief", headers=headers_a)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["fingerprint"]["n_decisions"] == 2
        cited = payload["debrief"]["cited_decisions"]
        assert cited and set(cited).issubset({1, 2})

        async with sessionmaker() as s:
            sess_row = (
                await s.execute(select(Session).where(Session.id == uuid.UUID(session_id)))
            ).scalars().one()
            assert sess_row.display_seed == DISPLAY_SEED

        # 8) tenant isolation: tenant B cannot see tenant A's simulation
        r = await client.get(f"/simulations/{sim_id}", headers={"X-Tenant-Id": str(tenant_b)})
        assert r.status_code == 404

        # missing tenant header -> 422 (required header)
        r = await client.get(f"/simulations/{sim_id}")
        assert r.status_code == 422

    await dispose_engine()
