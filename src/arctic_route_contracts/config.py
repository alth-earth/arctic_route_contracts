"""TOML loading for versioned shared facts."""

from __future__ import annotations

import re
import tomllib
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import ContractError
from .models import (
    CalibrationStatus,
    CorridorDefinition,
    CorridorRole,
    GeoBoundingBox,
    GeoPoint,
    HorizonPolicy,
    ReferencePoint,
    ScenarioDefinition,
    ScenarioMode,
    VesselProfile,
    validate_identifier,
    validate_version,
)
from .timeutils import ensure_utc

_SAFE_CONFIG_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")


def default_config_root() -> Path:
    """Return configs from a source checkout or an installed wheel."""

    source_root = Path(__file__).resolve().parents[2] / "configs"
    if source_root.is_dir():
        return source_root
    packaged_root = Path(__file__).resolve().parent / "configs"
    if packaged_root.is_dir():
        return packaged_root
    raise ContractError("shared config root cannot be located; pass --config-root")


def list_config_ids(config_root: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    root = Path(config_root) if config_root is not None else default_config_root()
    result: dict[str, tuple[str, ...]] = {}
    for section in ("corridors", "scenarios", "vessels"):
        directory = root / section
        result[section] = tuple(
            sorted(
                path.stem
                for path in directory.glob("*.toml")
                if _SAFE_CONFIG_ID.fullmatch(path.stem)
            )
        )
    return result


def load_corridor(
    config_root: str | Path | None,
    corridor_id: str,
) -> CorridorDefinition:
    root = Path(config_root) if config_root is not None else default_config_root()
    value = _load_named_toml(root, "corridors", corridor_id)
    try:
        start = GeoPoint(**value.pop("start"))
        destination = GeoPoint(**value.pop("destination"))
        start_allowed = GeoBoundingBox(**value.pop("start_allowed_region"))
        destination_allowed = GeoBoundingBox(**value.pop("destination_allowed_region"))
        data_bbox = GeoBoundingBox(**value.pop("data_bbox"))
        horizon = HorizonPolicy(**value.pop("horizon_policy"))
        reference_values = value.pop("reference_points", [])
        references = tuple(
            ReferencePoint(
                **{
                    **item,
                    "location": GeoPoint(**item["location"]),
                }
            )
            for item in reference_values
        )
        value["role"] = CorridorRole(value["role"])
        corridor = CorridorDefinition(
            **value,
            start=start,
            destination=destination,
            start_allowed_region=start_allowed,
            destination_allowed_region=destination_allowed,
            data_bbox=data_bbox,
            horizon_policy=horizon,
            reference_points=references,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid corridor config {corridor_id}: {exc}") from exc
    if corridor.corridor_id != corridor_id:
        raise ContractError(f"corridor file name does not match corridor_id: {corridor_id}")
    return corridor


def load_scenario(
    config_root: str | Path | None,
    scenario_id: str,
) -> ScenarioDefinition:
    root = Path(config_root) if config_root is not None else default_config_root()
    value = _load_named_toml(root, "scenarios", scenario_id)
    try:
        value["mode"] = ScenarioMode(value["mode"])
        value.setdefault("simulation_start", None)
        value.setdefault("simulation_end", None)
        value.setdefault("forecast_anchor_policy", None)
        value.setdefault("is_template", False)
        value["required_data_types"] = tuple(value["required_data_types"])
        value["optional_data_types"] = tuple(value.get("optional_data_types", ()))
        scenario = ScenarioDefinition(**value)
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid scenario config {scenario_id}: {exc}") from exc
    if scenario.scenario_id != scenario_id:
        raise ContractError(f"scenario file name does not match scenario_id: {scenario_id}")
    corridor = load_corridor(root, scenario.corridor_id)
    validate_scenario_for_corridor(scenario, corridor)
    return scenario


def load_vessel_profile(
    config_root: str | Path | None,
    vessel_profile_id: str,
) -> VesselProfile:
    root = Path(config_root) if config_root is not None else default_config_root()
    value = _load_named_toml(root, "vessels", vessel_profile_id)
    try:
        value["calibration_status"] = CalibrationStatus(value["calibration_status"])
        value["source_urls"] = tuple(value["source_urls"])
        vessel = VesselProfile(**value)
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid vessel config {vessel_profile_id}: {exc}") from exc
    if vessel.vessel_profile_id != vessel_profile_id:
        raise ContractError(
            f"vessel file name does not match vessel_profile_id: {vessel_profile_id}"
        )
    return vessel


def validate_scenario_for_corridor(
    scenario: ScenarioDefinition,
    corridor: CorridorDefinition,
) -> None:
    if scenario.corridor_id != corridor.corridor_id:
        raise ContractError("scenario and corridor IDs do not match")
    if scenario.corridor_version != corridor.version:
        raise ContractError("scenario pins a different corridor version")
    policy = corridor.horizon_policy
    if not policy.minimum_hours <= scenario.horizon_hours <= policy.maximum_hours:
        raise ContractError("scenario horizon is outside corridor policy bounds")
    if scenario.horizon_hours % policy.rounding_hours:
        raise ContractError("scenario horizon is not aligned with corridor rounding_hours")


def validate_scenario_for_vessel(
    scenario: ScenarioDefinition,
    vessel: VesselProfile,
) -> None:
    if scenario.default_vessel_profile_id != vessel.vessel_profile_id:
        raise ContractError("scenario and vessel profile IDs do not match")
    if scenario.default_vessel_profile_version != vessel.version:
        raise ContractError("scenario pins a different vessel profile version")


def materialize_frozen_forecast(
    template: ScenarioDefinition,
    simulation_start: datetime,
    *,
    horizon_hours: int | None = None,
    scenario_id: str | None = None,
    version: str | None = None,
) -> ScenarioDefinition:
    """Create a deterministic concrete scenario from an explicit UTC anchor."""

    if not template.is_template or template.mode is not ScenarioMode.FROZEN_FORECAST:
        raise ContractError("materialize_frozen_forecast requires a frozen template")
    start = ensure_utc(simulation_start, field="simulation_start")
    selected_horizon = template.horizon_hours if horizon_hours is None else horizon_hours
    if (
        not isinstance(selected_horizon, int)
        or isinstance(selected_horizon, bool)
        or selected_horizon <= 0
    ):
        raise ContractError("horizon_hours must be a positive integer")
    token = start.strftime("%Y%m%dt%H%Mz").lower()
    base = template.scenario_id.removesuffix("_template_v1")
    horizon_token = "" if selected_horizon == template.horizon_hours else f"_h{selected_horizon}"
    version_horizon_token = (
        "" if selected_horizon == template.horizon_hours else f".h{selected_horizon}"
    )
    concrete_id = scenario_id or f"{base}_{token}{horizon_token}_v1"
    concrete_version = version or (f"{template.version}+start.{token}{version_horizon_token}")
    validate_identifier(concrete_id, field="scenario_id")
    validate_version(concrete_version, field="scenario.version")
    return replace(
        template,
        scenario_id=concrete_id,
        version=concrete_version,
        display_name=(
            f"{template.display_name.removesuffix(' template')} @ {token} ({selected_horizon} h)"
        ),
        simulation_start=start,
        simulation_end=start + timedelta(hours=selected_horizon),
        horizon_hours=selected_horizon,
        is_template=False,
    )


def _load_named_toml(root: Path, section: str, config_id: str) -> dict[str, Any]:
    if not isinstance(config_id, str) or _SAFE_CONFIG_ID.fullmatch(config_id) is None:
        raise ContractError(f"unsafe config ID: {config_id!r}")
    path = root / section / f"{config_id}.toml"
    try:
        with path.open("rb") as handle:
            return dict(tomllib.load(handle))
    except FileNotFoundError as exc:
        raise ContractError(f"config file does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ContractError(f"config file is not valid TOML: {path}: {exc}") from exc
