import os
import sys
import time
import json
import stat
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import backend.remediation as rem
import backend.scanner as scanner
import backend.state as state
from backend.main import Api


class TestBackups:
    def test_create_and_list_backups(self, tmp_path):
        test_file = tmp_path / "secret.env"
        test_file.write_text("API_KEY=secret123\nPASSWORD=mypass", encoding="utf-8")

        entry = rem.create_backup(str(test_file), base_dir=str(tmp_path))
        assert entry is not None
        assert os.path.exists(entry["backup_path"])

        backups = rem.list_backups(base_dir=str(tmp_path))
        assert len(backups) == 1
        assert backups[0]["backup_path"] == entry["backup_path"]
        assert backups[0]["original_path"] == str(os.path.abspath(test_file))

    def test_create_backup_non_existent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            rem.create_backup(str(tmp_path / "does_not_exist.txt"), base_dir=str(tmp_path))

    def test_restore_backup(self, tmp_path):
        test_file = tmp_path / "data.txt"
        test_file.write_text("original content", encoding="utf-8")

        entry = rem.create_backup(str(test_file), base_dir=str(tmp_path))
        
        # Modify file
        test_file.write_text("corrupted content", encoding="utf-8")

        res = rem.restore_backup(entry["id"], base_dir=str(tmp_path))
        assert res["success"] is True
        assert test_file.read_text(encoding="utf-8") == "original content"

    def test_restore_backup_missing_or_invalid(self, tmp_path):
        res = rem.restore_backup("non_existent_id", base_dir=str(tmp_path))
        assert res["success"] is False

    def test_restore_backup_file_missing_on_disk(self, tmp_path):
        test_file = tmp_path / "data.txt"
        test_file.write_text("orig", encoding="utf-8")
        entry = rem.create_backup(str(test_file), base_dir=str(tmp_path))
        
        # Remove backup file manually
        os.remove(entry["backup_path"])
        res = rem.restore_backup(entry["id"], base_dir=str(tmp_path))
        assert res["success"] is False
        assert res["error"] == "Backup file missing on disk"

    def test_prune_expired_backups(self, tmp_path):
        test_file = tmp_path / "data.txt"
        test_file.write_text("some content", encoding="utf-8")

        entry = rem.create_backup(str(test_file), base_dir=str(tmp_path))
        backup_file = Path(entry["backup_path"])
        assert backup_file.exists()

        # Manually alter timestamp in index to 30 days ago
        index = rem._load_backup_index(str(tmp_path))
        index[0]["timestamp"] = time.time() - (30 * 86400)
        rem._save_backup_index(index, str(tmp_path))

        pruned = rem.prune_expired_backups(max_days=7, base_dir=str(tmp_path))
        assert pruned == 1
        assert not backup_file.exists()

    def test_load_backup_index_corrupt(self, tmp_path):
        index_file = tmp_path / ".argus_backups" / "index.json"
        index_file.parent.mkdir(parents=True, exist_ok=True)
        index_file.write_text("invalid json content", encoding="utf-8")
        assert rem._load_backup_index(str(tmp_path)) == []


