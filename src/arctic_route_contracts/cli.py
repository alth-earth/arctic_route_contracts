"""Small stdlib-only launcher for shared configuration and RunContext creation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .bundle import load_dataset_bundle
from .config import (
    default_config_root,
    list_config_ids,
    load_corridor,
    load_scenario,
    load_vessel_profile,
    materialize_frozen_forecast,
    validate_scenario_for_vessel,
)
from .context import create_run_context, write_run_context_atomic
from .digest import canonical_sha256
from .errors import ContractError
from .timeutils import parse_utc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arctic-route-context",
        description="Validate shared facts and create immutable system RunContext files.",
    )
    parser.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="shared configs directory (defaults to the packaged/source config root)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list available shared config IDs")
    list_parser.add_argument(
        "--kind",
        choices=("all", "corridors", "scenarios", "vessels"),
        default="all",
    )

    subparsers.add_parser("validate", help="load and cross-check every shared config")

    recommend_parser = subparsers.add_parser(
        "recommend-horizon",
        help="assess a route-specific full-voyage horizon without changing config files",
    )
    recommend_parser.add_argument("--corridor", required=True, dest="corridor_id")
    recommend_parser.add_argument("--vessel", required=True, dest="vessel_profile_id")
    recommend_parser.add_argument(
        "--candidate-route-distance-nm",
        type=float,
        help="optional candidate route length; otherwise use great-circle × detour factor",
    )

    create_parser = subparsers.add_parser(
        "create",
        help="bind a concrete scenario and vessel to an exact A DatasetBundle",
    )
    create_parser.add_argument("--scenario", required=True, dest="scenario_id")
    create_parser.add_argument("--vessel", dest="vessel_profile_id")
    create_parser.add_argument("--dataset-bundle", required=True, type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    create_parser.add_argument(
        "--simulation-start",
        help="required UTC ISO-8601 anchor for a frozen-forecast template",
    )
    create_parser.add_argument(
        "--candidate-route-distance-nm",
        type=float,
        help=(
            "for a frozen template, select a route-specific horizon from the shared policy; "
            "unsupported coverage fails closed"
        ),
    )
    create_parser.add_argument("--run-id", help="optional explicit run-<UUID> identity")
    create_parser.add_argument(
        "--created-at",
        help="optional explicit UTC creation time (primarily for reproducible tests)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        root = args.config_root or default_config_root()
        if args.command == "list":
            values = list_config_ids(root)
            if args.kind != "all":
                values = {args.kind: values[args.kind]}
            print(json.dumps(values, ensure_ascii=False, indent=2))
            return 0
        if args.command == "validate":
            summary = _validate_all(root)
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "recommend-horizon":
            summary = _recommend_horizon(args, root)
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if summary["coverage_sufficient"] else 2
        if args.command == "create":
            context = _create(args, root)
            write_run_context_atomic(context, args.output)
            print(
                json.dumps(
                    {
                        "output": str(args.output),
                        "run_id": context.run_id,
                        "scenario_id": context.scenario_id,
                        "scenario_version": context.scenario_version,
                        "scenario_digest": context.scenario_digest,
                        "config_digest": context.config_digest,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except ContractError as exc:
        parser.exit(2, f"error: {exc}\n")
    raise AssertionError("unreachable")


def _validate_all(root: Path) -> dict[str, object]:
    ids = list_config_ids(root)
    corridors = {config_id: load_corridor(root, config_id) for config_id in ids["corridors"]}
    vessels = {config_id: load_vessel_profile(root, config_id) for config_id in ids["vessels"]}
    scenarios = {}
    for config_id in ids["scenarios"]:
        scenario = load_scenario(root, config_id)
        vessel = vessels.get(scenario.default_vessel_profile_id)
        if vessel is None:
            raise ContractError(
                f"scenario {scenario.scenario_id} references an unknown vessel profile"
            )
        validate_scenario_for_vessel(scenario, vessel)
        scenarios[config_id] = scenario
    return {
        "status": "valid",
        "config_root": str(root.resolve()),
        "counts": {
            "corridors": len(corridors),
            "scenarios": len(scenarios),
            "vessels": len(vessels),
        },
        "digests": {
            "corridors": {
                config_id: canonical_sha256(value) for config_id, value in corridors.items()
            },
            "scenarios": {
                config_id: canonical_sha256(value) for config_id, value in scenarios.items()
            },
            "vessels": {config_id: canonical_sha256(value) for config_id, value in vessels.items()},
        },
    }


def _create(args: argparse.Namespace, root: Path):
    scenario = load_scenario(root, args.scenario_id)
    corridor = load_corridor(root, scenario.corridor_id)
    vessel_id = args.vessel_profile_id or scenario.default_vessel_profile_id
    vessel = load_vessel_profile(root, vessel_id)
    if scenario.is_template:
        if args.simulation_start is None:
            raise ContractError("frozen-forecast templates require --simulation-start")
        selected_horizon = None
        if args.candidate_route_distance_nm is not None:
            selected_horizon = corridor.horizon_policy.recommend_hours(
                great_circle_distance_nm=corridor.great_circle_distance_nm,
                nominal_speed_knots=vessel.nominal_speed_knots,
                candidate_route_distance_nm=args.candidate_route_distance_nm,
            )
        scenario = materialize_frozen_forecast(
            scenario,
            parse_utc(args.simulation_start, field="simulation_start"),
            horizon_hours=selected_horizon,
        )
    elif args.simulation_start is not None or args.candidate_route_distance_nm is not None:
        raise ContractError(
            "--simulation-start/--candidate-route-distance-nm are accepted only "
            "for a scenario template"
        )
    bundle = load_dataset_bundle(args.dataset_bundle)
    created_at = parse_utc(args.created_at, field="created_at") if args.created_at else None
    return create_run_context(
        scenario=scenario,
        corridor=corridor,
        vessel=vessel,
        dataset_bundle=bundle,
        run_id=args.run_id,
        created_at=created_at,
    )


def _recommend_horizon(args: argparse.Namespace, root: Path) -> dict[str, object]:
    corridor = load_corridor(root, args.corridor_id)
    vessel = load_vessel_profile(root, args.vessel_profile_id)
    candidate = args.candidate_route_distance_nm
    assessment = corridor.horizon_policy.assess_hours(
        great_circle_distance_nm=corridor.great_circle_distance_nm,
        nominal_speed_knots=vessel.nominal_speed_knots,
        candidate_route_distance_nm=candidate,
    )
    design_distance = (
        candidate
        if candidate is not None
        else corridor.great_circle_distance_nm * corridor.horizon_policy.corridor_detour_factor
    )
    return {
        "status": (
            "sufficient" if assessment.coverage_sufficient else "forecast_coverage_insufficient"
        ),
        "corridor_id": corridor.corridor_id,
        "vessel_profile_id": vessel.vessel_profile_id,
        "great_circle_distance_nm": round(corridor.great_circle_distance_nm, 3),
        "candidate_route_distance_nm": candidate,
        "design_distance_nm": round(design_distance, 3),
        "nominal_speed_knots": vessel.nominal_speed_knots,
        "required_hours": assessment.required_hours,
        "selected_hours": assessment.selected_hours,
        "maximum_hours": assessment.maximum_hours,
        "coverage_sufficient": assessment.coverage_sufficient,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
