#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

CALLER = """name: Python static review

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  static-review:
    uses: Certropy-Technology/.github/.github/workflows/python-static-review.yml@main
    with:
      config-path: .github/static-review.json
      python-version: \"3.12\"
"""


@dataclass(frozen=True)
class Repository:
    name: str
    default_branch: str
    private: bool


class GitHub:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "certropy-static-review-bootstrap/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(
                f"GitHub {method} {path} failed: {exc.code} {detail}"
            ) from exc


def list_repositories(api: GitHub, organization: str) -> list[Repository]:
    result: list[Repository] = []
    page = 1
    while True:
        items = api.request(
            "GET",
            f"/orgs/{organization}/repos?type=all&per_page=100&page={page}",
        )
        if not items:
            break
        for item in items:
            if (
                item.get("archived")
                or item.get("fork")
                or not item.get("default_branch")
            ):
                continue
            result.append(
                Repository(
                    name=item["name"],
                    default_branch=item["default_branch"],
                    private=bool(item["private"]),
                )
            )
        page += 1
    return result


def tree(api: GitHub, organization: str, repository: Repository) -> set[str]:
    branch = urllib.parse.quote(repository.default_branch, safe="")
    data = api.request(
        "GET",
        f"/repos/{organization}/{repository.name}/git/trees/{branch}?recursive=1",
    )
    return {
        item["path"]
        for item in data.get("tree", [])
        if item.get("type") == "blob" and isinstance(item.get("path"), str)
    }


def infer_config(paths: set[str]) -> dict[str, Any] | None:
    python_files = sorted(path for path in paths if path.endswith(".py"))
    if not python_files:
        return None

    if "harbor-secure-runner/pyproject.toml" in paths:
        project_root = "harbor-secure-runner"
        install_profile = (
            "harbor-020"
            if "harbor_runtime/kind_environment.py" in paths
            else "editable"
        )
    elif "pyproject.toml" in paths or "setup.py" in paths or "setup.cfg" in paths:
        project_root = "."
        install_profile = "editable"
    else:
        project_root = "."
        install_profile = "none"

    ruff_candidates = [
        "src",
        "tests",
        "harbor-secure-runner/src",
        "harbor-secure-runner/tests",
        "harbor_runtime",
        "harbor-conformance",
        "benchmarks",
    ]
    ruff_paths = [
        candidate
        for candidate in ruff_candidates
        if any(path == candidate or path.startswith(candidate + "/") for path in paths)
    ]
    if not ruff_paths:
        ruff_paths = [python_files[0]]

    test_candidates = ["tests", "harbor-secure-runner/tests"]
    pytest_paths = [
        candidate
        for candidate in test_candidates
        if any(path.startswith(candidate + "/") for path in paths)
    ]
    if not pytest_paths:
        pytest_paths = [python_files[0]]

    mypy_candidates = ["src", "harbor-secure-runner/src/harbor_secure"]
    mypy_paths = [
        candidate
        for candidate in mypy_candidates
        if any(path.startswith(candidate + "/") for path in paths)
    ]
    if not mypy_paths:
        mypy_paths = [python_files[0]]

    requirements = sorted(
        path
        for path in paths
        if path.rsplit("/", 1)[-1].startswith("requirements") and path.endswith(".txt")
    )
    return {
        "schema_version": 1,
        "project_root": project_root,
        "install_profile": install_profile,
        "ruff_paths": ruff_paths,
        "ruff_format": True,
        "mypy_paths": mypy_paths,
        "pytest_paths": pytest_paths,
        "audit_requirements": requirements,
    }


def content(
    api: GitHub, organization: str, name: str, path: str, ref: str
) -> dict[str, Any] | None:
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    try:
        return api.request(
            "GET",
            f"/repos/{organization}/{name}/contents/{encoded_path}?ref={encoded_ref}",
        )
    except RuntimeError as exc:
        if " 404 " in str(exc):
            return None
        raise


def put_content(
    api: GitHub,
    organization: str,
    name: str,
    path: str,
    branch: str,
    value: str,
) -> None:
    existing = content(api, organization, name, path, branch)
    body: dict[str, Any] = {
        "message": "Add organization static review configuration",
        "content": base64.b64encode(value.encode()).decode(),
        "branch": branch,
    }
    if existing:
        body["sha"] = existing["sha"]
    encoded_path = urllib.parse.quote(path, safe="/")
    api.request("PUT", f"/repos/{organization}/{name}/contents/{encoded_path}", body)


def open_bootstrap_pr(
    api: GitHub,
    organization: str,
    repository: Repository,
    config: dict[str, Any],
) -> str:
    branch = "automation/static-review"
    repo_path = f"/repos/{organization}/{repository.name}"
    default_ref = api.request(
        "GET",
        repo_path
        + "/git/ref/heads/"
        + urllib.parse.quote(repository.default_branch, safe=""),
    )
    try:
        api.request(
            "POST",
            repo_path + "/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": default_ref["object"]["sha"]},
        )
    except RuntimeError as exc:
        if " 422 " not in str(exc):
            raise

    put_content(
        api,
        organization,
        repository.name,
        ".github/workflows/static-review.yml",
        branch,
        CALLER,
    )
    put_content(
        api,
        organization,
        repository.name,
        ".github/static-review.json",
        branch,
        json.dumps(config, indent=2, sort_keys=True) + "\n",
    )
    existing = api.request(
        "GET",
        repo_path
        + "/pulls?state=open&head="
        + urllib.parse.quote(f"{organization}:{branch}", safe="")
        + "&base="
        + urllib.parse.quote(repository.default_branch, safe=""),
    )
    if existing:
        return existing[0]["html_url"]
    pull = api.request(
        "POST",
        repo_path + "/pulls",
        {
            "title": "Add organization Python static review",
            "head": branch,
            "base": repository.default_branch,
            "body": (
                "This PR was generated by Certropy-Technology/.github. It adds the "
                "shared Ruff, mypy, pytest, and pip-audit review without repository secrets."
            ),
        },
    )
    return pull["html_url"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--repositories", default="")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise SystemExit("GH_TOKEN is required")
    selected = {item.strip() for item in args.repositories.split(",") if item.strip()}
    api = GitHub(token)
    for repository in list_repositories(api, args.organization):
        if repository.name == ".github" or (
            selected and repository.name not in selected
        ):
            continue
        paths = tree(api, args.organization, repository)
        if ".github/workflows/static-review.yml" in paths:
            print(f"skip {repository.name}: already configured")
            continue
        config = infer_config(paths)
        if config is None:
            print(f"skip {repository.name}: no Python files")
            continue
        url = open_bootstrap_pr(api, args.organization, repository, config)
        print(f"onboard {repository.name}: {url}")


if __name__ == "__main__":
    main()
