# Argus PII Guard - Validation & Testing Pipeline Protocol

> **MANDATORY INSTRUCTION FOR ALL AI CODING ASSISTANTS & DEVELOPERS**
> No feature, bug fix, or refactor may be marked as completed until the validation criteria outlined in this document are strictly satisfied.

---

## 🎯 Core Requirements & Quality Gates

1. **85% Minimum Code Coverage**:
   - Every modified or newly added module in `backend/` must maintain at least **85% line coverage**.
   - Running the test suite with coverage enforcement must pass:
     ```bash
     pytest --cov=backend --cov-report=term-missing --cov-fail-under=85
     ```

2. **Zero Regressions**:
   - All existing tests in `tests/` must pass without failures or unhandled exceptions.
   - Any modification to business logic (caching, scanning, text extraction, API endpoints) must retain backwards compatibility or update tests deliberately with documented reasoning.

3. **New Feature Test Obligation**:
   - Whenever a new feature or file format is introduced, corresponding unit tests and integration tests **must be added** to `tests/`.
   - Tests must cover:
     - Happy path (standard expected inputs).
     - Edge cases (corrupted files, empty files, missing keys, special characters).
     - Error handling and graceful fallbacks.

---

## 🧪 Test Architecture & Structure

The test suite is organized under `tests/`:

```
tests/
├── conftest.py          # Shared fixtures, temporary directory mocks, and state resets
├── test_state.py        # Unit tests for settings, results, and scan caching persistence
├── test_scanner.py      # Unit tests for PII regex patterns, file extractors (PDF/Word/Excel), and RAM auto-config
└── test_api.py          # Integration tests for Api bridge methods (delete, mark_ok, preview, scan)
```

---

## 📋 Standard Validation Procedure Before Declaring Completion

Before presenting any feature as complete to the user, the agent must execute the following 3-step verification process:

### Step 1: Syntax & Bytecode Compilation
```bash
python -m py_compile backend/main.py backend/scanner.py backend/state.py
```

### Step 2: Full Test Suite Execution
```bash
pytest tests/ -v
```

### Step 3: Coverage Gate Verification (>= 85%)
```bash
pytest --cov=backend --cov-report=term-missing --cov-fail-under=85
```

---

## 🛡️ Key Testing Guidelines for Specific Modules

### 1. File Parsers & Extractors (`scanner.py`)
- Mock or create temporary in-memory sample files for `.pdf`, `.docx`, `.xlsx`, `.pptx`, `.txt`, `.csv`, `.json`, etc.
- Verify that text extraction handles empty files and missing libraries gracefully without crashing the UI thread.

### 2. State & Cache System (`state.py`)
- Use isolated temporary directories for test artifacts so production `cache.json`, `settings.json`, and `results.json` are never overwritten during tests.

### 3. PyWebView API Layer (`main.py`)
- Verify that methods called from the JavaScript frontend (`mark_file_ok`, `delete_files`, `verify_file`, `get_image_base64`) return the exact JSON serializable dictionaries expected by `script.js`.