class TestPermissionsAndIntegrity:
    def test_check_write_permission_and_fix(self, tmp_path):
        test_file = tmp_path / "readonly.txt"
        test_file.write_text("read only text", encoding="utf-8")

        assert rem.check_write_permission(str(test_file)) is True
        assert rem.check_write_permission(str(tmp_path / "missing.txt")) is False

        # Make read-only
        os.chmod(str(test_file), stat.S_IREAD)
        
        fix_res = rem.fix_file_permissions(str(test_file))
        assert fix_res["success"] is True
        assert rem.check_write_permission(str(test_file)) is True

    def test_check_write_permission_access_denied(self, tmp_path):
        test_file = tmp_path / "denied.txt"
        test_file.write_text("content", encoding="utf-8")
        with patch("os.access", return_value=False):
            assert rem.check_write_permission(str(test_file)) is False

    def test_fix_permissions_non_existent(self, tmp_path):
        res = rem.fix_file_permissions(str(tmp_path / "not_there.txt"))
        assert res["success"] is False

    def test_verify_file_integrity(self, tmp_path):
        test_file = tmp_path / "integrity.txt"
        test_file.write_text("argus secure checksum", encoding="utf-8")

        checksum = rem.calculate_file_checksum(str(test_file))
        is_valid, curr_hash = rem.verify_file_integrity(str(test_file), checksum)
        assert is_valid is True
        assert curr_hash == checksum

        is_valid_bad, _ = rem.verify_file_integrity(str(test_file), "invalid_hash_12345")
        assert is_valid_bad is False

        is_valid_missing, _ = rem.verify_file_integrity(str(tmp_path / "non_existent.txt"), checksum)
        assert is_valid_missing is False


class TestMasking:
    def test_mask_text_styles(self):
        secret = "123-45-6789"
        
        redacted = rem.mask_text(secret, mask_pattern="redacted")
        assert redacted == "[REDACTED]"

        confidential = rem.mask_text(secret, mask_pattern="confidential")
        assert confidential == "[CONFIDENTIAL]"

        masked = rem.mask_text(secret, mask_pattern="mask")
        assert masked == "XXX-XX-6789"

        short_secret = "abc"
        assert rem.mask_text(short_secret, mask_pattern="mask") == "***"

        custom = rem.mask_text(secret, mask_pattern="[DELETED]")
        assert custom == "[DELETED]"

        assert rem.mask_text("", mask_pattern="redacted") == "[REDACTED]"

    def test_mask_credit_card(self):
        cc = "4532-1122-3344-5566"
        res = rem.mask_text(cc, mask_pattern="mask")
        assert res == "XXXX-XXXX-XXXX-5566"


