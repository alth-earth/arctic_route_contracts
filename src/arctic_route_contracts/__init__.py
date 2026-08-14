"""Public API for system-wide Arctic-route facts and run identity."""

from .bundle import DatasetBundleIdentity, load_dataset_bundle, verify_dataset_bundle
from .config import (
    default_config_root,
    list_config_ids,
    load_corridor,
    load_scenario,
    load_vessel_profile,
    materialize_frozen_forecast,
    validate_scenario_for_corridor,
    validate_scenario_for_vessel,
)
from .context import (
    create_run_context,
    load_run_context,
    run_context_from_dict,
    run_context_to_dict,
    write_run_context_atomic,
)
from .digest import canonical_json_bytes, canonical_sha256, configuration_digest
from .errors import ContractError
from .models import (
    CalibrationStatus,
    CorridorDefinition,
    CorridorRole,
    GeoBoundingBox,
    GeoPoint,
    HorizonAssessment,
    HorizonPolicy,
    ReferencePoint,
    RunContext,
    ScenarioDefinition,
    ScenarioMode,
    VesselProfile,
)

__all__ = [
    "CalibrationStatus",
    "ContractError",
    "CorridorDefinition",
    "CorridorRole",
    "DatasetBundleIdentity",
    "GeoBoundingBox",
    "GeoPoint",
    "HorizonAssessment",
    "HorizonPolicy",
    "ReferencePoint",
    "RunContext",
    "ScenarioDefinition",
    "ScenarioMode",
    "VesselProfile",
    "canonical_json_bytes",
    "canonical_sha256",
    "configuration_digest",
    "create_run_context",
    "default_config_root",
    "list_config_ids",
    "load_corridor",
    "load_dataset_bundle",
    "load_run_context",
    "load_scenario",
    "load_vessel_profile",
    "materialize_frozen_forecast",
    "run_context_from_dict",
    "run_context_to_dict",
    "validate_scenario_for_corridor",
    "validate_scenario_for_vessel",
    "verify_dataset_bundle",
    "write_run_context_atomic",
]

__version__ = "0.3.0"
