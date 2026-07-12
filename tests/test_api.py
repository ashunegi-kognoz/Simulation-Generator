"""End-to-end API test against an offline SQLite database with the mock provider.

Exercises the whole Part 3 surface in one flow (kept as a single async test so the
async engine stays bound to one event loop):

  create (+ idempotent re-create)  ->  run job to completion  ->  create session
  ->  fetch posture-stripped decisions  ->  submit letter allocations
  ->  verify letter->posture resolution in storage  ->  fingerprint + reflection
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


def _sim_input(tenant_id: str, engine_version: int = 1) -> dict:
    # engine_version pinned to 1 by default here: test_full_offline_flow is the
    # permanent guarantee for the legacy fixed-posture engine. The v2 (default)
    # engine has its own flow test below.
    return {
        "engine_version": engine_version,
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

        # 7) reflection board -> fingerprint math + stance lexicon; debrief retired
        r = await client.get(f"/sessions/{session_id}/reflection", headers=headers_a)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["orientation"]["n_decisions"] == 2
        assert len(payload["stances"]) == 4
        overall = payload["orientation"]["overall"]
        assert abs(sum(v["share"] for v in overall.values()) - 1.0) < 0.05
        assert payload["orientation"]["dominant"]["key"] in overall
        # v1 sim: no framework yet; weights not curated -> pending, no invented scores
        assert payload["weights_pending"] is True and payload["outcome_scores"] is None
        r = await client.get(f"/sessions/{session_id}/debrief", headers=headers_a)
        assert r.status_code == 410

        async with sessionmaker() as s:
            sess_row = (
                await s.execute(select(Session).where(Session.id == uuid.UUID(session_id)))
            ).scalars().one()
            assert sess_row.display_seed == DISPLAY_SEED

        # 8) tenant isolation: tenant B cannot see tenant A's simulation
        r = await client.get(f"/simulations/{sim_id}", headers={"X-Tenant-Id": str(tenant_b)})
        assert r.status_code == 404

        # no auth (no bearer, no tenant header) -> 401
        r = await client.get(f"/simulations/{sim_id}")
        assert r.status_code == 401

    await dispose_engine()


@pytest.mark.asyncio
async def test_full_offline_flow_v2_default() -> None:
    """The DEFAULT engine is v2: create with no engine_version, and the whole flow
    (generate -> session -> allocate -> reflection) runs on dynamic stances."""
    get_settings.cache_clear()
    reset_engine_for_tests()
    reset_semaphore_for_tests()

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = get_sessionmaker()
    tenant = uuid.uuid4()
    async with sessionmaker() as s:
        s.add(Tenant(id=tenant, name="Tenant V2"))
        await s.commit()

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    headers = {"X-Tenant-Id": str(tenant)}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = _sim_input(str(tenant))
        body.pop("engine_version")  # exercise the DEFAULT (must be v2)
        for rnd in body["rounds"]:
            rnd.pop("dimensions", None)  # focuses must be DERIVED, not authored
        r = await client.post("/simulations", json=body, headers=headers)
        assert r.status_code == 202, r.text
        sim_id = r.json()["simulation_id"]

        r = await client.post(f"/simulations/{sim_id}/run", headers=headers)
        assert r.status_code == 200, r.text

        # generated content: reflection spec + type-set present; boards use its keys;
        # vestigial posture_scheme is dropped on v2
        r = await client.get(f"/simulations/{sim_id}/content", headers=headers)
        assert r.status_code == 200, r.text
        sim_data = r.json()["sim_data"]
        common = sim_data["common_data"]
        assert common["reflection_spec"] is not None
        assert common["type_set"] is not None
        assert common.get("posture_scheme") is None
        keys = {st["key"] for st in common["type_set"]["stances"]}
        assert len(keys) == 4
        boards = sim_data["rounds"]["round_1"]["participants"]
        focus_tags = {
            d["dimension"]
            for pc in boards.values()
            for d in pc["decision_board"]
        }
        assert focus_tags and not focus_tags <= {"MOVE", "HOLD", "FRAME"}  # derived focuses
        for pc in boards.values():
            for d in pc["decision_board"]:
                assert {o["posture"] for o in d["options"]} == keys
                for o in d["options"]:
                    assert o.get("impact_weights") is None  # SME placeholder untouched

        # session -> allocate by letters -> reflection on dynamic stances
        r = await client.post(
            "/sessions",
            json={"simulation_id": sim_id, "participant_ref": "p1", "round_index": 1},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        session_id = r.json()["session_id"]
        rendered = (await client.get(f"/sessions/{session_id}", headers=headers)).json()
        payload = {
            "allocations": [
                {
                    "decision_number": d["decision_number"],
                    "units": {o["letter"]: u for o, u in zip(d["options"], (40, 30, 20, 10))},
                }
                for d in rendered["decisions"]
            ]
        }
        r = await client.post(
            f"/sessions/{session_id}/allocations", json=payload, headers=headers
        )
        assert r.status_code == 200, r.text

        r = await client.get(f"/sessions/{session_id}/reflection", headers=headers)
        assert r.status_code == 200, r.text
        refl = r.json()
        assert refl["framework"] is not None
        assert {s2["key"] for s2 in refl["stances"]} == keys
        assert set(refl["orientation"]["overall"]) == keys
        assert refl["orientation"]["dominant"]["key"] in keys
        assert refl["weights_pending"] is True and refl["outcome_scores"] is None

    await dispose_engine()