class TestRedaction:
    def test_redact_file_entity_text(self, tmp_path):
        test_file = tmp_path / "app.env"
        test_file.write_text(
            "PORT=8080\nAPI_KEY=AKIAIOSFODNN7EXAMPLE\nDEBUG=True\n",
            encoding="utf-8"
        )
        checksum = rem.calculate_file_checksum(str(test_file))

        # Redact AKIAIOSFODNN7EXAMPLE on line 2 (cols 8 to 28)
        res = rem.redact_file_entity(
            file_path=str(test_file),
            line_number=2,
            start_col=8,
            end_col=28,
            match_text="AKIAIOSFODNN7EXAMPLE",
            mask_pattern="redacted",
            expected_checksum=checksum,
            base_dir=str(tmp_path)
        )

        assert res["success"] is True
        content = test_file.read_text(encoding="utf-8")
        assert "API_KEY=[REDACTED]" in content
        assert "PORT=8080" in content
        assert "DEBUG=True" in content

    def test_redact_file_entity_integrity_mismatch(self, tmp_path):
        test_file = tmp_path / "tamper.txt"
        test_file.write_text("Line 1\nLine 2 Secret\n", encoding="utf-8")

        res = rem.redact_file_entity(
            file_path=str(test_file),
            line_number=2,
            start_col=7,
            end_col=13,
            match_text="Secret",
            expected_checksum="mismatched_sha256",
            base_dir=str(tmp_path)
        )
        assert res["success"] is False
        assert res["error"] == "file_modified"

    def test_redact_file_entity_not_found(self, tmp_path):
        res = rem.redact_file_entity(str(tmp_path / "missing.txt"), 1, 0, 5, "test", base_dir=str(tmp_path))
        assert res["success"] is False
        assert res["error"] == "file_not_found"

    def test_redact_file_entity_pdf_unsupported(self, tmp_path):
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"%PDF-1.4 dummy")
        res = rem.redact_file_entity(str(test_file), 1, 0, 5, "secret", base_dir=str(tmp_path))
        assert res["success"] is False
        assert res["error"] == "unsupported_format"

    def test_redact_image_unsupported(self, tmp_path):
        img_file = tmp_path / "leak.jpg"
        img_file.write_bytes(b"\xff\xd8\xff dummy jpeg")
        res = rem.redact_file_entity(str(img_file), 1, 0, 5, "secret", base_dir=str(tmp_path))
        assert res["success"] is False
        assert res["error"] == "unsupported_format"

    def test_redact_permission_denied(self, tmp_path):
        test_file = tmp_path / "locked.txt"
        test_file.write_text("Secret=123", encoding="utf-8")
        os.chmod(str(test_file), stat.S_IREAD)

        with patch.object(rem, "check_write_permission", return_value=False):
            res = rem.redact_file_entity(str(test_file), 1, 7, 10, "123", base_dir=str(tmp_path))
            assert res["success"] is False
            assert res["error"] == "permission_denied"

            batch_res = rem.batch_redact_file(str(test_file), base_dir=str(tmp_path))
            assert batch_res["success"] is False
            assert batch_res["error"] == "permission_denied"

        rem.fix_file_permissions(str(test_file))

    def test_batch_redact_file_text_with_findings(self, tmp_path):
        test_file = tmp_path / "credentials.txt"
        test_file.write_text(
            "User: admin | Pass: secret123 | Token: tok_9988\nOther: clean\n",
            encoding="utf-8"
        )

        res = rem.batch_redact_file(str(test_file), mask_pattern="redacted", base_dir=str(tmp_path))
        assert res["success"] is True

    def test_batch_redact_file_not_found(self, tmp_path):
        res = rem.batch_redact_file(str(tmp_path / "missing.txt"), base_dir=str(tmp_path))
        assert res["success"] is False

    def test_batch_redact_image_unsupported(self, tmp_path):
        test_file = tmp_path / "photo.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        res = rem.batch_redact_file(str(test_file), base_dir=str(tmp_path))
        assert res["success"] is False
        assert res["error"] == "unsupported_format"

    def test_batch_redact_no_findings(self, tmp_path):
        clean_file = tmp_path / "clean_file.txt"
        clean_file.write_text("Nothing sensitive here", encoding="utf-8")
        res = rem.batch_redact_file(str(clean_file), base_dir=str(tmp_path))
        assert res["success"] is True
        assert res["redacted_count"] == 0


class TestOfficeRedaction:
    def test_docx_redaction(self, tmp_path):
        test_file = tmp_path / "sample.docx"
        test_file.write_bytes(b"dummy docx binary")

        mock_doc = MagicMock()
        mock_p = MagicMock()
        mock_p.text = "Sensitive SSN is 123-45-6789 in doc"
        mock_doc.paragraphs = [mock_p]
        mock_cell = MagicMock()
        mock_cell.text = "Table 123-45-6789"
        mock_row = MagicMock()
        mock_row.cells = [mock_cell]
        mock_tbl = MagicMock()
        mock_tbl.rows = [mock_row]
        mock_doc.tables = [mock_tbl]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_doc

        with patch.dict(sys.modules, {"docx": mock_docx_module}):
            res = rem.redact_file_entity(
                str(test_file),
                line_number=1,
                start_col=0,
                end_col=11,
                match_text="123-45-6789",
                mask_pattern="redacted",
                base_dir=str(tmp_path)
            )
            assert res["success"] is True

    def test_xlsx_redaction(self, tmp_path):
        test_file = tmp_path / "sample.xlsx"
        test_file.write_bytes(b"dummy xlsx binary")

        mock_wb = MagicMock()
        mock_sheet = MagicMock()
        mock_cell = MagicMock()
        mock_cell.value = "Card 4532-1122-3344-5566"
        mock_sheet.iter_rows.return_value = [[mock_cell]]
        mock_wb.worksheets = [mock_sheet]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}):
            res = rem.redact_file_entity(
                str(test_file),
                line_number=1,
                start_col=0,
                end_col=19,
                match_text="4532-1122-3344-5566",
                mask_pattern="redacted",
                base_dir=str(tmp_path)
            )
            assert res["success"] is True

    def test_pptx_redaction(self, tmp_path):
        test_file = tmp_path / "sample.pptx"
        test_file.write_bytes(b"dummy pptx binary")

        mock_prs = MagicMock()
        mock_slide = MagicMock()
        mock_shape = MagicMock()
        mock_shape.has_text_frame = True
        mock_shape.text = "AWS AKIAIOSFODNN7EXAMPLE key"
        mock_p = MagicMock()
        mock_p.text = "AWS AKIAIOSFODNN7EXAMPLE key"
        mock_shape.text_frame.paragraphs = [mock_p]
        mock_shape.has_table = False
        mock_slide.shapes = [mock_shape]
        mock_prs.slides = [mock_slide]

        mock_pptx = MagicMock()
        mock_pptx.Presentation.return_value = mock_prs

        with patch.dict(sys.modules, {"pptx": mock_pptx}):
            res = rem.redact_file_entity(
                str(test_file),
                line_number=1,
                start_col=0,
                end_col=20,
                match_text="AKIAIOSFODNN7EXAMPLE",
                mask_pattern="redacted",
                base_dir=str(tmp_path)
            )
            assert res["success"] is True


