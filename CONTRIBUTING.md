# Development workflow

This repository uses the GenerativeQC-style issue, branch, validation, and pull-request workflow. The workflow protects the scientific identity of a result as well as the source code that produced it.

## Start from an issue

An issue states the question, inputs, dependencies, expected artifacts, acceptance commands, and remaining boundaries. A result is not accepted because a script ran once. The issue must say which evidence distinguishes a solved target from an approximation, a rejected target, an unavailable reference, or a failed execution.

## Work in an isolated branch

Use a short-lived branch with the issue number, for example `codex/13-response-ci`. Keep unrelated work in a separate worktree. Commit one coherent change at a time and keep generated evidence tied to the source and input identities that produced it.

Before opening a pull request, run the narrow checks for the affected entry point and then the full archive or science tier when the change can affect published records. Keep the command logs and result paths in the pull request description. Do not commit scheduler logs, compiler products, temporary databases, or local checkouts.

## Open a pull request

The pull request describes the scientific identity, independent reference, numerical gates, failure behavior, measured work, persistent assets, and negative results. Update current documentation in the same change. Put durable reasoning and rejected alternatives in the research decision records. A generated inventory supports provenance, but it does not replace a human review of the affected behavior.

The required `Response validation gate` must pass before merge. It includes the archive replay, the molecular CPU regression, and the pre-commit hooks. Changes that alter a method, state, response, precision, or cost contract need an independent reference and a follow-up issue when the current evidence is incomplete.

## Merge and retain evidence

`main` accepts pull requests through the repository ruleset and uses squash merges. Review the final diff after generated files are updated. Retain compact scientific records with source, input, environment, commands, gates, failures, and costs. Keep transient runs in `.work/` or CI artifacts. Do not publish a release or push a tag without explicit authorization for that operation.

The current research queue and source evidence remain under `handoff/gqcdataset_codex_goal/research/`. The response check entry point is `scripts/check_response_ci.py`.
