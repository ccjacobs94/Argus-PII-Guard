# Project-Scoped Agent Guidelines for Argus PII Guard

## Mandatory Validation & Testing Rules

1. **Test-Driven Delivery**:
   - Do NOT mark any feature or bugfix as complete without running the validation suite:
     ```bash
     pytest --cov=backend --cov-report=term-missing --cov-fail-under=85
     ```
2. **Coverage Threshold**:
   - Code coverage across the `backend/` package must remain at **85% or higher**.
   - Any new methods, branches, or file extractors must include comprehensive test cases in `tests/`.

3. **Zero Regression Policy**:
   - All tests in `tests/` must pass cleanly before ending any task.
   - For more details, consult `VALIDATION_PIPELINE.md`.

## Mandatory Onboarding Tour & Feature Demo Synchronization Rule

4. **Onboarding Tour & Feature Demo Maintenance**:
   - Whenever any new feature, UI view, setting, or scanner capability is added or significantly modified in Argus PII Guard, you MUST update the `ArgusTourEngine` steps in `frontend/script.js` and corresponding tour elements in `frontend/index.html`.
   - Ensure the interactive product tour/demo accurately introduces users to all new and updated features before changes reach the `main` branch.
   - For full pipeline validation details, consult `VALIDATION_PIPELINE.md`.

## Mandatory Git Branching & Isolation Rules

5. **Feature Branch Isolation**:
   - Every time a new thread or task begins that modifies code in any way, a dedicated feature branch MUST be created and checked out before making code changes (e.g., `git checkout -b feature/<feature-name>`).
   - Branch naming format: `feature/<feature-name>` (e.g., `feature/workflow-validation`, `feature/pdf-parser-fix`).
   - Direct commits and modifications to `main` are strictly prohibited to prevent accidental overwrites or regressions on the production branch.

## Mandatory Repository Hygiene & Gitignore Auditing Rule

6. **Gitignore & Artifact Auditing**:
   - Whenever any new feature, build pipeline, download mechanism, test runner, dependency, or runtime cache is introduced or modified, audit the repository file structure and update `.gitignore` as needed.
   - Ensure local state files (e.g. temporary model downloads `*.tmp`, test coverage reports, secrets `.env.*`, build targets, OS/editor metadata) are never accidentally tracked or committed.