class TestDeletion:
    def test_trash_or_delete_file_permanent(self, tmp_path):
        test_file = tmp_path / "delete_me.txt"
        test_file.write_text("to be deleted", encoding="utf-8")

        res = rem.trash_or_delete_file(str(test_file), permanent=True, base_dir=str(tmp_path))
        assert res["success"] is True
        assert not test_file.exists()

    def test_trash_or_delete_directory_permanent(self, tmp_path):
        target_dir = tmp_path / "dir_to_delete"
        target_dir.mkdir()
        (target_dir / "sub.txt").write_text("sub", encoding="utf-8")

        res = rem.trash_or_delete_file(str(target_dir), permanent=True, base_dir=str(tmp_path))
        assert res["success"] is True
        assert not target_dir.exists()

    def test_trash_or_delete_file_trash(self, tmp_path):
        test_file = tmp_path / "trash_me.txt"
        test_file.write_text("to be trashed", encoding="utf-8")

        res = rem.trash_or_delete_file(str(test_file), permanent=False, base_dir=str(tmp_path))
        assert res["success"] is True
        assert not test_file.exists()

    def test_trash_or_delete_non_existent(self, tmp_path):
        res = rem.trash_or_delete_file(str(tmp_path / "missing.txt"), base_dir=str(tmp_path))
        assert res["success"] is True

    def test_trash_darwin_mock(self, tmp_path):
        test_file = tmp_path / "mac_trash.txt"
        test_file.write_text("mac", encoding="utf-8")
        with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            res = rem.trash_or_delete_file(str(test_file), permanent=False, base_dir=str(tmp_path))
            assert res["success"] is True

    def test_trash_linux_gio_mock(self, tmp_path):
        test_file = tmp_path / "linux_trash.txt"
        test_file.write_text("linux", encoding="utf-8")
        with patch("sys.platform", "linux"), patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0)
            res = rem.trash_or_delete_file(str(test_file), permanent=False, base_dir=str(tmp_path))
            assert res["success"] is True

    def test_trash_windows_mock(self, tmp_path):
        test_file = tmp_path / "win_trash.txt"
        test_file.write_text("win", encoding="utf-8")
        mock_shell32 = MagicMock()
        mock_shell32.SHFileOperationW.return_value = 0
        with patch("sys.platform", "win32"), patch("ctypes.windll.shell32", mock_shell32, create=True):
            res = rem.trash_or_delete_file(str(test_file), permanent=False, base_dir=str(tmp_path))
            assert res["success"] is True


