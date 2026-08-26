# Certropy Technology GitHub automation

This repository owns the reusable static-review workflow used by organization
repositories and the bootstrap automation that opens onboarding pull requests.

## Shared Python review

Repositories opt in with two files:

- `.github/workflows/static-review.yml` calls the shared workflow;
- `.github/static-review.json` declares project-relative paths and one fixed
  installation profile. It may also select a repository Ruff configuration by
  relative path; arbitrary shell commands are never accepted.

The shared workflow runs Ruff lint and formatting checks, mypy, pytest, and
pip-audit. Repository configuration cannot inject shell commands.

Older repositories may temporarily set `ruff_format` to `false` while an
explicit formatting-only PR establishes their baseline. Ruff lint, mypy,
pytest, and pip-audit remain mandatory.

## Automatic onboarding

`bootstrap-static-review.yml` scans organization repositories daily and can be
started manually. It opens a PR when it finds a Python repository without the
shared caller and configuration pair. A repository with an older standalone
`static-review.yml` is migrated to the shared workflow through the same PR.

Configure an Actions secret named `ORG_BOOTSTRAP_TOKEN` in this repository.
Use a fine-grained token limited to the target organization with:

- Contents: read and write;
- Pull requests: read and write;
- Workflows: read and write, when required by the selected token type.

The workflow safely does nothing when the secret is absent. Organization-wide
branch protection is a separate GitHub Team/Enterprise setting.
