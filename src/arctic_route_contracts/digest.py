"""Canonical JSON serialization and shared content identities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .errors import ContractError
from .models import CorridorDefinition, ScenarioDefinition, VesselProfile, validate_digest
from .timeutils import isoformat_utc


def canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_value(asdict(value))
    if isinstance(value, datetime):
        return isoformat_utc(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(*objects: object) -> str:
    value: object = objects[0] if len(objects) == 1 else list(objects)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def configuration_digest(
    scenario: ScenarioDefinition,
    corridor: CorridorDefinition,
    vessel: VesselProfile,
    *,
    dataset_bundle_id: str,
    dataset_bundle_digest: str,
) -> str:
    """Hash only shared scenario/vessel facts and A's content-addressed bundle."""

    validate_digest(dataset_bundle_digest, field="dataset_bundle_digest")
    if re.fullmatch(r"a-bundle-[0-9a-f]{24}", dataset_bundle_id) is None:
        raise ContractError("dataset_bundle_id must be an A DatasetBundle ID")
    identity = {
        "schema_version": "shared-config-digest.v2",
        "scenario": {
            "definition": scenario,
            "corridor": corridor,
        },
        "vessel_profile": vessel,
        "dataset_bundle": {
            "bundle_id": dataset_bundle_id,
            "bundle_digest": dataset_bundle_digest,
        },
    }
    return canonical_sha256(identity)
