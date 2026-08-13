"""Independent verification of Work Package A DatasetBundle v1/v2 identities."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from .errors import ContractError
from .models import validate_digest, validate_identifier
from .timeutils import isoformat_utc, parse_utc

_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+\-]{0,127}$")
_FORMAL_CADENCE_HOURS: dict[str, frozenset[float | None]] = {
    # Frozen GFS is 3-hourly; NCEI retrospective analysis is 6-hourly.
    "wind_field": frozenset({3.0, 6.0}),
    "temperature": frozenset({3.0, 6.0}),
    "visibility": frozenset({3.0, 6.0}),
    "wave": frozenset({3.0}),
    # Current A native Copernicus products are published as hourly frames.
    "ocean_current": frozenset({1.0}),
    "water_level": frozenset({1.0}),
    "sea_ice_concentration": frozenset({1.0}),
    "sea_ice_type": frozenset({1.0}),
    "sea_ice_edge": frozenset({1.0}),
    "sea_ice_drift": frozenset({1.0}),
    "sea_ice_thickness": frozenset({1.0}),
    "bathymetry": frozenset({None}),
    "land_sea_mask": frozenset({None}),
    "long_term_restricted_area": frozenset({None}),
}


@dataclass(frozen=True, slots=True, init=False)
class DatasetBundleIdentity:
    schema_version: str
    bundle_id: str
    bundle_digest: str
    corridor_id: str
    as_of_time: datetime
    requested_start: datetime
    requested_end: datetime
    minimum_required_end: datetime
    requested_data_types: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...]
    record_count: int
    coverage_complete: bool
    # Keep the complete verified transport document so every trust-boundary
    # consumer can recompute records, cadence and provenance instead of
    # trusting this compact summary (including instances forged through
    # Python's introspection facilities).
    _verified_document_json: str

    @classmethod
    def _verified(
        cls,
        *,
        schema_version: str,
        bundle_id: str,
        bundle_digest: str,
        corridor_id: str,
        as_of_time: datetime,
        requested_start: datetime,
        requested_end: datetime,
        minimum_required_end: datetime,
        requested_data_types: tuple[str, ...],
        source_snapshot_ids: tuple[str, ...],
        record_count: int,
        coverage_complete: bool,
        verified_document_json: str,
    ) -> DatasetBundleIdentity:
        instance = object.__new__(cls)
        for name, value in locals().items():
            if name not in {"cls", "instance"}:
                target = "_verified_document_json" if name == "verified_document_json" else name
                object.__setattr__(instance, target, value)
        return instance

    @property
    def formal_run_eligible(self) -> bool:
        return self.schema_version == "a.dataset-bundle.v2" and self.coverage_complete


def load_dataset_bundle(path: str | Path) -> DatasetBundleIdentity:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"DatasetBundle file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"DatasetBundle is not valid JSON: {path}: {exc}") from exc
    return verify_dataset_bundle(value)


def reverify_dataset_bundle_identity(
    identity: DatasetBundleIdentity,
) -> DatasetBundleIdentity:
    """Recompute a compact identity from its complete bound document.

    ``DatasetBundleIdentity`` is intentionally convenient for callers, but a
    Python object alone is not a trust boundary: private constructors can still
    be reached through introspection.  Formal RunContext creation therefore
    calls this function and accepts only fields reproduced by the full v2
    document verifier.
    """

    if not isinstance(identity, DatasetBundleIdentity):
        raise ContractError("dataset_bundle must come from load/verify_dataset_bundle")
    try:
        document = json.loads(identity._verified_document_json)
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError("DatasetBundleIdentity has no verifiable bound document") from exc
    verified = verify_dataset_bundle(document)
    public_fields = (
        "schema_version",
        "bundle_id",
        "bundle_digest",
        "corridor_id",
        "as_of_time",
        "requested_start",
        "requested_end",
        "minimum_required_end",
        "requested_data_types",
        "source_snapshot_ids",
        "record_count",
        "coverage_complete",
    )
    if any(getattr(identity, name) != getattr(verified, name) for name in public_fields):
        raise ContractError(
            "DatasetBundleIdentity fields do not match its independently verified document"
        )
    return verified


def verify_dataset_bundle(value: Mapping[str, Any]) -> DatasetBundleIdentity:
    if not isinstance(value, Mapping):
        raise ContractError("DatasetBundle must be an object")
    version = value.get("schema_version")
    if version not in {"a.dataset-bundle.v1", "a.dataset-bundle.v2"}:
        raise ContractError("DatasetBundle schema_version must be v1 or v2")
    required = {
        "schema_version",
        "bundle_id",
        "bundle_digest",
        "corridor_id",
        "as_of_time",
        "requested_start",
        "requested_end",
        "minimum_required_end",
        "requested_data_types",
        "source_snapshot_ids",
        "record_count",
        "records",
    }
    if version == "a.dataset-bundle.v2":
        required.add("coverage")
    if set(value) != required:
        raise ContractError(f"DatasetBundle fields must exactly match {version}")
    corridor_id = value["corridor_id"]
    validate_identifier(corridor_id, field="DatasetBundle.corridor_id")
    bundle_digest = value["bundle_digest"]
    validate_digest(bundle_digest, field="DatasetBundle.bundle_digest")
    if value["bundle_id"] != f"a-bundle-{bundle_digest[:24]}":
        raise ContractError("DatasetBundle bundle_id does not match bundle_digest")
    requested_types = _identifier_list(value["requested_data_types"], "requested_data_types")
    if not requested_types:
        raise ContractError("DatasetBundle requested_data_types cannot be empty")
    snapshots = _snapshot_list(value["source_snapshot_ids"])
    raw_records = value["records"]
    if not isinstance(raw_records, list):
        raise ContractError("DatasetBundle records must be an array")
    if (
        not isinstance(value["record_count"], int)
        or isinstance(value["record_count"], bool)
        or value["record_count"] != len(raw_records)
    ):
        raise ContractError("DatasetBundle record_count does not match records")
    records = tuple(_normalize_record(record) for record in raw_records)
    canonical_records = tuple(
        sorted(
            records,
            key=lambda item: (
                item["data_type"],
                parse_utc(item["valid_time"]),
                item["data_id"],
            ),
        )
    )
    if records != canonical_records:
        raise ContractError("DatasetBundle records are not canonically sorted")
    if len({record["data_id"] for record in records}) != len(records):
        raise ContractError("DatasetBundle contains duplicate data_id values")
    if {record["data_type"] for record in records} - set(requested_types):
        raise ContractError("DatasetBundle contains unrequested data types")
    derived_snapshots = tuple(
        sorted(
            {
                record["source_snapshot_id"]
                for record in records
                if record["source_snapshot_id"] is not None
            }
        )
    )
    if snapshots != derived_snapshots:
        raise ContractError("DatasetBundle source_snapshot_ids do not match records")
    as_of = parse_utc(value["as_of_time"], field="DatasetBundle.as_of_time")
    start = parse_utc(value["requested_start"], field="DatasetBundle.requested_start")
    end = parse_utc(value["requested_end"], field="DatasetBundle.requested_end")
    minimum_end = parse_utc(
        value["minimum_required_end"], field="DatasetBundle.minimum_required_end"
    )
    if not start <= minimum_end <= end:
        raise ContractError("DatasetBundle time bounds are invalid")
    if any(parse_utc(record["issue_time"]) > as_of for record in records):
        raise ContractError("DatasetBundle contains records issued after as_of_time")

    coverage: list[dict[str, Any]] = []
    coverage_complete = False
    if version == "a.dataset-bundle.v2":
        raw_coverage = value["coverage"]
        if not isinstance(raw_coverage, list) or len(raw_coverage) != len(requested_types):
            raise ContractError("DatasetBundle coverage must cover every requested type")
        intervals = _coverage_intervals(raw_coverage, requested_types)
        for data_type, interval in intervals.items():
            if data_type not in _FORMAL_CADENCE_HOURS:
                raise ContractError(f"DatasetBundle has unknown formal data type: {data_type}")
            if interval not in _FORMAL_CADENCE_HOURS[data_type]:
                allowed = sorted(
                    _FORMAL_CADENCE_HOURS[data_type],
                    key=lambda value: -1 if value is None else value,
                )
                raise ContractError(
                    f"DatasetBundle cadence for {data_type} does not match the formal "
                    f"contract: allowed={allowed}"
                )
        coverage = [
            _rebuild_coverage(
                data_type=data_type,
                records=tuple(record for record in records if record["data_type"] == data_type),
                requested_start=start,
                requested_end=end,
                minimum_required_end=minimum_end,
                expected_interval_hours=intervals[data_type],
            )
            for data_type in requested_types
        ]
        if coverage != raw_coverage:
            raise ContractError(
                "DatasetBundle coverage does not match independently recomputed "
                "records/cadence/provenance"
            )
        coverage_complete = bool(coverage) and all(item["complete"] for item in coverage)

    identity: dict[str, Any] = {
        "schema_version": version,
        "corridor_id": corridor_id,
        "as_of_time": isoformat_utc(as_of),
        "requested_start": isoformat_utc(start),
        "requested_end": isoformat_utc(end),
        "minimum_required_end": isoformat_utc(minimum_end),
        "requested_data_types": list(requested_types),
        "source_snapshot_ids": list(snapshots),
        "records": list(records),
    }
    if version == "a.dataset-bundle.v2":
        identity["coverage"] = coverage
    calculated = _canonical_digest(identity)
    if calculated != bundle_digest:
        raise ContractError("DatasetBundle content digest verification failed")
    verified_document = {
        **identity,
        "bundle_id": value["bundle_id"],
        "bundle_digest": bundle_digest,
        "record_count": len(records),
    }
    return DatasetBundleIdentity._verified(
        schema_version=str(version),
        bundle_id=value["bundle_id"],
        bundle_digest=bundle_digest,
        corridor_id=corridor_id,
        as_of_time=as_of,
        requested_start=start,
        requested_end=end,
        minimum_required_end=minimum_end,
        requested_data_types=requested_types,
        source_snapshot_ids=snapshots,
        record_count=len(records),
        coverage_complete=coverage_complete,
        verified_document_json=json.dumps(
            verified_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _coverage_intervals(
    coverage: list[Any], requested_types: tuple[str, ...]
) -> dict[str, float | None]:
    intervals: dict[str, float | None] = {}
    for item in coverage:
        if not isinstance(item, Mapping) or not isinstance(item.get("data_type"), str):
            raise ContractError("DatasetBundle coverage entry is invalid")
        data_type = item["data_type"]
        if data_type in intervals:
            raise ContractError("DatasetBundle coverage contains duplicate data types")
        interval = item.get("expected_interval_hours")
        if interval is not None and (
            isinstance(interval, bool)
            or not isinstance(interval, int | float)
            or not math.isfinite(float(interval))
            or interval <= 0
        ):
            raise ContractError("DatasetBundle expected_interval_hours is invalid")
        intervals[data_type] = None if interval is None else float(interval)
    if tuple(intervals) != requested_types:
        raise ContractError("DatasetBundle coverage must be canonically sorted")
    return intervals


def _rebuild_coverage(
    *,
    data_type: str,
    records: tuple[dict[str, Any], ...],
    requested_start: datetime,
    requested_end: datetime,
    minimum_required_end: datetime,
    expected_interval_hours: float | None,
) -> dict[str, Any]:
    times = [parse_utc(record["valid_time"]) for record in records]
    missing: list[tuple[datetime, datetime]] = []
    if expected_interval_hours is not None:
        for lower, upper in pairwise(times):
            if (
                (upper - lower).total_seconds() / 3600 > expected_interval_hours
                and lower < requested_end
                and upper > requested_start
            ):
                missing.append((lower, upper))
    available_start = times[0] if times else None
    available_end = times[-1] if times else None
    snapshots = sorted(
        {
            record["source_snapshot_id"]
            for record in records
            if record["source_snapshot_id"] is not None
        }
    )
    provenance_complete = bool(records) and all(
        record["source_snapshot_id"] is not None for record in records
    )
    if expected_interval_hours is None:
        has_start_support = bool(records)
        meets_minimum = bool(records)
        covers_requested = bool(records)
    else:
        has_start_support = any(time <= requested_start for time in times) and any(
            time >= requested_start for time in times
        )
        meets_minimum = (
            has_start_support
            and available_end is not None
            and available_end >= minimum_required_end
            and not any(lower < minimum_required_end for lower, _ in missing)
        )
        covers_requested = (
            has_start_support
            and available_end is not None
            and available_end >= requested_end
            and not any(lower < requested_end for lower, _ in missing)
        )
    provenance = [
        {
            "data_id": record["data_id"],
            "checksum": record["checksum"],
            "source_snapshot_id": record["source_snapshot_id"],
        }
        for record in records
    ]
    result: dict[str, Any] = {
        "data_type": data_type,
        "record_count": len(records),
        "records_digest": _canonical_digest(list(records)),
        "provenance_digest": _canonical_digest(provenance),
        "available_start": isoformat_utc(available_start) if available_start else None,
        "available_end": isoformat_utc(available_end) if available_end else None,
        "expected_interval_hours": expected_interval_hours,
        "missing_intervals": [
            [isoformat_utc(lower), isoformat_utc(upper)] for lower, upper in missing
        ],
        "source_snapshot_ids": snapshots,
        "has_start_support": has_start_support,
        "meets_minimum_horizon": meets_minimum,
        "covers_requested_window": covers_requested,
        "provenance_complete": provenance_complete,
        "complete": covers_requested and provenance_complete,
    }
    result["coverage_digest"] = _canonical_digest(result)
    return result


def _identifier_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"DatasetBundle {field} must be a unique array")
    if len(set(value)) != len(value):
        raise ContractError(f"DatasetBundle {field} must be a unique array")
    for item in value:
        validate_identifier(item, field=f"DatasetBundle.{field}")
    if value != sorted(value):
        raise ContractError(f"DatasetBundle {field} must be sorted")
    return tuple(value)


def _snapshot_list(value: Any) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or _SNAPSHOT_ID.fullmatch(item) is None for item in value)
        or len(set(value)) != len(value)
        or value != sorted(value)
    ):
        raise ContractError("DatasetBundle source_snapshot_ids are invalid")
    return tuple(value)


def _normalize_record(value: Any) -> dict[str, Any]:
    required = {
        "data_id",
        "data_type",
        "issue_time",
        "valid_time",
        "source",
        "version",
        "quality_flag",
        "checksum",
        "source_snapshot_id",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ContractError("DatasetBundle record fields are invalid")
    for field in ("data_id", "data_type", "source", "version"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ContractError(f"DatasetBundle record {field} cannot be empty")
    if value["quality_flag"] not in {"good", "suspect", "degraded"}:
        raise ContractError("DatasetBundle record quality_flag is invalid")
    validate_digest(value["checksum"], field="DatasetBundle record checksum")
    snapshot = value["source_snapshot_id"]
    if snapshot is not None and (
        not isinstance(snapshot, str) or _SNAPSHOT_ID.fullmatch(snapshot) is None
    ):
        raise ContractError("DatasetBundle record source_snapshot_id is invalid")
    return {
        "data_id": value["data_id"],
        "data_type": value["data_type"],
        "issue_time": isoformat_utc(parse_utc(value["issue_time"], field="issue_time")),
        "valid_time": isoformat_utc(parse_utc(value["valid_time"], field="valid_time")),
        "source": value["source"],
        "version": value["version"],
        "quality_flag": value["quality_flag"],
        "checksum": value["checksum"],
        "source_snapshot_id": snapshot,
    }
