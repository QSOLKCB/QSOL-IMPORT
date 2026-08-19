from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from qsol_import.canonical import canonical_json_bytes, loads_strict, sha256_bytes, sha256_file


OBSERVATION_PROTOCOL = "QSOL-ARK/THOTH-EVALUATION-OBSERVATION/1"
RECEIPT_PROTOCOL = "QSOL-IMPORT/ARK-CLEANROOM-RECEIPT/1"
ARK_CONTRACT_PROTOCOL = "QSOL-ARK/PERSONAL-CONTINUITY/1"
THOTH_POLICY_PROTOCOL = "QSOL-THOTH/ARK-EVALUATION-POLICY/1"
SCHEMA_VERSION = "1.0.0"
MAX_OBSERVATION_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 10_000
MAX_OBJECT_BYTES = 2 * 1024 * 1024 * 1024
TRIALS = {"P0", "P1", "P2", "P3"}
RECORD_CLASSES = {"synthetic-conformance", "externally-observed-clean-room"}
TRANSPORT_PROFILES = (
    "local-directory",
    "archive",
    "static-http",
    "capability-relay",
)
NEGATIVE_SPACE_CHECKS = (
    "style_leakage",
    "unsupported_historical_interpolation",
    "accidental_private_source_dependency",
)
BOUNDARIES = (
    "PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION",
    "RESTORED_STYLE != IDENTITY_PROOF",
    "RESTORED_CONTEXT != HIDDEN_PROVIDER_MEMORY",
    "RECOVERY_SCORE != TRUTH",
    "CAPSULE_HASH_MATCH != CLAIM_AUTHORITY",
    "CLEAN_ROOM_SUCCESS != ORIGINAL_ASSISTANT_CONTINUITY",
    "STYLE_FIDELITY != FACTUAL_ACCURACY != PHYSICAL_TRUTH",
    "ROUTE_SUFFICIENCY != ROUTE_MINIMALITY",
    "HISTORICAL_COVERAGE != HISTORICAL_TRUTH",
    "TRANSPORT_EQUIVALENCE != AUTHORITY",
    "MEASURED_OBSERVATION != AUTOMATIC_TRUTH",
    "AGGREGATE_SCORE = FORBIDDEN",
)