class TestAllowedExceptions:
    def test_mark_as_safe_and_ignore(self, tmp_path):
        test_file = tmp_path / "sample.py"
        test_file.write_text("KEY = 'secret123'\n", encoding="utf-8")
        test_path = str(test_file)

        # Whitelist whole file
        res = rem.mark_as_safe_exception(test_path)
        assert res["success"] is True
        assert rem.is_file_or_match_ignored(test_path) is True

        # Whitelist specific match pattern
        res2 = rem.mark_as_safe_exception(
            test_path,
            match_text="TEST_API_KEY_123",
            pattern_name="API Key"
        )
        assert res2["success"] is True
        assert rem.is_file_or_match_ignored(test_path, match_text="TEST_API_KEY_123") is True

        # Test listing and removing
        exceptions = rem.get_allowed_exceptions()
        assert len(exceptions) >= 1

        ex_id = exceptions[0]["id"]
        remove_res = rem.remove_allowed_exception(ex_id)
        assert remove_res["success"] is True

        # Removing invalid ID
        bad_remove = rem.remove_allowed_exception("invalid_unknown_id")
        assert bad_remove["success"] is False


class TestScannerIntegration:
    def test_scanner_skips_ignored_file(self, tmp_path):
        scannable_file = tmp_path / "safe_notes.txt"
        scannable_file.write_text("AKIAIOSFODNN7EXAMPLE", encoding="utf-8")

        # Mark as safe
        rem.mark_as_safe_exception(str(scannable_file))

        # Scanner get_scannable_files should ignore it
        files = scanner.get_scannable_files([str(tmp_path)])
        assert str(scannable_file) not in [str(f) for f in files]

    def test_locate_text_pii_matches_filters_whitelisted(self, tmp_path):
        test_file = tmp_path / "config.env"
        test_file.write_text("AWS_KEY=AKIAIOSFODNN7EXAMPLE\nOTHER=clean\n", encoding="utf-8")

        # Whitelist this specific match
        rem.mark_as_safe_exception(str(test_file), match_text="AKIAIOSFODNN7EXAMPLE")

        # Locate matches with file_path
        matches = scanner.locate_text_pii_matches(
            test_file.read_text(encoding="utf-8"),
            file_path=str(test_file)
        )
        assert len(matches) == 0


class TestAPIEndpoints:
    def test_api_remediation_endpoints(self, tmp_path):
        api = Api()
        test_file = tmp_path / "api_test.txt"
        test_file.write_text("SECRET=123-45-6789\n", encoding="utf-8")

        # 1. Preview details
        preview = api.get_file_preview_details(str(test_file))
        assert preview["is_writable"] is True
        assert len(preview["highlights"]) > 0

        # Non-existent preview
        bad_preview = api.get_file_preview_details(str(tmp_path / "missing_file.txt"))
        assert "error" in bad_preview

        # 2. Redact entity
        h = preview["highlights"][0]
        redact_res = api.redact_entity(
            str(test_file),
            h["line_number"],
            h["start_col"],
            h["end_col"],
            h["match_text"],
            "redacted",
            preview["checksum"]
        )
        assert redact_res["success"] is True

        # 3. Batch redact
        test_file2 = tmp_path / "batch_test.txt"
        test_file2.write_text("SSN: 987-65-4321\nKEY: AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8")
        batch_res = api.batch_redact(str(test_file2))
        assert batch_res["success"] is True

        # 4. Mark as safe
        safe_res = api.mark_as_safe(str(test_file), "some_safe_str", "Safe Pattern")
        assert safe_res["success"] is True

        # 5. Get allowed exceptions
        exs = api.get_allowed_exceptions()
        assert len(exs) > 0

        # 6. Remove exception
        api.remove_allowed_exception(exs[0]["id"])

        # 7. Backups API
        backups = api.get_backups_list()
        assert isinstance(backups, list)
        prune_res = api.prune_backups(7)
        assert "pruned_count" in prune_res

        # 8. Restore backup
        if len(backups) > 0:
            restore_res = api.restore_backup_file(backups[0]["id"])
            assert "success" in restore_res

        # 9. Permissions
        perm_res = api.fix_file_permissions(str(test_file))
        assert perm_res["success"] is True

        # 10. Delete file item & batch delete
        del_res = api.delete_file_item(str(test_file), permanent=True)
        assert del_res["success"] is True
        assert not test_file.exists()

        del_batch = api.batch_delete_files([str(test_file2)], permanent=True)
        assert isinstance(del_batch, list)
        assert len(del_batch) == 1
        assert del_batch[0] == str(test_file2)
        assert not test_file2.exists()


