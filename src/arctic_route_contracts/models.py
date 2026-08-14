"""Immutable shared facts used by work packages A, B, C, and D."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from .errors import ContractError
from .timeutils import ensure_utc

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:\+[A-Za-z0-9.-]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CorridorRole(StrEnum):
    PRIMARY_DEVELOPMENT = "primary_development"
    TRANSFER_VALIDATION = "transfer_validation"


class ScenarioMode(StrEnum):
    RETROSPECTIVE_BEST_ESTIMATE = "retrospective_best_estimate"
    FROZEN_FORECAST = "frozen_forecast"


class CalibrationStatus(StrEnum):
    PUBLIC_REFERENCE_UNVALIDATED = "public_reference_unvalidated"
    CALIBRATED = "calibrated"


def validate_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ContractError(f"{field} must match {_SAFE_ID.pattern}")


def validate_version(value: str, *, field: str) -> None:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise ContractError(f"{field} must be a semantic version")


def validate_digest(value: str, *, field: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"{field} must be a lowercase SHA-256 digest")


def _positive(value: float, *, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ContractError(f"{field} must be numeric")
    if not math.isfinite(value) or value <= 0:
        raise ContractError(f"{field} must be positive and finite")


@dataclass(frozen=True, slots=True)
class GeoPoint:
    longitude: float
    latitude: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ContractError("longitude must be finite and within [-180, 180]")
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ContractError("latitude must be finite and within [-90, 90]")


@dataclass(frozen=True, slots=True)
class GeoBoundingBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        values = (self.west, self.south, self.east, self.north)
        if any(not math.isfinite(value) for value in values):
            raise ContractError("bounding-box values must be finite")
        if not -180 <= self.west < self.east <= 180:
            raise ContractError("bounding box must satisfy -180 <= west < east <= 180")
        if not -90 <= self.south < self.north <= 90:
            raise ContractError("bounding box must satisfy -90 <= south < north <= 90")

    def contains(self, point: GeoPoint) -> bool:
        return (
            self.west <= point.longitude <= self.east and self.south <= point.latitude <= self.north
        )

    def contains_box(self, other: GeoBoundingBox) -> bool:
        return (
            self.west <= other.west <= other.east <= self.east
            and self.south <= other.south <= other.north <= self.north
        )


@dataclass(frozen=True, slots=True)
class ReferencePoint:
    reference_id: str
    display_name: str
    location: GeoPoint
    purpose: str
    excluded_from_route_optimization: bool

    def __post_init__(self) -> None:
        validate_identifier(self.reference_id, field="reference_id")
        if not self.display_name.strip() or not self.purpose.strip():
            raise ContractError("reference-point display_name and purpose cannot be empty")


@dataclass(frozen=True, slots=True)
class HorizonAssessment:
    required_hours: int
    selected_hours: int | None
    coverage_sufficient: bool
    maximum_hours: int


@dataclass(frozen=True, slots=True)
class HorizonPolicy:
    default_hours: int
    minimum_hours: int
    maximum_hours: int
    corridor_detour_factor: float
    conservative_environment_speed_factor: float
    minimum_buffer_hours: int = 48
    proportional_buffer: float = 0.20
    rounding_hours: int = 24

    def __post_init__(self) -> None:
        integer_fields = (
            self.default_hours,
            self.minimum_hours,
            self.maximum_hours,
            self.minimum_buffer_hours,
            self.rounding_hours,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in integer_fields
        ):
            raise ContractError("horizon and buffer hours must be positive integers")
        if not self.minimum_hours <= self.default_hours <= self.maximum_hours:
            raise ContractError("horizon must satisfy minimum <= default <= maximum")
        if self.minimum_hours % self.rounding_hours or self.maximum_hours % self.rounding_hours:
            raise ContractError("horizon bounds must be multiples of rounding_hours")
        _positive(self.corridor_detour_factor, field="corridor_detour_factor")
        if self.corridor_detour_factor < 1:
            raise ContractError("corridor_detour_factor cannot be below 1")
        _positive(
            self.conservative_environment_speed_factor,
            field="conservative_environment_speed_factor",
        )
        if self.conservative_environment_speed_factor > 1:
            raise ContractError("conservative_environment_speed_factor cannot exceed 1")
        if not math.isfinite(self.proportional_buffer) or self.proportional_buffer < 0:
            raise ContractError("proportional_buffer must be finite and non-negative")

    def recommend_hours(
        self,
        *,
        great_circle_distance_nm: float,
        nominal_speed_knots: float,
        candidate_route_distance_nm: float | None = None,
    ) -> int:
        """Return a supported dynamic horizon; fail instead of hiding a source-cap gap."""

        assessment = self.assess_hours(
            great_circle_distance_nm=great_circle_distance_nm,
            nominal_speed_knots=nominal_speed_knots,
            candidate_route_distance_nm=candidate_route_distance_nm,
        )
        if not assessment.coverage_sufficient or assessment.selected_hours is None:
            raise ContractError(
                "forecast_coverage_insufficient: required horizon "
                f"{assessment.required_hours}h exceeds {assessment.maximum_hours}h"
            )
        return assessment.selected_hours

    def assess_hours(
        self,
        *,
        great_circle_distance_nm: float,
        nominal_speed_knots: float,
        candidate_route_distance_nm: float | None = None,
    ) -> HorizonAssessment:
        """Expose both the raw requirement and whether formal coverage can satisfy it."""

        _positive(great_circle_distance_nm, field="great_circle_distance_nm")
        _positive(nominal_speed_knots, field="nominal_speed_knots")
        if candidate_route_distance_nm is None:
            design_distance = great_circle_distance_nm * self.corridor_detour_factor
        else:
            _positive(candidate_route_distance_nm, field="candidate_route_distance_nm")
            design_distance = candidate_route_distance_nm
        planning_speed = nominal_speed_knots * self.conservative_environment_speed_factor
        eta_hours = design_distance / planning_speed
        buffered = eta_hours + max(
            self.minimum_buffer_hours,
            eta_hours * self.proportional_buffer,
        )
        required = math.ceil(buffered / self.rounding_hours) * self.rounding_hours
        if required > self.maximum_hours:
            return HorizonAssessment(
                required_hours=required,
                selected_hours=None,
                coverage_sufficient=False,
                maximum_hours=self.maximum_hours,
            )
        return HorizonAssessment(
            required_hours=required,
            selected_hours=max(self.minimum_hours, required),
            coverage_sufficient=True,
            maximum_hours=self.maximum_hours,
        )


@dataclass(frozen=True, slots=True)
class CorridorDefinition:
    schema_version: str
    corridor_id: str
    version: str
    display_name: str
    role: CorridorRole
    crs: str
    start: GeoPoint
    destination: GeoPoint
    start_allowed_region: GeoBoundingBox
    destination_allowed_region: GeoBoundingBox
    data_bbox: GeoBoundingBox
    horizon_policy: HorizonPolicy
    reference_points: tuple[ReferencePoint, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != "corridor.v1":
            raise ContractError("CorridorDefinition.schema_version must be corridor.v1")
        validate_identifier(self.corridor_id, field="corridor_id")
        validate_version(self.version, field="corridor.version")
        if not self.display_name.strip():
            raise ContractError("corridor display_name cannot be empty")
        if self.crs != "EPSG:4326":
            raise ContractError("corridor.v1 accepts only EPSG:4326")
        if not self.start_allowed_region.contains(self.start):
            raise ContractError("start must be inside start_allowed_region")
        if not self.destination_allowed_region.contains(self.destination):
            raise ContractError("destination must be inside destination_allowed_region")
        if not self.data_bbox.contains_box(self.start_allowed_region):
            raise ContractError("data_bbox must contain start_allowed_region")
        if not self.data_bbox.contains_box(self.destination_allowed_region):
            raise ContractError("data_bbox must contain destination_allowed_region")
        if any(not self.data_bbox.contains(point.location) for point in self.reference_points):
            raise ContractError("all reference points must be inside data_bbox")
        ids = [point.reference_id for point in self.reference_points]
        if len(ids) != len(set(ids)):
            raise ContractError("reference-point IDs must be unique")

    @property
    def great_circle_distance_nm(self) -> float:
        radius_nm = 3440.065
        lat1 = math.radians(self.start.latitude)
        lat2 = math.radians(self.destination.latitude)
        delta_lat = lat2 - lat1
        delta_lon = math.radians(self.destination.longitude - self.start.longitude)
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        return radius_nm * 2 * math.asin(math.sqrt(haversine))


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    schema_version: str
    scenario_id: str
    version: str
    display_name: str
    corridor_id: str
    corridor_version: str
    mode: ScenarioMode
    simulation_start: datetime | None
    simulation_end: datetime | None
    horizon_hours: int
    default_vessel_profile_id: str
    default_vessel_profile_version: str
    required_data_types: tuple[str, ...]
    optional_data_types: tuple[str, ...]
    forecast_anchor_policy: str | None
    is_template: bool = False
    random_seed: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != "scenario.v2":
            raise ContractError("ScenarioDefinition.schema_version must be scenario.v2")
        validate_identifier(self.scenario_id, field="scenario_id")
        validate_version(self.version, field="scenario.version")
        validate_identifier(self.corridor_id, field="corridor_id")
        validate_version(self.corridor_version, field="corridor_version")
        validate_identifier(self.default_vessel_profile_id, field="default_vessel_profile_id")
        validate_version(
            self.default_vessel_profile_version,
            field="default_vessel_profile_version",
        )
        required_types = tuple(self.required_data_types)
        optional_types = tuple(self.optional_data_types)
        if not required_types:
            raise ContractError("required_data_types cannot be empty")
        for field, values in (
            ("required_data_types", required_types),
            ("optional_data_types", optional_types),
        ):
            if tuple(sorted(set(values))) != values:
                raise ContractError(f"{field} must be unique and canonically sorted")
            for value in values:
                validate_identifier(value, field=field)
        if set(required_types) & set(optional_types):
            raise ContractError("required_data_types and optional_data_types must be disjoint")
        object.__setattr__(self, "required_data_types", required_types)
        object.__setattr__(self, "optional_data_types", optional_types)
        if not self.display_name.strip():
            raise ContractError("scenario display_name cannot be empty")
        if not isinstance(self.horizon_hours, int) or isinstance(self.horizon_hours, bool):
            raise ContractError("horizon_hours must be an integer")
        if self.horizon_hours <= 0:
            raise ContractError("horizon_hours must be positive")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise ContractError("random_seed must be an integer")
        if self.is_template:
            if self.mode is not ScenarioMode.FROZEN_FORECAST:
                raise ContractError("only frozen_forecast scenarios may be templates")
            if self.simulation_start is not None or self.simulation_end is not None:
                raise ContractError("scenario templates cannot contain simulation times")
            if self.forecast_anchor_policy != "explicit_utc_only":
                raise ContractError("frozen templates require explicit_utc_only anchor policy")
            return
        if self.simulation_start is None or self.simulation_end is None:
            raise ContractError("concrete scenarios require simulation_start and simulation_end")
        start = ensure_utc(self.simulation_start, field="simulation_start")
        end = ensure_utc(self.simulation_end, field="simulation_end")
        if end != start + timedelta(hours=self.horizon_hours):
            raise ContractError("simulation_end must equal simulation_start + horizon_hours")
        if self.mode is ScenarioMode.FROZEN_FORECAST:
            if self.forecast_anchor_policy != "explicit_utc_only":
                raise ContractError("frozen forecasts require explicit_utc_only anchor policy")
        elif self.forecast_anchor_policy is not None:
            raise ContractError("retrospective scenarios cannot define a forecast anchor policy")
        object.__setattr__(self, "simulation_start", start)
        object.__setattr__(self, "simulation_end", end)


@dataclass(frozen=True, slots=True)
class VesselProfile:
    schema_version: str
    vessel_profile_id: str
    version: str
    display_name: str
    calibration_status: CalibrationStatus
    vessel_type: str
    imo_number: str
    deadweight_tonnes: int
    ice_class_system: str
    ice_class: str
    built_year: int
    builder: str
    length_overall_m: float
    beam_m: float
    reported_draft_m: float
    nominal_speed_knots: float
    reference_load_condition: str
    source_urls: tuple[str, ...]
    source_notes: str

    def __post_init__(self) -> None:
        if self.schema_version != "vessel-profile.v2":
            raise ContractError("VesselProfile.schema_version must be vessel-profile.v2")
        validate_identifier(self.vessel_profile_id, field="vessel_profile_id")
        validate_version(self.version, field="vessel.version")
        text_fields = (
            self.display_name,
            self.vessel_type,
            self.ice_class_system,
            self.ice_class,
            self.builder,
            self.reference_load_condition,
            self.source_notes,
        )
        if any(not value.strip() for value in text_fields):
            raise ContractError("vessel text fields cannot be empty")
        if not self.imo_number.isdigit() or len(self.imo_number) != 7:
            raise ContractError("imo_number must contain seven digits")
        if not isinstance(self.deadweight_tonnes, int) or self.deadweight_tonnes <= 0:
            raise ContractError("deadweight_tonnes must be a positive integer")
        if not isinstance(self.built_year, int) or not 1900 <= self.built_year <= 2100:
            raise ContractError("built_year is outside the supported range")
        for field, value in (
            ("length_overall_m", self.length_overall_m),
            ("beam_m", self.beam_m),
            ("reported_draft_m", self.reported_draft_m),
            ("nominal_speed_knots", self.nominal_speed_knots),
        ):
            _positive(value, field=field)
        if not self.source_urls or any(not url.startswith("https://") for url in self.source_urls):
            raise ContractError("source_urls must contain HTTPS references")
        if self.imo_number == "9529451" and self.ice_class.upper().startswith("PC"):
            raise ContractError("Nordic Odyssey reference must not be presented as Polar Class")


@dataclass(frozen=True, slots=True)
class RunContext:
    schema_version: str
    run_id: str
    created_at: datetime
    scenario_id: str
    scenario_version: str
    scenario_mode: ScenarioMode
    simulation_start: datetime
    simulation_end: datetime
    scenario_digest: str
    corridor_id: str
    corridor_version: str
    corridor_digest: str
    vessel_profile_id: str
    vessel_profile_version: str
    vessel_profile_digest: str
    dataset_bundle_id: str
    dataset_bundle_digest: str
    config_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != "run-context.v2":
            raise ContractError("RunContext.schema_version must be run-context.v2")
        if not isinstance(self.run_id, str) or not self.run_id.startswith("run-"):
            raise ContractError("run_id must use the run-<UUID> form")
        try:
            UUID(self.run_id.removeprefix("run-"))
        except ValueError as exc:
            raise ContractError("run_id must use the run-<UUID> form") from exc
        validate_identifier(self.scenario_id, field="scenario_id")
        validate_version(self.scenario_version, field="scenario_version")
        validate_identifier(self.corridor_id, field="corridor_id")
        validate_version(self.corridor_version, field="corridor_version")
        validate_identifier(self.vessel_profile_id, field="vessel_profile_id")
        validate_version(self.vessel_profile_version, field="vessel_profile_version")
        if re.fullmatch(r"a-bundle-[0-9a-f]{24}", self.dataset_bundle_id) is None:
            raise ContractError("dataset_bundle_id must be an A DatasetBundle ID")
        for field, value in (
            ("scenario_digest", self.scenario_digest),
            ("corridor_digest", self.corridor_digest),
            ("vessel_profile_digest", self.vessel_profile_digest),
            ("dataset_bundle_digest", self.dataset_bundle_digest),
            ("config_digest", self.config_digest),
        ):
            validate_digest(value, field=field)
        created = ensure_utc(self.created_at, field="created_at")
        start = ensure_utc(self.simulation_start, field="simulation_start")
        end = ensure_utc(self.simulation_end, field="simulation_end")
        if end <= start:
            raise ContractError("RunContext simulation_end must be after simulation_start")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "simulation_start", start)
        object.__setattr__(self, "simulation_end", end)