class ArkCleanroomError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ArkCleanroomError("observation_input", "observation must be a non-symlink file")
    if path.stat().st_size > MAX_OBSERVATION_BYTES:
        raise ArkCleanroomError("observation_size", "observation exceeds size limit")
    try:
        value = loads_strict(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ArkCleanroomError("observation_json", "observation is not strict JSON") from exc
    if not isinstance(value, dict):
        raise ArkCleanroomError("observation_shape", "observation must contain an object")
    return value


def _require_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    if set(value) != expected:
        raise ArkCleanroomError(
            "observation_fields",
            f"{where} fields mismatch: expected {sorted(expected)!r}, found {sorted(value)!r}",
        )


def _unique_strings(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ArkCleanroomError("observation_array", f"{where} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise ArkCleanroomError("observation_duplicate", f"{where} contains duplicate values")
    return list(value)


def _metric(numerator: int, denominator: int, *, fail: bool = False) -> dict[str, Any]:
    if denominator == 0:
        return {
            "status": "unassessed",
            "numerator": numerator,
            "denominator": denominator,
            "basis_points": None,
        }
    return {
        "status": "fail" if fail else "pass",
        "numerator": numerator,
        "denominator": denominator,
        "basis_points": (numerator * 10_000) // denominator,
    }


def _outcome_metric(rows: Any, *, pass_value: str, fail_value: str, where: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ArkCleanroomError("observation_dimension", f"{where} must be an array")
    seen: set[str] = set()
    passed = 0
    failed = 0
    unassessed = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"id", "outcome"}:
            raise ArkCleanroomError("observation_dimension", f"{where}[{index}] has invalid fields")
        item_id = row["id"]
        outcome = row["outcome"]
        if not isinstance(item_id, str) or not item_id or item_id in seen:
            raise ArkCleanroomError("observation_dimension", f"{where}[{index}] has invalid/duplicate id")
        seen.add(item_id)
        if outcome == pass_value:
            passed += 1
        elif outcome == fail_value:
            failed += 1
        elif outcome == "unverified":
            unassessed += 1
        else:
            raise ArkCleanroomError("observation_outcome", f"{where}[{index}] has unsupported outcome")
    assessed = passed + failed
    metric = _metric(passed, assessed, fail=failed > 0)
    return {**metric, "passed": passed, "failed": failed, "unassessed": unassessed}


def _validate_object_row(row: Any, where: str) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != {"object_id", "size_bytes", "bytes_sha256"}:
        raise ArkCleanroomError("transport_object", f"{where} has invalid fields")
    object_id = row["object_id"]
    bytes_sha = row["bytes_sha256"]
    size = row["size_bytes"]
    if (
        not isinstance(object_id, str)
        or not object_id.startswith("sha256:")
        or len(object_id) != 71
        or any(ch not in "0123456789abcdef" for ch in object_id[7:])
    ):
        raise ArkCleanroomError("transport_object_id", f"{where}.object_id is invalid")
    if bytes_sha != object_id:
        raise ArkCleanroomError("transport_object_hash", f"{where}.bytes_sha256 must equal object_id")
    if type(size) is not int or size < 0 or size > MAX_OBJECT_BYTES:
        raise ArkCleanroomError("transport_object_size", f"{where}.size_bytes is invalid")
    return {"object_id": object_id, "size_bytes": size, "bytes_sha256": bytes_sha}


def _inventory_objects(root: Path) -> dict[str, tuple[int, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise ArkCleanroomError("object_root", "objects root must be a non-symlink directory")
    inventory: dict[str, tuple[int, Path]] = {}
    count = 0
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix().encode("utf-8")):
        if path.is_symlink():
            raise ArkCleanroomError("object_symlink", "objects root contains a symlink")
        count += 1
        if count > MAX_OBJECTS:
            raise ArkCleanroomError("object_count", "objects root exceeds file limit")
        size = path.stat().st_size
        if size > MAX_OBJECT_BYTES:
            raise ArkCleanroomError("object_size", "portable object exceeds size limit")
        digest = "sha256:" + sha256_file(path)
        if digest in inventory:
            raise ArkCleanroomError("object_duplicate", f"duplicate object bytes found for {digest}")
        inventory[digest] = (size, path)
    return inventory


def evaluate_clean_room(
    observation_path: Path,
    objects_root: Path,
    *,
    ark_trial_id: str,
    record_class: str = "synthetic-conformance",
    execution_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    if ark_trial_id not in TRIALS:
        raise ArkCleanroomError("ark_trial", "ARK trial must be P0, P1, P2, or P3")
    if record_class not in RECORD_CLASSES:
        raise ArkCleanroomError("record_class", "unsupported clean-room record class")
    if record_class == "synthetic-conformance" and execution_receipt_sha256 is not None:
        raise ArkCleanroomError("synthetic_execution_claim", "synthetic conformance must not carry an execution receipt")
    if record_class == "externally-observed-clean-room":
        if (
            not isinstance(execution_receipt_sha256, str)
            or len(execution_receipt_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in execution_receipt_sha256)
        ):
            raise ArkCleanroomError("execution_receipt", "externally observed runs require a SHA-256 execution receipt")

    observation = _load_object(observation_path)
    _require_keys(
        observation,
        {
            "protocol",
            "schema_version",
            "trial_id",
            "assessment_authority",
            "route",
            "style_fidelity",
            "factual_accuracy",
            "historical_reconstruction",
            "clean_room",
            "transports",
            "negative_space",
            "boundaries",
        },
        "observation",
    )
    if observation["protocol"] != OBSERVATION_PROTOCOL or observation["schema_version"] != SCHEMA_VERSION:
        raise ArkCleanroomError("observation_protocol", "unsupported ARK/THOTH observation protocol/version")
    if observation["assessment_authority"] != "explicit-observations-not-automatic-truth":
        raise ArkCleanroomError("assessment_authority", "observation authority boundary mismatch")

    route = observation["route"]
    if not isinstance(route, dict):
        raise ArkCleanroomError("route_shape", "route observation must be an object")
    _require_keys(route, {"selected_role_ids", "required_role_ids", "justified_role_ids"}, "route")
    selected = _unique_strings(route["selected_role_ids"], "route.selected_role_ids")
    required = _unique_strings(route["required_role_ids"], "route.required_role_ids")
    justified = _unique_strings(route["justified_role_ids"], "route.justified_role_ids")
    selected_set = set(selected)
    required_covered = len(set(required) & selected_set)
    justified_selected = len(set(justified) & selected_set)
    route_sufficiency = _metric(required_covered, len(required), fail=required_covered != len(required))
    route_minimality = _metric(justified_selected, len(selected), fail=justified_selected != len(selected))

    style = observation["style_fidelity"]
    factual = observation["factual_accuracy"]
    historical = observation["historical_reconstruction"]
    if not isinstance(style, dict) or set(style) != {"obligations"}:
        raise ArkCleanroomError("style_shape", "style_fidelity must contain obligations")
    if not isinstance(factual, dict) or set(factual) != {"claims"}:
        raise ArkCleanroomError("factual_shape", "factual_accuracy must contain claims")
    if not isinstance(historical, dict) or set(historical) != {"obligations"}:
        raise ArkCleanroomError("historical_shape", "historical_reconstruction must contain obligations")
    style_metric = _outcome_metric(style["obligations"], pass_value="pass", fail_value="fail", where="style_fidelity.obligations")
    factual_metric = _outcome_metric(factual["claims"], pass_value="correct", fail_value="incorrect", where="factual_accuracy.claims")
    historical_metric = _outcome_metric(historical["obligations"], pass_value="covered", fail_value="missing", where="historical_reconstruction.obligations")

    clean_room = observation["clean_room"]
    expected_clean_room = {
        "portable_inputs_only": True,
        "private_source_repository_access": False,
        "private_context_connector_access": False,
        "hidden_provider_memory_dependency": False,
    }
    if clean_room != expected_clean_room:
        raise ArkCleanroomError("clean_room_boundary", "clean-room requirements are not satisfied")

    transports = observation["transports"]
    if not isinstance(transports, list) or len(transports) != len(TRANSPORT_PROFILES):
        raise ArkCleanroomError("transport_profiles", "all four transport profiles are required")
    transport_objects: dict[str, tuple[dict[str, Any], ...]] = {}
    for index, transport in enumerate(transports):
        if not isinstance(transport, dict) or set(transport) != {"id", "objects"}:
            raise ArkCleanroomError("transport_shape", f"transports[{index}] has invalid fields")
        transport_id = transport["id"]
        if transport_id not in TRANSPORT_PROFILES or transport_id in transport_objects:
            raise ArkCleanroomError("transport_id", f"transports[{index}] has invalid/duplicate id")
        rows = transport["objects"]
        if not isinstance(rows, list) or len(rows) > MAX_OBJECTS:
            raise ArkCleanroomError("transport_objects", f"transports[{index}].objects is invalid")
        normalized = tuple(sorted((_validate_object_row(row, f"transports[{index}].objects") for row in rows), key=lambda row: row["object_id"]))
        transport_objects[transport_id] = normalized
    baseline = transport_objects[TRANSPORT_PROFILES[0]]
    if any(transport_objects[transport_id] != baseline for transport_id in TRANSPORT_PROFILES[1:]):
        raise ArkCleanroomError("transport_equivalence", "transport profiles do not expose identical object identities")

    inventory = _inventory_objects(objects_root)
    verified_objects: list[dict[str, Any]] = []
    for row in baseline:
        observed = inventory.get(row["object_id"])
        if observed is None:
            raise ArkCleanroomError("object_missing", f"portable object is missing: {row['object_id']}")
        size, _path = observed
        if size != row["size_bytes"]:
            raise ArkCleanroomError("object_size_mismatch", f"portable object size mismatch: {row['object_id']}")
        verified_objects.append(dict(row))

    negative_space = observation["negative_space"]
    if not isinstance(negative_space, dict) or set(negative_space) != set(NEGATIVE_SPACE_CHECKS):
        raise ArkCleanroomError("negative_space_shape", "negative-space checks mismatch")
    if any(type(negative_space[key]) is not bool for key in NEGATIVE_SPACE_CHECKS):
        raise ArkCleanroomError("negative_space_type", "negative-space checks must be boolean")
    negative_space_pass = not any(negative_space.values())

    boundaries = observation["boundaries"]
    if not isinstance(boundaries, list) or any(not isinstance(item, str) for item in boundaries):
        raise ArkCleanroomError("observation_boundaries", "observation boundaries must be strings")
    required_thoth_boundaries = {
        "STYLE_FIDELITY != FACTUAL_ACCURACY != PHYSICAL_TRUTH",
        "ROUTE_SUFFICIENCY != ROUTE_MINIMALITY",
        "HISTORICAL_COVERAGE != HISTORICAL_TRUTH",
        "TRANSPORT_EQUIVALENCE != AUTHORITY",
        "CLEAN_ROOM_SUCCESS != PRIVATE_SOURCE_ACCESS",
        "MEASURED_OBSERVATION != AUTOMATIC_TRUTH",
        "AGGREGATE_SCORE = FORBIDDEN",
    }
    if not required_thoth_boundaries.issubset(boundaries):
        raise ArkCleanroomError("observation_boundary_missing", "observation is missing a required THOTH boundary")

    metrics = [
        {"id": "route_sufficiency", **route_sufficiency},
        {"id": "route_minimality", **route_minimality},
        {"id": "style_fidelity", **style_metric},
        {"id": "factual_accuracy", **factual_metric},
        {"id": "historical_reconstruction_coverage", **historical_metric},
    ]
    conformance_pass = (
        all(metric["status"] != "fail" for metric in metrics)
        and negative_space_pass
        and clean_room == expected_clean_room
    )
    body = {
        "protocol": RECEIPT_PROTOCOL,
        "schema_version": SCHEMA_VERSION,
        "authority": "measurement-contract-only",
        "record_class": record_class,
        "ark_contract_protocol": ARK_CONTRACT_PROTOCOL,
        "thoth_policy_protocol": THOTH_POLICY_PROTOCOL,
        "ark_trial_id": ark_trial_id,
        "observation_trial_id": observation["trial_id"],
        "observation_sha256": sha256_file(observation_path),
        "execution_receipt_sha256": execution_receipt_sha256,
        "model_execution_claimed": record_class == "externally-observed-clean-room",
        "t5_ai_reconstruction_implemented": False,
        "metrics": metrics,
        "clean_room": {**expected_clean_room, "pass": True},
        "transport_equivalence": {
            "profiles": list(TRANSPORT_PROFILES),
            "objects": verified_objects,
            "pass": True,
        },
        "negative_space": {**negative_space, "pass": negative_space_pass},
        "conformance_pass": conformance_pass,
        "aggregate_score_emitted": False,
        "boundaries": list(BOUNDARIES),
    }
    return {**body, "receipt_sha256": sha256_bytes(canonical_json_bytes(body))}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a QSOL-ARK/THOTH clean-room observation without claiming model continuity")
    parser.add_argument("observation", type=Path)
    parser.add_argument("objects_root", type=Path)
    parser.add_argument("--ark-trial", choices=sorted(TRIALS), required=True)
    parser.add_argument("--record-class", choices=sorted(RECORD_CLASSES), default="synthetic-conformance")
    parser.add_argument("--execution-receipt-sha256", default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    receipt = evaluate_clean_room(
        args.observation,
        args.objects_root,
        ark_trial_id=args.ark_trial,
        record_class=args.record_class,
        execution_receipt_sha256=args.execution_receipt_sha256,
    )
    encoded = canonical_json_bytes(receipt)
    if args.output is None:
        import sys

        sys.stdout.buffer.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
