# Development resources

This page records the resources needed to operate the repository workflow. It keeps access requests separate from scientific inputs and makes the boundary between pull-request checks and longer research runs explicit.

## Available now

| Resource | Current use | Boundary |
| --- | --- | --- |
| GitHub repository administration | Rulesets, Actions, issue and pull-request management | The active account is used for repository maintenance. It should not be the only scientific approver once the review gate is enabled. |
| GitHub Actions `ubuntu-24.04` CPU runners | Archive replay, molecular CPU regression, and pre-commit | The current response gate completed in about two minutes. It uses public pinned source and wheel inputs. |
| Pinned GQC and PySCF source records | Reproducible source acquisition and local scientific runs | Full source trees remain local under `_references/`. The repository stores locks, inventories, and evidence. |
| n2 and n5 environments | GPU, Slurm, and cross-node validation | These are research resources and are not a hidden dependency of the pull-request gate. |

## Needed for independent review

Provide a second GitHub username for scientific review. Add that account as a collaborator with the smallest role that can submit a pull-request review. Then add it to `.github/CODEOWNERS` for response code, scientific protocols, and published evidence. The repository ruleset can then require one approval.

The account must use its own GitHub login. Do not share passwords or personal access tokens in chat, commits, workflow files, or Actions variables. If automation later needs GitHub API access, create a narrowly scoped token as a repository secret and record its purpose and rotation owner in the issue that introduced it.

## Optional future resources

| Resource | When it becomes necessary | Current decision |
| --- | --- | --- |
| Hosted or self-hosted GPU runner | A GPU result becomes a merge-blocking acceptance criterion | Keep GPU work in n2/n5 research runs until a reproducible runner, cost limit, and cleanup policy are agreed. |
| Artifact storage | Raw scheduler logs or large profiling streams need retention beyond Actions artifacts | Keep compact accepted evidence in Git and transient runs in `.work/` or CI artifacts. Add storage only with a retention and checksum contract. |
| Private data access | A future source is not publicly downloadable | Add a read-only secret only after its license, provenance, and reproducible fallback are documented. |

## Current control points

- `.github/workflows/response.yml` is the executable pull-request gate.
- `.pre-commit-config.yaml` is the local and CI hook contract.
- `CONTRIBUTING.md` defines the issue, branch, evidence, and merge procedure.
- The GitHub `main-validation` ruleset is the external merge control. Its required status is `Response validation gate`.
