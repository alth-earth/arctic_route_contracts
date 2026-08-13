"""RunContext creation, verification, and immutable publication."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .bundle import DatasetBundleIdentity, reverify_dataset_bundle_identity
from .config import validate_scenario_for_corridor, validate_scenario_for_vessel
from .digest import canonical_sha256, canonical_value, configuration_digest
from .errors import ContractError
from .models import CorridorDefinition, RunContext, ScenarioDefinition, ScenarioMode, VesselProfile
from .timeutils import parse_utc


def create_run_context(
    *,
    scenario: ScenarioDefinition,
    corridor: CorridorDefinition,
    vessel: VesselProfile,
    dataset_bundle: DatasetBundleIdentity,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> RunContext:
    if scenario.is_template or scenario.simulation_start is None or scenario.simulation_end is None:
        raise ContractError("a template cannot be used to create a RunContext")
    if not isinstance(dataset_bundle, DatasetBundleIdentity):
        raise ContractError("dataset_bundle must come from load/verify_dataset_bundle")
    dataset_bundle = reverify_dataset_bundle_identity(dataset_bundle)
    if dataset_bundle.schema_version != "a.dataset-bundle.v2":
        raise ContractError(
            "formal RunContext requires a.dataset-bundle.v2; v1 is legacy-read-only"
        )
    if not dataset_bundle.coverage_complete:
        raise ContractError(
            "formal RunContext requires complete coverage and provenance for every requested type"
        )
    validate_scenario_for_corridor(scenario, corridor)
    validate_scenario_for_vessel(scenario, vessel)
    if dataset_bundle.corridor_id != corridor.corridor_id:
        raise ContractError("DatasetBundle corridor does not match the scenario corridor")
    missing_required_types = sorted(
        set(scenario.required_data_types) - set(dataset_bundle.requested_data_types)
    )
    unexpected_types = sorted(
        set(dataset_bundle.requested_data_types)
        - set(scenario.required_data_types)
        - set(scenario.optional_data_types)
    )
    if missing_required_types:
        raise ContractError(
            "DatasetBundle is missing scenario required_data_types: "
            + ", ".join(missing_required_types)
        )
    if unexpected_types:
        raise ContractError(
            "DatasetBundle contains types outside the scenario data profile: "
            + ", ".join(unexpected_types)
        )
    if dataset_bundle.requested_start != scenario.simulation_start:
        raise ContractError("DatasetBundle requested_start must equal scenario simulation_start")
    if dataset_bundle.requested_end < scenario.simulation_end:
        raise ContractError("DatasetBundle requested_end does not cover scenario simulation_end")
    if dataset_bundle.minimum_required_end < scenario.simulation_end:
        raise ContractError("DatasetBundle minimum_required_end does not cover the scenario")
    if (
        scenario.mode is ScenarioMode.FROZEN_FORECAST
        and dataset_bundle.as_of_time > scenario.simulation_start
    ):
        raise ContractError(
            "frozen_forecast DatasetBundle as_of_time cannot be later than simulation_start"
        )
    scenario_digest = canonical_sha256(scenario)
    corridor_digest = canonical_sha256(corridor)
    vessel_digest = canonical_sha256(vessel)
    public_digest = configuration_digest(
        scenario,
        corridor,
        vessel,
        dataset_bundle_id=dataset_bundle.bundle_id,
        dataset_bundle_digest=dataset_bundle.bundle_digest,
    )
    return RunContext(
        schema_version="run-context.v2",
        run_id=run_id or f"run-{uuid4()}",
        created_at=created_at or datetime.now(UTC),
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.version,
        scenario_mode=scenario.mode,
        simulation_start=scenario.simulation_start,
        simulation_end=scenario.simulation_end,
        scenario_digest=scenario_digest,
        corridor_id=corridor.corridor_id,
        corridor_version=corridor.version,
        corridor_digest=corridor_digest,
        vessel_profile_id=vessel.vessel_profile_id,
        vessel_profile_version=vessel.version,
        vessel_profile_digest=vessel_digest,
        dataset_bundle_id=dataset_bundle.bundle_id,
        dataset_bundle_digest=dataset_bundle.bundle_digest,
        config_digest=public_digest,
    )


def run_context_to_dict(context: RunContext) -> dict[str, Any]:
    return canonical_value(context)


def run_context_from_dict(value: Mapping[str, Any]) -> RunContext:
    if not isinstance(value, Mapping):
        raise ContractError("RunContext must be an object")
    expected = {field.name for field in fields(RunContext)}
    if set(value) != expected:
        raise ContractError("RunContext fields must exactly match run-context.v2")
    try:
        converted = dict(value)
        converted["scenario_mode"] = ScenarioMode(converted["scenario_mode"])
        for field in ("created_at", "simulation_start", "simulation_end"):
            converted[field] = parse_utc(converted[field], field=field)
        return RunContext(**converted)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid RunContext: {exc}") from exc


def load_run_context(path: str | Path) -> RunContext:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"RunContext file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"RunContext is not valid JSON: {path}: {exc}") from exc
    return run_context_from_dict(value)


def write_run_context_atomic(context: RunContext, path: str | Path) -> Path:
    """Atomically create, but never replace, an immutable RunContext JSON file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            run_context_to_dict(context),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, target)
        except FileExistsError as exc:
            raise ContractError(f"immutable RunContext already exists: {target}") from exc
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return target
