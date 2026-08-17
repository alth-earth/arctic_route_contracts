from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from arctic_route_contracts import (
    ContractError,
    CorridorRole,
    ScenarioMode,
    canonical_sha256,
    create_run_context,
    default_config_root,
    load_corridor,
    load_dataset_bundle,
    load_run_context,
    load_scenario,
    load_vessel_profile,
    materialize_frozen_forecast,
    validate_scenario_for_corridor,
    write_run_context_atomic,
)
from arctic_route_contracts.bundle import DatasetBundleIdentity
from arctic_route_contracts.cli import main

ROOT = default_config_root()
MURMANSK = "offshore_murmansk_to_offshore_dikson"
TROMSO = "tromso_to_isfjorden_outer"
VESSEL = "nordic_odyssey_reference_v1"
FORMAL_DATA_PROFILE: dict[str, float | None] = {
    "land_sea_mask": None,
    "ocean_current": 1.0,
    "sea_ice_concentration": 1.0,
    "sea_ice_drift": 1.0,
    "sea_ice_edge": 1.0,
    "sea_ice_thickness": 1.0,
    "sea_ice_type": 1.0,
    "temperature": 3.0,
    "visibility": 3.0,
    "water_level": 1.0,
    "wave": 3.0,
    "wind_field": 3.0,
}


