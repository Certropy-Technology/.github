#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
INSTALL_PROFILES = {
    "none": [],
    "editable": ["editable"],
    "harbor-020": ["harbor>=0.20.0,<0.21.0", "editable"],
}


def fail(message: str) -> None:
    raise SystemExit(f"static-review: {message}")


def relative_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must contain non-empty relative paths")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        fail(f"{field} contains an unsafe path: {value!r}")
    return path.as_posix()


def path_list(
    config: dict[str, Any], field: str, *, required: bool = True
) -> list[str]:
    value = config.get(field, [])
    if not isinstance(value, list):
        fail(f"{field} must be an array")
    result = [relative_path(item, field=field) for item in value]
    if required and not result:
        fail(f"{field} must not be empty")
    return result


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        fail(f"{path} must use schema_version {SCHEMA_VERSION}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".github/static-review.json")
    args = parser.parse_args()

    config_path = Path(relative_path(args.config, field="config"))
    config = load_config(config_path)
    project_root = relative_path(config.get("project_root", "."), field="project_root")
    install_profile = config.get("install_profile", "editable")
    if install_profile not in INSTALL_PROFILES:
        fail(f"install_profile must be one of {', '.join(sorted(INSTALL_PROFILES))}")

    ruff_paths = path_list(config, "ruff_paths")
    mypy_paths = path_list(config, "mypy_paths")
    pytest_paths = path_list(config, "pytest_paths")
    audit_files = path_list(config, "audit_requirements", required=False)

    for path in [project_root, *ruff_paths, *mypy_paths, *pytest_paths, *audit_files]:
        if path != "." and not Path(path).exists():
            fail(f"configured path does not exist: {path}")

    profile = INSTALL_PROFILES[install_profile]
    for item in profile:
        if item == "editable":
            run([sys.executable, "-m", "pip", "install", "-e", project_root])
        else:
            run([sys.executable, "-m", "pip", "install", item])

    run(["ruff", "check", *ruff_paths])
    run(["ruff", "format", "--check", *ruff_paths])
    run(["mypy", "--ignore-missing-imports", "--follow-imports", "skip", *mypy_paths])
    run(["pytest", "-q", *pytest_paths])

    if audit_files:
        for requirements in audit_files:
            run(
                [
                    "pip-audit",
                    "--strict",
                    "--progress-spinner",
                    "off",
                    "-r",
                    requirements,
                ]
            )
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8"
        ) as handle:
            handle.write("# This project declares no requirements file.\n")
            handle.flush()
            run(
                [
                    "pip-audit",
                    "--strict",
                    "--progress-spinner",
                    "off",
                    "-r",
                    handle.name,
                ]
            )


if __name__ == "__main__":
    main()
