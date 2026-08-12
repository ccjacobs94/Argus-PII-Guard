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

## Mandatory Onboarding Tour Synchronization Rule

4. **Onboarding Tour Maintenance**:
   - Whenever any new feature, UI view, setting, or scanner capability is added or significantly modified in Argus PII Guard, you MUST update the `ArgusTourEngine` steps in `frontend/script.js` and corresponding tour elements in `frontend/index.html`.
   - Ensure the interactive product tour accurately introduces users to all new and updated features.