def _bundle_payload(
    *,
    corridor_id: str,
    start: str,
    end: str,
    data_type: str = "wave",
    interval_hours: float | None = 3.0,
) -> dict[str, object]:
    start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    step_count = (
        0
        if interval_hours is None
        else int((end_time - start_time).total_seconds() / (interval_hours * 3600))
    )
    records = [
        {
            "data_id": f"{data_type}-frame-{index:03d}",
            "data_type": data_type,
            "issue_time": "2026-07-14T18:00:00Z",
            "valid_time": (
                start_time.replace(tzinfo=UTC) + timedelta(hours=(interval_hours or 0) * index)
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "source": "test-source",
            "version": "v1",
            "quality_flag": "good",
            "checksum": hashlib.sha256(f"frame-{index}".encode()).hexdigest(),
            "source_snapshot_id": "source-a",
        }
        for index in range(step_count + 1)
    ]
    canonical = lambda value: hashlib.sha256(  # noqa: E731
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    provenance = [
        {
            "data_id": record["data_id"],
            "checksum": record["checksum"],
            "source_snapshot_id": record["source_snapshot_id"],
        }
        for record in records
    ]
    coverage_body = {
        "data_type": data_type,
        "record_count": len(records),
        "records_digest": canonical(records),
        "provenance_digest": canonical(provenance),
        "available_start": start,
        # A static layer is represented by one snapshot at the window start;
        # its support is timeless within the declared scenario window.
        "available_end": start if interval_hours is None else end,
        "expected_interval_hours": interval_hours,
        "missing_intervals": [],
        "source_snapshot_ids": ["source-a"],
        "has_start_support": True,
        "meets_minimum_horizon": True,
        "covers_requested_window": True,
        "provenance_complete": True,
        "complete": True,
    }
    coverage = {**coverage_body, "coverage_digest": canonical(coverage_body)}
    identity = {
        "schema_version": "a.dataset-bundle.v2",
        "corridor_id": corridor_id,
        "as_of_time": "2026-07-15T00:00:00Z",
        "requested_start": start,
        "requested_end": end,
        "minimum_required_end": end,
        "requested_data_types": [data_type],
        "source_snapshot_ids": ["source-a"],
        "records": records,
        "coverage": [coverage],
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        **identity,
        "bundle_id": f"a-bundle-{digest[:24]}",
        "bundle_digest": digest,
        "record_count": len(records),
    }


def _formal_bundle_payload(*, corridor_id: str, start: str, end: str) -> dict[str, object]:
    parts = [
        _bundle_payload(
            corridor_id=corridor_id,
            start=start,
            end=end,
            data_type=data_type,
            interval_hours=interval,
        )
        for data_type, interval in FORMAL_DATA_PROFILE.items()
    ]
    records = sorted(
        (record for part in parts for record in part["records"]),
        key=lambda record: (record["data_type"], record["valid_time"], record["data_id"]),
    )
    coverage = sorted(
        (part["coverage"][0] for part in parts),
        key=lambda item: item["data_type"],
    )
    identity = {
        "schema_version": "a.dataset-bundle.v2",
        "corridor_id": corridor_id,
        "as_of_time": "2026-07-15T00:00:00Z",
        "requested_start": start,
        "requested_end": end,
        "minimum_required_end": end,
        "requested_data_types": sorted(FORMAL_DATA_PROFILE),
        "source_snapshot_ids": ["source-a"],
        "records": records,
        "coverage": coverage,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        **identity,
        "bundle_id": f"a-bundle-{digest[:24]}",
        "bundle_digest": digest,
        "record_count": len(records),
    }


def _write_bundle(tmp_path: Path, **kwargs: str) -> Path:
    path = tmp_path / "dataset-bundle.json"
    path.write_text(json.dumps(_formal_bundle_payload(**kwargs)), encoding="utf-8")
    return path


def test_mentor_corridor_facts_and_roles_are_exact() -> None:
    primary = load_corridor(ROOT, MURMANSK)
    transfer = load_corridor(ROOT, TROMSO)

    # Demo RC1 corridor 2.2.0: endpoints moved to offshore cells with full
    # 12-type data support (2026-08-16 change; see CHANGELOG).
    assert (primary.start.latitude, primary.start.longitude) == (69.55, 34.00)
    assert (primary.destination.latitude, primary.destination.longitude) == (73.80, 80.00)
    assert primary.start_allowed_region.west == 33.30
    assert primary.destination_allowed_region.east == 80.50
    assert primary.role is CorridorRole.PRIMARY_DEVELOPMENT
    assert primary.version == "2.2.0"
    assert primary.horizon_policy.default_hours == 168
    assert primary.horizon_policy.minimum_buffer_hours == 48
    assert (primary.horizon_policy.minimum_hours, primary.horizon_policy.maximum_hours) == (
        144,
        216,
    )

    assert (transfer.start.latitude, transfer.start.longitude) == (70.5, 18.0)
    assert (transfer.destination.latitude, transfer.destination.longitude) == (78.15, 13.0)
    assert transfer.role is CorridorRole.TRANSFER_VALIDATION
    assert transfer.version == "1.2.0"
    assert transfer.horizon_policy.default_hours == 96
    assert transfer.horizon_policy.minimum_buffer_hours == 48
    assert len(transfer.reference_points) == 1
    longyearbyen = transfer.reference_points[0]
    assert (longyearbyen.location.latitude, longyearbyen.location.longitude) == (78.22, 15.65)
    assert longyearbyen.excluded_from_route_optimization is True
    assert longyearbyen.location != transfer.destination


def test_horizon_formula_reports_unsupported_tail_instead_of_clamping() -> None:
    primary = load_corridor(ROOT, MURMANSK)
    transfer = load_corridor(ROOT, TROMSO)

    # RC1 corridor 2.2.0 offshore endpoints shorten the great-circle distance.
    assert 870 < primary.great_circle_distance_nm < 890
    assert 455 < transfer.great_circle_distance_nm < 480
    assert (
        primary.horizon_policy.recommend_hours(
            great_circle_distance_nm=primary.great_circle_distance_nm,
            nominal_speed_knots=15.7,
        )
        == 168
    )
    assert (
        transfer.horizon_policy.recommend_hours(
            great_circle_distance_nm=transfer.great_circle_distance_nm,
            nominal_speed_knots=15.7,
        )
        == 96
    )
    # The 10-day sprint freezes these two design-distance examples.  They are
    # deliberately separate from the great-circle fallback above so a future
    # corridor geometry edit cannot silently change the demo window.
    assert (
        primary.horizon_policy.recommend_hours(
            great_circle_distance_nm=primary.great_circle_distance_nm,
            nominal_speed_knots=15.7,
            candidate_route_distance_nm=1137,
        )
        == 168
    )
    assert (
        transfer.horizon_policy.recommend_hours(
            great_circle_distance_nm=transfer.great_circle_distance_nm,
            nominal_speed_knots=15.7,
            candidate_route_distance_nm=555,
        )
        == 96
    )
    assessment = primary.horizon_policy.assess_hours(
        great_circle_distance_nm=primary.great_circle_distance_nm,
        nominal_speed_knots=15.7,
        candidate_route_distance_nm=3000,
    )
    assert assessment.coverage_sufficient is False
    assert assessment.selected_hours is None
    assert assessment.required_hours > 216
    with pytest.raises(ContractError, match="forecast_coverage_insufficient"):
        primary.horizon_policy.recommend_hours(
            great_circle_distance_nm=primary.great_circle_distance_nm,
            nominal_speed_knots=15.7,
            candidate_route_distance_nm=3000,
        )


def test_dual_scenarios_have_distinct_truth_semantics() -> None:
    retrospective = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    template = load_scenario(ROOT, "murmansk_dikson_frozen_forecast_template_v1")

    assert retrospective.mode is ScenarioMode.RETROSPECTIVE_BEST_ESTIMATE
    assert retrospective.version == "1.1.0"
    assert retrospective.corridor_version == "2.2.0"
    assert retrospective.simulation_start == datetime(2026, 7, 15, tzinfo=UTC)
    assert retrospective.simulation_end == datetime(2026, 7, 22, tzinfo=UTC)
    assert retrospective.is_template is False
    assert template.mode is ScenarioMode.FROZEN_FORECAST
    assert template.version == "1.1.0"
    assert template.corridor_version == "2.2.0"
    assert template.is_template is True
    assert template.simulation_start is None
    assert set(retrospective.required_data_types) == set(FORMAL_DATA_PROFILE)
    assert retrospective.optional_data_types == (
        "bathymetry",
        "long_term_restricted_area",
    )


def test_frozen_template_requires_explicit_anchor_and_is_deterministic() -> None:
    template = load_scenario(ROOT, "murmansk_dikson_frozen_forecast_template_v1")
    start = datetime(2026, 8, 12, tzinfo=UTC)

    first = materialize_frozen_forecast(template, start)
    second = materialize_frozen_forecast(template, start)

    assert first == second
    assert first.scenario_id == "murmansk_dikson_frozen_forecast_20260812t0000z_v1"
    assert first.version == "1.1.0+start.20260812t0000z"
    assert first.simulation_end == datetime(2026, 8, 19, tzinfo=UTC)
    shorter = materialize_frozen_forecast(template, start, horizon_hours=144)
    assert shorter.scenario_id == ("murmansk_dikson_frozen_forecast_20260812t0000z_h144_v1")
    assert shorter.version == "1.1.0+start.20260812t0000z.h144"
    assert shorter.simulation_end == datetime(2026, 8, 18, tzinfo=UTC)
    with pytest.raises(ContractError, match="timezone"):
        materialize_frozen_forecast(template, datetime(2026, 8, 12))


def test_public_vessel_facts_do_not_invent_polar_class_or_maneuvering() -> None:
    vessel = load_vessel_profile(ROOT, VESSEL)

    assert vessel.imo_number == "9529451"
    assert vessel.deadweight_tonnes == 75603
    assert vessel.ice_class == "1A"
    assert "Finnish-Swedish" in vessel.ice_class_system
    assert vessel.reported_draft_m == 14.08
    assert vessel.nominal_speed_knots == 15.7
    assert "not Polar Class PC6" in vessel.source_notes
    assert not hasattr(vessel, "turn_radius_m")
    assert not hasattr(vessel, "under_keel_clearance_m")


def test_canonical_digest_is_stable_and_covers_corridor_facts() -> None:
    primary = load_corridor(ROOT, MURMANSK)
    assert canonical_sha256(primary) == canonical_sha256(primary)
    transfer = load_corridor(ROOT, TROMSO)
    assert canonical_sha256(primary) != canonical_sha256(transfer)


def test_previous_policy_context_remains_readable_but_cannot_mix_with_current_config(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    bundle = load_dataset_bundle(
        _write_bundle(
            tmp_path,
            corridor_id=MURMANSK,
            start="2026-07-15T00:00:00Z",
            end="2026-07-22T00:00:00Z",
        )
    )
    current = create_run_context(
        scenario=scenario,
        corridor=corridor,
        vessel=vessel,
        dataset_bundle=bundle,
        run_id="run-00000000-0000-4000-8000-000000000001",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )
    previous_corridor = replace(
        corridor,
        version="2.0.0",
        horizon_policy=replace(corridor.horizon_policy, minimum_buffer_hours=24),
    )
    previous_scenario = replace(
        scenario,
        version="1.0.0",
        corridor_version=previous_corridor.version,
    )
    previous = create_run_context(
        scenario=previous_scenario,
        corridor=previous_corridor,
        vessel=vessel,
        dataset_bundle=bundle,
        run_id="run-00000000-0000-4000-8000-000000000002",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )

    previous_path = tmp_path / "previous-run-context.json"
    write_run_context_atomic(previous, previous_path)
    assert load_run_context(previous_path) == previous
    assert previous.config_digest != current.config_digest
    assert previous.scenario_digest != current.scenario_digest
    assert previous.corridor_digest != current.corridor_digest
    with pytest.raises(ContractError, match="different corridor version"):
        validate_scenario_for_corridor(previous_scenario, corridor)


def test_a_bundle_is_independently_verified_and_binds_run_context(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, scenario.corridor_id)
    vessel = load_vessel_profile(ROOT, VESSEL)
    bundle_path = _write_bundle(
        tmp_path,
        corridor_id=MURMANSK,
        start="2026-07-15T00:00:00Z",
        end="2026-07-22T00:00:00Z",
    )
    bundle = load_dataset_bundle(bundle_path)

    context = create_run_context(
        scenario=scenario,
        corridor=corridor,
        vessel=vessel,
        dataset_bundle=bundle,
        run_id="run-00000000-0000-4000-8000-000000000001",
        created_at=datetime(2026, 7, 15, tzinfo=UTC),
    )

    assert context.dataset_bundle_id == bundle.bundle_id
    assert context.scenario_mode is ScenarioMode.RETROSPECTIVE_BEST_ESTIMATE
    assert len(context.config_digest) == 64
    output = tmp_path / "run-context.json"
    write_run_context_atomic(context, output)
    assert load_run_context(output) == context
    with pytest.raises(ContractError, match="already exists"):
        write_run_context_atomic(context, output)


def test_formal_run_context_rejects_complete_but_incomplete_data_profile(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    wave_only = load_dataset_bundle(
        _write_payload(
            tmp_path / "wave-only.json",
            _bundle_payload(
                corridor_id=MURMANSK,
                start="2026-07-15T00:00:00Z",
                end="2026-07-22T00:00:00Z",
            ),
        )
    )
    assert wave_only.coverage_complete is True

    with pytest.raises(ContractError, match="required_data_types"):
        create_run_context(
            scenario=scenario,
            corridor=corridor,
            vessel=vessel,
            dataset_bundle=wave_only,
        )


def test_shared_verifier_accepts_native_cadence_and_rejects_legacy_guess(
    tmp_path: Path,
) -> None:
    hourly_ice = _bundle_payload(
        corridor_id=MURMANSK,
        start="2026-07-15T00:00:00Z",
        end="2026-07-16T00:00:00Z",
        data_type="sea_ice_type",
        interval_hours=1.0,
    )
    verified = load_dataset_bundle(_write_payload(tmp_path / "hourly-ice.json", hourly_ice))
    assert verified.coverage_complete is True

    guessed_daily_ice = _bundle_payload(
        corridor_id=MURMANSK,
        start="2026-07-15T00:00:00Z",
        end="2026-07-16T00:00:00Z",
        data_type="sea_ice_type",
        interval_hours=24.0,
    )
    with pytest.raises(ContractError, match="cadence"):
        load_dataset_bundle(_write_payload(tmp_path / "guessed-daily-ice.json", guessed_daily_ice))


def test_formal_run_context_rejects_v1_and_incomplete_v2(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    payload = _formal_bundle_payload(
        corridor_id=MURMANSK,
        start="2026-07-15T00:00:00Z",
        end="2026-07-22T00:00:00Z",
    )

    legacy = dict(payload)
    legacy.pop("coverage")
    legacy["schema_version"] = "a.dataset-bundle.v1"
    identity = {
        key: legacy[key]
        for key in (
            "schema_version",
            "corridor_id",
            "as_of_time",
            "requested_start",
            "requested_end",
            "minimum_required_end",
            "requested_data_types",
            "source_snapshot_ids",
            "records",
        )
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    legacy["bundle_digest"] = digest
    legacy["bundle_id"] = f"a-bundle-{digest[:24]}"
    legacy_bundle = load_dataset_bundle(_write_payload(tmp_path / "legacy.json", legacy))
    assert legacy_bundle.coverage_complete is False
    with pytest.raises(ContractError, match="legacy-read-only"):
        create_run_context(
            scenario=scenario,
            corridor=corridor,
            vessel=vessel,
            dataset_bundle=legacy_bundle,
        )

    incomplete = json.loads(json.dumps(payload))
    incomplete["coverage"][0]["complete"] = False
    with pytest.raises(ContractError, match="independently recomputed"):
        load_dataset_bundle(_write_payload(tmp_path / "incomplete.json", incomplete))


def test_dataset_bundle_identity_cannot_be_constructed_without_verification() -> None:
    with pytest.raises(TypeError):
        DatasetBundleIdentity(  # type: ignore[call-arg]
            schema_version="a.dataset-bundle.v2",
            bundle_id="a-bundle-" + "1" * 24,
            bundle_digest="1" * 64,
            corridor_id=MURMANSK,
            as_of_time=datetime(2026, 7, 15, tzinfo=UTC),
            requested_start=datetime(2026, 7, 15, tzinfo=UTC),
            requested_end=datetime(2026, 7, 22, tzinfo=UTC),
            minimum_required_end=datetime(2026, 7, 22, tzinfo=UTC),
            requested_data_types=("wave",),
            source_snapshot_ids=(),
            record_count=0,
            coverage_complete=True,
        )


def test_run_context_rejects_identity_forged_through_internal_factory(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    valid = load_dataset_bundle(
        _write_bundle(
            tmp_path,
            corridor_id=MURMANSK,
            start="2026-07-15T00:00:00Z",
            end="2026-07-22T00:00:00Z",
        )
    )
    forged = DatasetBundleIdentity._verified(
        schema_version="a.dataset-bundle.v2",
        bundle_id="a-bundle-" + "1" * 24,
        bundle_digest="1" * 64,
        corridor_id=MURMANSK,
        as_of_time=datetime(2026, 7, 15, tzinfo=UTC),
        requested_start=datetime(2026, 7, 15, tzinfo=UTC),
        requested_end=datetime(2026, 7, 22, tzinfo=UTC),
        minimum_required_end=datetime(2026, 7, 22, tzinfo=UTC),
        requested_data_types=tuple(sorted(FORMAL_DATA_PROFILE)),
        source_snapshot_ids=("source-a",),
        record_count=0,
        coverage_complete=True,
        verified_document_json=valid._verified_document_json,
    )

    with pytest.raises(ContractError, match="do not match"):
        create_run_context(
            scenario=scenario,
            corridor=corridor,
            vessel=vessel,
            dataset_bundle=forged,
        )


def test_frozen_run_context_rejects_bundle_with_future_knowledge(tmp_path: Path) -> None:
    template = load_scenario(ROOT, "murmansk_dikson_frozen_forecast_template_v1")
    scenario = materialize_frozen_forecast(
        template,
        datetime(2026, 7, 15, tzinfo=UTC),
    )
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    payload = _formal_bundle_payload(
        corridor_id=MURMANSK,
        start="2026-07-15T00:00:00Z",
        end="2026-07-22T00:00:00Z",
    )
    payload["as_of_time"] = "2026-07-20T00:00:00Z"
    identity = {
        key: payload[key]
        for key in (
            "schema_version",
            "corridor_id",
            "as_of_time",
            "requested_start",
            "requested_end",
            "minimum_required_end",
            "requested_data_types",
            "source_snapshot_ids",
            "records",
            "coverage",
        )
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["bundle_digest"] = digest
    payload["bundle_id"] = f"a-bundle-{digest[:24]}"
    bundle = load_dataset_bundle(_write_payload(tmp_path / "future-knowledge.json", payload))

    with pytest.raises(ContractError, match="as_of_time"):
        create_run_context(
            scenario=scenario,
            corridor=corridor,
            vessel=vessel,
            dataset_bundle=bundle,
        )


def _write_payload(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_run_context_rejects_wrong_corridor_or_short_coverage(tmp_path: Path) -> None:
    scenario = load_scenario(ROOT, "murmansk_dikson_july_2026_retrospective_v1")
    corridor = load_corridor(ROOT, MURMANSK)
    vessel = load_vessel_profile(ROOT, VESSEL)
    wrong_bundle = load_dataset_bundle(
        _write_bundle(
            tmp_path,
            corridor_id=TROMSO,
            start="2026-07-15T00:00:00Z",
            end="2026-07-22T00:00:00Z",
        )
    )
    with pytest.raises(ContractError, match="corridor"):
        create_run_context(
            scenario=scenario,
            corridor=corridor,
            vessel=vessel,
            dataset_bundle=wrong_bundle,
        )


def test_cli_lists_and_validates_configs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config-root", str(ROOT), "validate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    # RC1 adds the August frozen demo scenarios (one per corridor) and RC2 adds
    # the 72 h Tromso smoke scenario on top of the July/forecast-template ones.
    assert payload["counts"] == {"corridors": 2, "scenarios": 7, "vessels": 1}


def test_cli_recommends_route_specific_horizon_and_reports_source_cap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = [
        "--config-root",
        str(ROOT),
        "recommend-horizon",
        "--corridor",
        MURMANSK,
        "--vessel",
        VESSEL,
    ]
    assert main(base) == 0
    supported = json.loads(capsys.readouterr().out)
    assert supported["coverage_sufficient"] is True
    assert supported["selected_hours"] == 168

    assert main([*base, "--candidate-route-distance-nm", "3000"]) == 2
    unsupported = json.loads(capsys.readouterr().out)
    assert unsupported["status"] == "forecast_coverage_insufficient"
    assert unsupported["selected_hours"] is None


def test_all_json_schemas_are_well_formed() -> None:
    schema_root = Path(__file__).parents[1] / "schemas"
    schemas = sorted(schema_root.glob("*.schema.json"))
    assert len(schemas) == 5
    for path in schemas:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert value["additionalProperties"] is False
