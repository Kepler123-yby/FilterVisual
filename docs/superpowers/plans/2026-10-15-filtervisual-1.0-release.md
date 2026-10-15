# FilterVisual 1.0 Release Implementation Plan

> **For agentic workers:** Execute the independent reviews in parallel, reproduce concrete findings with targeted tests, then perform one final integrated verification before publishing.

**Goal:** Audit the accepted application and its documentation, fix confirmed defects, and publish the reviewed commit as the annotated Git tag `1.0`.

**Architecture:** Keep the existing Python numerical service and React workbench. Independent reviewers cover numerical kernels/models, simulation/evaluation, and documentation. The release owner checks configuration, storage/API boundaries, frontend data flow, versions, and the final publication.

**Tech Stack:** Python 3.10–3.13, NumPy/SciPy, FastAPI, React/TypeScript, Vite, pytest, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-15-filtervisual-design.md`, plus the user's accepted current implementation and explicit request for a self-reviewed `1.0` release.

## Global Constraints

- Preserve the accepted feature scope and user changes, including `bee9016` and signed motion.
- Keep configuration `schema_version=1`; release version is `1.0.0`, requested Git tag is `1.0`.
- Preserve independent measurement/filter frequencies and post-correction forecast branches.
- Keep true observation noise distinct from each filter's assumed R.
- Publish only after verification; never move or overwrite an existing release tag.
- Record actual test outcomes and remaining limitations, distinguishing historical benchmarks from current checks.

## Review Focus

- Signed motion, zero crossings, wrapped angular residuals, and covariance dimensions.
- Forecast branches with missing observations, noninteger leads, and unavailable future truth.
- Custom/formula model errors, incompatible metadata, and partially failing filter instances.
- API/storage validation, immutable result/config identity, canceled or timed-out analysis jobs.
- Documentation commands, parameter units/meaning, exported versions, and frontend round-trip fidelity.

## Task 1: Audit and repair confirmed logic defects

**Files:** Existing `backend/src/filtervisual`, `web/src`, corresponding test files, `README.md`, and user-facing `docs/*.md`.

**Interfaces:** Retain the version 1 configuration and API contracts. Reviewers report cross-owned issues to the release owner before editing.

- [x] Read the implementation and compare against documented behavior.
- [x] For each confirmed defect, add a focused test that reproduces it and observe failure.
- [x] Apply the smallest correction and pass its focused regression.
- [x] Correct contradictory or outdated user documentation.
- [x] Review the integrated changes independently.

## Task 2: Prepare and verify the release

**Files:** `backend/pyproject.toml`, `backend/src/filtervisual/__init__.py`, service and manifest version references, `web/package.json`, `web/package-lock.json`, `web/src/api/openapi.json`, `docs/releases/1.0.md`, `docs/acceptance.md`.

**Interfaces:** The backend package, health endpoint, OpenAPI info, and newly created artifact manifests report `1.0.0`. Existing stored manifests remain unchanged.

- [x] Centralize backend runtime version references and set package versions to `1.0.0`.
- [x] Regenerate OpenAPI and check frontend generation for unintended contract changes.
- [x] Run the complete backend and frontend suites, production build, package dependency checks, and browser E2E against an isolated data directory.
- [x] Verify a production entry point and actual JSON/CSV/NPZ export with the release version.
- [x] Record actual verification results, fixes, and product limitations in the release notes and acceptance record.
- [ ] Commit the reviewed release after the completed formatting/diff checks.

## Task 3: Publish tag `1.0`

**Files:** Git release commit and annotated tag only.

**Interfaces:** `origin/main` contains the release commit; remote `refs/tags/1.0` peels to that same commit.

- [x] Fetch remote main and tags; resolve any concurrent changes without discarding user work.
- [ ] Create annotated tag `1.0` on the verified commit if the name is unused.
- [ ] Push the branch and tag without force, preferably atomically.
- [ ] Verify the remote branch and peeled tag match the local release commit.
- [ ] Return the tag link, verification summary, and any material remaining limitations.