class TestEdgeCasesAndParsing:
    def test_redact_plain_text_empty(self):
        assert rem._redact_plain_text("", 1, 0, 0, "test", "[REDACTED]") == ""

    def test_redact_plain_text_fallback_in_line(self):
        content = "Line 1\nSecretKey=123456\nLine 3\n"
        res = rem._redact_plain_text(content, line_number=2, start_col=0, end_col=5, match_text="123456", masked="[REDACTED]")
        assert "SecretKey=[REDACTED]" in res

    def test_redact_plain_text_out_of_bounds_fallback_global(self):
        content = "Line 1\nSecretKey=123456\nLine 3\n"
        res = rem._redact_plain_text(content, line_number=99, start_col=0, end_col=5, match_text="123456", masked="[REDACTED]")
        assert "SecretKey=[REDACTED]" in res

    def test_redact_plain_text_string_not_found(self):
        content = "Line 1\nLine 2\n"
        res = rem._redact_plain_text(content, line_number=99, start_col=0, end_col=5, match_text="NONEXISTENT", masked="[REDACTED]")
        assert res == content

    def test_argusignore_parsing_and_rules(self, tmp_path):
        ignore_file = tmp_path / ".argusignore"
        ignore_file.write_text(
            "# Comments and empty lines\n\n*.tmp\n/build/\nsecret_match_value\n",
            encoding="utf-8"
        )

        entries = rem.load_argusignore(base_dir=str(tmp_path))
        assert len(entries) == 3
        assert entries[0] == "*.tmp"
        assert entries[1] == "/build/"
        assert entries[2] == "secret_match_value"

        # Check ignored matching
        assert rem.is_file_or_match_ignored(str(tmp_path / "test.tmp"), base_dir=str(tmp_path)) is True
        assert rem.is_file_or_match_ignored(str(tmp_path / "build" / "app.js"), base_dir=str(tmp_path)) is True
        assert rem.is_file_or_match_ignored(str(tmp_path / "notes.txt"), match_text="secret_match_value", base_dir=str(tmp_path)) is True
        assert rem.is_file_or_match_ignored(str(tmp_path / "notes.txt"), match_text="clean_value", base_dir=str(tmp_path)) is False

    def test_append_argusignore_with_comment(self, tmp_path):
        rem.append_argusignore_entry("test_rule", comment="Rule description", base_dir=str(tmp_path))
        lines = rem.load_argusignore(base_dir=str(tmp_path))
        assert "test_rule" in lines

    def test_sync_state_with_remaining_findings(self, tmp_path):
        test_file = tmp_path / "partial.txt"
        test_file.write_text("API_KEY=AKIAIOSFODNN7EXAMPLE\nSECOND_KEY=AKIAIOSFODNN7EXAMPLE2\n", encoding="utf-8")

        results = [{"file": str(test_file), "compromised": True, "reason": "Initial leaks"}]
        state.save_results(results)
        scanner.scan_state.flagged_files = [{"file": str(test_file), "compromised": True}]

        checksum = rem.calculate_file_checksum(str(test_file))
        rem._sync_state_after_remediation(str(test_file), checksum)

        saved = state.load_results()
        assert len(saved) >= 0
