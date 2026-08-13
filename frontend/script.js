// Wait for PyWebView API to be ready
window.addEventListener('pywebviewready', function() {
    initApp();
});

// Fallback for direct browser testing
window.addEventListener('DOMContentLoaded', function() {
    if (!window.pywebview) {
        setTimeout(() => {
            if (!window.appInitialized) {
                initApp();
            }
        }, 300);
    }
});

let scanInterval = null;
let currentResults = [];
let currentPreviewFile = null;
let currentPreviewData = null;
let currentResultsTab = 'active'; // 'active' or 'resolved'
let resultsSearchQuery = '';
let activeFindingIndex = 0;
let lastScanStats = { scanned_files: 0, flagged_count: 0 };

function switchView(targetId) {
    document.querySelectorAll('.nav-item').forEach(n => {
        if (n.getAttribute('data-target') === targetId) {
            n.classList.add('active');
        } else {
            n.classList.remove('active');
        }
    });
    document.querySelectorAll('.view').forEach(v => {
        if (v.id === targetId) {
            v.classList.add('active');
        } else {
            v.classList.remove('active');
        }
    });

    if (targetId === 'results' && (!window.argusTour || !window.argusTour.isActive)) {
        loadResults();
    }
}

function initTheme() {
    const themeToggle = document.getElementById('theme-toggle');
    const savedTheme = localStorage.getItem('argus-theme') || 'dark';
    
    document.documentElement.setAttribute('data-theme', savedTheme);
    if (themeToggle) {
        themeToggle.checked = savedTheme === 'light';
        themeToggle.addEventListener('change', (e) => {
            const newTheme = e.target.checked ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('argus-theme', newTheme);
        });
    }
}

function renderFolders(folders) {
    const list = document.getElementById('folder-list');
    list.innerHTML = '';
    
    if (folders.length === 0) {
        list.innerHTML = '<p style="color:var(--text-muted); font-size: 13px; padding: 12px;">No directories added for inspection yet.</p>';
        return;
    }

    folders.forEach((folder, index) => {
        const li = document.createElement('li');
        li.className = 'folder-item';
        li.innerHTML = `
            <div class="folder-path" title="${folder}">${folder}</div>
            <button class="btn-icon delete-folder-btn" data-index="${index}" title="Remove Folder"><i class="ph ph-x"></i></button>
        `;
        list.appendChild(li);
    });

    document.querySelectorAll('.delete-folder-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const index = parseInt(e.currentTarget.getAttribute('data-index'));
            const settings = await pywebview.api.get_settings();
            settings.folders.splice(index, 1);
            await pywebview.api.save_settings(settings);
            renderFolders(settings.folders);
        });
    });
}

// ============================================================================
// SECTION 1: Counter Badge Management
// ============================================================================

/**
 * Requirement 1: In the area of the image labeled 1, display a counter only if
 * there are pending files that need review or have been identified as containing PII.
 */
function updateDetectionsCounter(results) {
    const counterEl = document.getElementById('nav-results-counter');
    if (!counterEl) return;

    const list = Array.isArray(results) ? results : (currentResults || []);
    // Count pending files needing review or identified as containing PII
    const pendingCount = list.filter(r => !r.auto_deleted && r.compromised !== false).length;

    if (pendingCount > 0) {
        counterEl.textContent = pendingCount;
        counterEl.classList.remove('hidden');
    } else {
        counterEl.textContent = '0';
        counterEl.classList.add('hidden');
    }
}

// ============================================================================
// SECTION 2: Reset Main Screen Handler
// ============================================================================

/**
 * Requirement 2: When the user clicks "Okay", the main screen must reset.
 */
function resetMainScreen() {
    const summaryContainer = document.getElementById('scan-summary-container');
    const progressContainer = document.getElementById('scan-progress-container');
    const startScanBtn = document.getElementById('start-scan-btn');
    const modeOptions = document.getElementById('scan-mode-options');
    const sidebarScanStatus = document.getElementById('sidebar-scan-status');
    const fillEl = document.getElementById('scan-progress-fill');
    const scannedCountEl = document.getElementById('scan-scanned-count');
    const skippedCountEl = document.getElementById('scan-skipped-count');
    const flaggedCountEl = document.getElementById('scan-flagged-count');
    const currentFileEl = document.getElementById('scan-current-file');

    if (summaryContainer) summaryContainer.classList.add('hidden');
    if (progressContainer) progressContainer.classList.add('hidden');
    if (sidebarScanStatus) sidebarScanStatus.classList.add('hidden');
    if (modeOptions) modeOptions.classList.remove('hidden');
    if (startScanBtn) {
        startScanBtn.classList.remove('hidden');
        startScanBtn.disabled = false;
        startScanBtn.innerHTML = '<i class="ph-fill ph-play"></i> SCAN NOW';
    }

    if (fillEl) fillEl.style.width = '0%';
    if (scannedCountEl) scannedCountEl.innerText = '0 / 0';
    if (skippedCountEl) skippedCountEl.innerText = '(0 skipped)';
    if (flaggedCountEl) flaggedCountEl.innerText = '0 flagged';
    if (currentFileEl) currentFileEl.innerText = 'Scanning...';
}

function startProgressPolling() {
    if (scanInterval) clearInterval(scanInterval);
    scanInterval = setInterval(async () => {
        const data = await pywebview.api.get_scan_progress();
        
        if (data.flagged_files) {
            renderResultsUI(data.flagged_files);
        }

        if (!data.is_scanning) {
            stopProgressPolling(true);
            await loadResults();
            return;
        }

        const p = data.progress || {};
        lastScanStats.scanned_files = p.scanned_files || 0;
        lastScanStats.flagged_count = p.flagged_count || 0;

        const percent = p.total_files > 0 ? (p.scanned_files / p.total_files) * 100 : 0;
        
        document.getElementById('scan-progress-fill').style.width = `${percent}%`;
        document.getElementById('scan-scanned-count').innerText = `${p.scanned_files} / ${p.total_files}`;
        
        const skippedCount = p.skipped_count || 0;
        const skippedEl = document.getElementById('scan-skipped-count');
        if (skippedEl) {
            skippedEl.innerText = `(${skippedCount} skipped)`;
        }
        
        document.getElementById('scan-flagged-count').innerText = `${p.flagged_count} flagged`;
        
        const filePath = p.current_file || '';
        const fileName = filePath ? filePath.split('\\').pop().split('/').pop() : 'Inspecting...';
        document.getElementById('scan-current-file').innerText = fileName ? `Inspecting: ${fileName}` : 'Inspecting...';
        
    }, 800);
}

function stopProgressPolling(completedSuccessfully = false) {
    if (scanInterval) clearInterval(scanInterval);
    
    document.getElementById('scan-progress-container').classList.add('hidden');
    document.getElementById('sidebar-scan-status').classList.add('hidden');

    if (completedSuccessfully) {
        // Requirement 2: Show Scan Summary Overview in Section 2
        const summaryScanned = document.getElementById('summary-scanned-count');
        const summaryFlagged = document.getElementById('summary-flagged-count');
        if (summaryScanned) summaryScanned.innerText = lastScanStats.scanned_files;
        if (summaryFlagged) summaryFlagged.innerText = lastScanStats.flagged_count;

        const summaryContainer = document.getElementById('scan-summary-container');
        if (summaryContainer) summaryContainer.classList.remove('hidden');

        // Hide start scan btn & options while summary is displayed
        document.getElementById('start-scan-btn').classList.add('hidden');
        const modeOptions = document.getElementById('scan-mode-options');
        if (modeOptions) modeOptions.classList.add('hidden');
    } else {
        resetMainScreen();
    }
}

async function loadResults() {
    const results = await pywebview.api.get_results();
    currentResults = results;
    document.getElementById('select-all-checkbox').checked = false;
    renderResultsUI(results);
}

function renderResultsUI(results) {
    const list = document.getElementById('results-list');
    if (!list) return;

    // Requirement 1: Update Detections & Reports counter badge in sidebar
    updateDetectionsCounter(results);

    // Filter active vs resolved
    const activeResults = results.filter(r => !r.auto_deleted && r.compromised !== false);
    const resolvedResults = results.filter(r => r.auto_deleted || r.compromised === false);

    const activeBadge = document.getElementById('active-findings-badge');
    const resolvedBadge = document.getElementById('resolved-findings-badge');
    if (activeBadge) activeBadge.textContent = activeResults.length;
    if (resolvedBadge) resolvedBadge.textContent = resolvedResults.length;

    let targetResults = currentResultsTab === 'resolved' ? resolvedResults : activeResults;

    // Apply search query filter if typed
    if (resultsSearchQuery) {
        const q = resultsSearchQuery.toLowerCase();
        targetResults = targetResults.filter(r => {
            const fileName = (r.file || '').toLowerCase();
            const reason = (r.reason || '').toLowerCase();
            const type = (r.type || '').toLowerCase();
            return fileName.includes(q) || reason.includes(q) || type.includes(q);
        });
    }

    if (targetResults.length === 0) {
        if (currentResultsTab === 'resolved') {
            list.innerHTML = `
                <div class="empty-state">
                    <i class="ph-fill ph-check-circle" style="font-size: 52px; color: var(--argus-teal);"></i>
                    <p style="margin-top: 14px; font-weight: 700; font-size: 16px; color: var(--text-main);">No Resolved Files Yet</p>
                    <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Remediated or whitelisted safe files will appear here.</p>
                </div>
            `;
        } else {
            list.innerHTML = `
                <div class="empty-state">
                    <i class="ph-fill ph-shield-check" style="font-size: 52px; color: var(--argus-teal);"></i>
                    <p style="margin-top: 14px; font-weight: 700; font-size: 16px; color: var(--text-main);">All Inspected Files are SECURE</p>
                    <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">No active PII leaks or compromised data detected.</p>
                </div>
            `;
        }
        return;
    }

    list.innerHTML = '';
    targetResults.forEach((res, rowIdx) => {
        const row = document.createElement('div');
        row.className = 'result-row';
        row.id = `result-row-${rowIdx}`;
        const isDeleted = res.auto_deleted;
        const needsVerification = res.needs_ai_verification;
        const isVerified = res.verified_true;
        
        let checkboxHtml = '';
        if (isDeleted) {
            checkboxHtml = `<span class="danger-text" style="font-size: 11px; font-weight: 700; white-space: nowrap; margin-left: -4px;">DELETED</span>`;
        } else {
            checkboxHtml = `<input type="checkbox" class="result-checkbox" data-file="${res.file.replace(/"/g, '&quot;')}">`;
        }
        
        // Status Badge
        let statusBadgeHtml = '';
        if (isDeleted) {
            statusBadgeHtml = `<span class="status-indicator badge-leak"><i class="ph-bold ph-trash"></i> REMOVED</span>`;
        } else if (needsVerification) {
            statusBadgeHtml = `<span class="status-indicator badge-attention"><i class="ph-bold ph-warning"></i> ATTENTION</span>`;
        } else if (res.compromised === false) {
            statusBadgeHtml = `<span class="status-indicator badge-secure"><i class="ph-bold ph-check-circle"></i> SECURE</span>`;
        } else {
            statusBadgeHtml = `<span class="status-indicator badge-leak"><i class="ph-bold ph-x-circle"></i> LEAK FOUND</span>`;
        }
        
        // Action Buttons
        let actionsHtml = `<div style="display:flex; align-items:center; gap:8px; margin-left:auto;">`;
        if (needsVerification) {
            actionsHtml += `<button class="btn btn-secondary btn-small verify-ai-btn" data-file="${res.file.replace(/"/g, '&quot;')}"><i class="ph-fill ph-magic-wand"></i> AI Verify</button>`;
        } else if (isVerified) {
            actionsHtml += `<span style="color: var(--argus-teal); font-size: 12px; font-weight: 700; display:flex; align-items:center; gap:4px;"><i class="ph-fill ph-check-circle"></i> Verified</span>`;
        }
        if (!isDeleted) {
            actionsHtml += `<button class="btn btn-primary btn-small quick-redact-btn" data-file="${res.file.replace(/"/g, '&quot;')}" title="Sanitize all findings in this file in-place"><i class="ph-bold ph-eraser"></i> Redact</button>`;
            actionsHtml += `<button class="mark-ok-btn" data-file="${res.file.replace(/"/g, '&quot;')}" title="Mark as false positive (whitelist rule)"><i class="ph-bold ph-shield-check"></i> Safe</button>`;
        }
        actionsHtml += `</div>`;
        
        const dataFileAttr = isDeleted ? '' : `data-file="${res.file.replace(/"/g, '&quot;')}"`;
        
        row.innerHTML = `
            <div class="col-checkbox">${checkboxHtml}</div>
            <div class="col-file ${isDeleted ? 'deleted' : ''}" title="${res.file}" ${dataFileAttr}>
                ${res.file.split('\\').pop().split('/').pop()}
            </div>
            <div class="col-type">${res.type}</div>
            <div class="col-status">${statusBadgeHtml}</div>
            <div class="col-reason" style="display:flex; justify-content:space-between; align-items:center;">
                <span style="flex:1; margin-right:12px;">${res.reason}</span>
                ${actionsHtml}
            </div>
        `;
        list.appendChild(row);
    });

    // Add click handler for file preview / inspector
    document.querySelectorAll('.col-file:not(.deleted)').forEach(el => {
        el.addEventListener('click', async (e) => {
            const filePath = e.currentTarget.getAttribute('data-file');
            showPreview(filePath);
        });
    });

    // Quick Redact in list
    document.querySelectorAll('.quick-redact-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filePath = e.currentTarget.getAttribute('data-file');
            btn.innerHTML = '<i class="ph ph-spinner spin"></i> Redacting...';
            btn.disabled = true;
            if (pywebview.api.batch_redact) {
                const res = await pywebview.api.batch_redact(filePath);
                if (res && res.success) {
                    loadResults();
                } else {
                    alert(res?.message || 'Redaction failed');
                    btn.innerHTML = '<i class="ph-bold ph-eraser"></i> Redact';
                    btn.disabled = false;
                }
            }
        });
    });

    // Add click handler for Mark OK / Safe buttons
    document.querySelectorAll('.mark-ok-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filePath = e.currentTarget.getAttribute('data-file');
            if (pywebview.api.mark_as_safe) {
                await pywebview.api.mark_as_safe(filePath);
            } else {
                await pywebview.api.mark_file_ok(filePath);
            }
            loadResults();
        });
    });

    // Add click handler for AI Verify button
    document.querySelectorAll('.verify-ai-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filePath = e.currentTarget.getAttribute('data-file');
            e.currentTarget.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Verifying...';
            e.currentTarget.disabled = true;
            
            await pywebview.api.verify_file(filePath);
            loadResults();
        });
    });
}

// --------------------------------------------------------------------------
// Deep Remediation Inspector & Preview Modal
// --------------------------------------------------------------------------

async function showPreview(filePath) {
    currentPreviewFile = filePath;
    activeFindingIndex = 0;

    const modal = document.getElementById('preview-modal');
    const body = document.getElementById('preview-body');
    const title = document.getElementById('preview-title');
    const subtitle = document.getElementById('preview-subtitle');
    const iconContainer = document.getElementById('preview-file-icon');
    const badgesContainer = document.getElementById('preview-badges');
    const findingsBar = document.getElementById('preview-findings-bar');
    const findingsChips = document.getElementById('preview-findings-chips');
    const reasonText = document.getElementById('preview-status-reason');
    const alertBanner = document.getElementById('preview-alert-banner');

    const fileName = filePath.split('\\').pop().split('/').pop();
    title.innerText = fileName;
    title.setAttribute('title', filePath);
    subtitle.innerText = filePath;
    badgesContainer.innerHTML = '';
    findingsChips.innerHTML = '';
    findingsBar.classList.add('hidden');
    if (alertBanner) {
        alertBanner.innerHTML = '';
        alertBanner.className = 'preview-alert-banner hidden';
    }
    reasonText.innerText = '';
    body.innerHTML = '<div class="pulse-ring"></div>';
    modal.classList.remove('hidden');

    let previewData = null;
    try {
        if (pywebview.api.get_file_preview_details) {
            previewData = await pywebview.api.get_file_preview_details(filePath);
        } else {
            const raw = await pywebview.api.get_image_base64(filePath);
            previewData = {
                file_path: filePath,
                file_name: fileName,
                content_type: raw && raw.startsWith('data:image') ? 'image' : 'text',
                data: raw,
                content: raw,
                highlights: []
            };
        }
    } catch (e) {
        body.innerHTML = `<p style="color:var(--danger)">Error loading preview: ${e.message}</p>`;
        return;
    }

    if (!previewData || previewData.error) {
        body.innerHTML = `<p style="color:var(--text-muted)">${previewData?.error || 'File not found or empty.'}</p>`;
        return;
    }

    currentPreviewData = previewData;

    // Check write permissions
    if (previewData.is_writable === false && alertBanner) {
        alertBanner.className = 'preview-alert-banner alert-permission';
        alertBanner.innerHTML = `
            <span><i class="ph-bold ph-lock-key"></i> <strong>Permission Denied:</strong> This file is read-only. Remove write protection to enable in-place remediation.</span>
            <button id="alert-fix-permissions-btn" class="btn btn-secondary btn-small">
                <i class="ph-bold ph-key"></i> Fix Permissions
            </button>
        `;
        alertBanner.classList.remove('hidden');

        const fixBtn = document.getElementById('alert-fix-permissions-btn');
        if (fixBtn) {
            fixBtn.addEventListener('click', async () => {
                fixBtn.disabled = true;
                fixBtn.innerHTML = '<i class="ph ph-spinner spin"></i> Fixing...';
                if (pywebview.api.fix_file_permissions) {
                    const res = await pywebview.api.fix_file_permissions(filePath);
                    if (res && res.success) {
                        showPreview(filePath);
                    } else {
                        alert('Could not update file permissions: ' + (res?.error || 'Unknown error'));
                        fixBtn.disabled = false;
                        fixBtn.innerHTML = '<i class="ph-bold ph-key"></i> Fix Permissions';
                    }
                }
            });
        }
    }

    if (previewData.content_type === 'image') {
        iconContainer.innerHTML = '<i class="ph-fill ph-image" style="color:var(--argus-teal)"></i>';
        renderImagePreview(previewData);
    } else {
        const fileType = previewData.file_type || 'Text';
        const iconName = fileType === 'PDF' ? 'ph-file-pdf' : fileType === 'Office' ? 'ph-file-doc' : 'ph-file-code';
        iconContainer.innerHTML = `<i class="ph-fill ${iconName}" style="color:var(--argus-teal)"></i>`;
        renderTextPreview(previewData);
    }
}

function renderTextPreview(previewData) {
    const body = document.getElementById('preview-body');
    const badgesContainer = document.getElementById('preview-badges');
    const findingsBar = document.getElementById('preview-findings-bar');
    const findingsChips = document.getElementById('preview-findings-chips');
    const reasonText = document.getElementById('preview-status-reason');
    const batchRedactBtn = document.getElementById('modal-batch-redact-btn');

    const highlights = previewData.highlights || [];
    const content = previewData.content || '';
    reasonText.innerText = previewData.reason || '';

    if (batchRedactBtn) {
        batchRedactBtn.style.display = (highlights.length > 0 && previewData.file_type !== 'PDF') ? 'inline-flex' : 'none';
    }

    // Badges & Findings bar
    let checksumBadge = '';
    if (previewData.checksum) {
        checksumBadge = `<span class="chip" style="font-size:11px; padding:2px 8px; font-family:monospace;" title="SHA-256 Checksum: ${escapeHtml(previewData.checksum)}"><i class="ph-bold ph-fingerprint"></i> ${escapeHtml(previewData.checksum.slice(0, 8))}...</span>`;
    }

    if (highlights.length > 0) {
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-leak"><i class="ph-bold ph-warning"></i> ${highlights.length} ${highlights.length === 1 ? 'Finding' : 'Findings'}</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Document'}</span>
            ${checksumBadge}
        `;
        findingsBar.classList.remove('hidden');
        findingsChips.innerHTML = '';

        highlights.forEach((h, idx) => {
            const chip = document.createElement('button');
            chip.className = `finding-chip ${h.source === 'ai' ? 'chip-ai' : ''} ${idx === activeFindingIndex ? 'active-chip' : ''}`;
            chip.id = `finding-chip-${idx}`;
            const icon = h.source === 'ai' ? 'ph-magic-wand' : 'ph-crosshair';
            chip.innerHTML = `<i class="ph-bold ${icon}"></i> #${idx + 1} Line ${h.line_number}: ${escapeHtml(h.pattern_name)}`;
            chip.title = `Jump to Line ${h.line_number} ("${h.match_text}")`;
            chip.addEventListener('click', () => {
                focusFindingIndex(idx);
            });
            findingsChips.appendChild(chip);
        });
    } else {
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-secure"><i class="ph-bold ph-check-circle"></i> Clean</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Document'}</span>
            ${checksumBadge}
        `;
        findingsBar.classList.add('hidden');
    }

    // Map highlights to line numbers
    const lines = content.split('\n');
    const wrapper = document.createElement('div');
    wrapper.className = 'code-viewer-wrapper';
    wrapper.id = 'code-viewer-scroll-container';

    const table = document.createElement('div');
    table.className = 'code-viewer-table';

    const lineHighlightsMap = {};
    highlights.forEach((h, idx) => {
        h._globalIndex = idx;
        if (!lineHighlightsMap[h.line_number]) {
            lineHighlightsMap[h.line_number] = [];
        }
        lineHighlightsMap[h.line_number].push(h);
    });

    lines.forEach((lineText, idx) => {
        const lineNum = idx + 1;
        const lineRow = document.createElement('div');
        lineRow.className = 'code-row';
        lineRow.id = `code-line-${lineNum}`;

        const isFlagged = Boolean(lineHighlightsMap[lineNum]);
        if (isFlagged) {
            lineRow.classList.add('line-flagged');
        }

        const numCell = document.createElement('div');
        numCell.className = 'line-num';
        numCell.innerText = lineNum;

        const textCell = document.createElement('div');
        textCell.className = 'line-text';

        if (isFlagged) {
            textCell.innerHTML = formatHighlightedLine(lineText, lineHighlightsMap[lineNum]);
        } else {
            textCell.textContent = lineText || ' ';
        }

        lineRow.appendChild(numCell);
        lineRow.appendChild(textCell);
        table.appendChild(lineRow);

        // Persistent inline action bar beneath each flagged finding line
        if (isFlagged && previewData.file_type !== 'PDF') {
            const lineHits = lineHighlightsMap[lineNum];
            lineHits.forEach(h => {
                const actionBar = document.createElement('div');
                actionBar.className = 'inline-finding-action-bar';
                actionBar.id = `action-bar-finding-${h._globalIndex}`;
                actionBar.innerHTML = `
                    <span class="inline-finding-label"><i class="ph-bold ph-shield-warning"></i> Finding #${h._globalIndex + 1}: ${escapeHtml(h.pattern_name)}</span>
                    <button class="inline-finding-btn inline-redact-btn" data-finding-idx="${h._globalIndex}" title="Sanitize only this detected string in-place">
                        <i class="ph-bold ph-eraser"></i> Redact Entity <kbd>R</kbd>
                    </button>
                    <button class="inline-finding-btn inline-safe-btn" data-finding-idx="${h._globalIndex}" title="Add whitelist rule to .argusignore">
                        <i class="ph-bold ph-shield-check"></i> Mark Safe <kbd>S</kbd>
                    </button>
                    <button class="inline-finding-btn inline-trash-btn" title="Move entire file to Recycle Bin">
                        <i class="ph-bold ph-trash"></i> Delete File <kbd>D</kbd>
                    </button>
                `;

                // Redact button handler
                actionBar.querySelector('.inline-redact-btn').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await executeRedactFinding(h);
                });

                // Mark Safe button handler
                actionBar.querySelector('.inline-safe-btn').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await executeMarkFindingSafe(h);
                });

                // Trash button handler
                actionBar.querySelector('.inline-trash-btn').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await executeDeleteFile();
                });

                table.appendChild(actionBar);
            });
        }
    });

    wrapper.appendChild(table);
    body.innerHTML = '';
    body.appendChild(wrapper);

    if (highlights.length > 0) {
        setTimeout(() => {
            focusFindingIndex(0);
        }, 80);
    }
}

function focusFindingIndex(index) {
    if (!currentPreviewData || !currentPreviewData.highlights || currentPreviewData.highlights.length === 0) return;
    const count = currentPreviewData.highlights.length;
    activeFindingIndex = (index + count) % count;

    const finding = currentPreviewData.highlights[activeFindingIndex];
    if (!finding) return;

    // Update active chip
    document.querySelectorAll('.finding-chip').forEach((c, idx) => {
        if (idx === activeFindingIndex) {
            c.classList.add('active-chip');
            c.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        } else {
            c.classList.remove('active-chip');
        }
    });

    // Highlight row
    document.querySelectorAll('.code-row').forEach(r => r.classList.remove('active-finding'));
    const targetLine = document.getElementById(`code-line-${finding.line_number}`);
    if (targetLine) {
        targetLine.classList.add('active-finding');
    }

    scrollToCodeLine(finding.line_number);
}

async function executeRedactFinding(finding) {
    if (!currentPreviewFile || !finding) return;
    const btn = document.querySelector(`#action-bar-finding-${finding._globalIndex} .inline-redact-btn`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="ph ph-spinner spin"></i> Redacting...';
    }

    if (pywebview.api.redact_entity) {
        const res = await pywebview.api.redact_entity(
            currentPreviewFile,
            finding.line_number,
            finding.start_col,
            finding.end_col,
            finding.match_text,
            null,
            currentPreviewData?.checksum
        );

        if (res && res.success) {
            await showPreview(currentPreviewFile);
            loadResults();
        } else if (res && res.error === 'file_modified') {
            const alertBanner = document.getElementById('preview-alert-banner');
            if (alertBanner) {
                alertBanner.className = 'preview-alert-banner alert-modified';
                alertBanner.innerHTML = `
                    <span><i class="ph-bold ph-warning"></i> <strong>File Modified:</strong> File was modified externally on disk.</span>
                    <button id="alert-reload-btn" class="btn btn-secondary btn-small"><i class="ph-bold ph-arrows-clockwise"></i> Reload Preview</button>
                `;
                alertBanner.classList.remove('hidden');
                document.getElementById('alert-reload-btn')?.addEventListener('click', () => showPreview(currentPreviewFile));
            }
        } else if (res && res.error === 'permission_denied') {
            const alertBanner = document.getElementById('preview-alert-banner');
            if (alertBanner) {
                alertBanner.className = 'preview-alert-banner alert-permission';
                alertBanner.innerHTML = `
                    <span><i class="ph-bold ph-lock-key"></i> <strong>Permission Denied:</strong> File is read-only.</span>
                    <button id="alert-fix-perm-btn" class="btn btn-secondary btn-small"><i class="ph-bold ph-key"></i> Fix Permissions</button>
                `;
                alertBanner.classList.remove('hidden');
            }
        } else {
            alert('Redaction error: ' + (res?.message || res?.error || 'Unknown error'));
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="ph-bold ph-eraser"></i> Redact Entity <kbd>R</kbd>';
            }
        }
    }
}

async function executeMarkFindingSafe(finding) {
    if (!currentPreviewFile) return;
    if (pywebview.api.mark_as_safe) {
        await pywebview.api.mark_as_safe(
            currentPreviewFile,
            finding ? finding.match_text : null,
            finding ? finding.pattern_name : null
        );
    } else {
        await pywebview.api.mark_file_ok(currentPreviewFile);
    }
    const modal = document.getElementById('preview-modal');
    if (modal) modal.classList.add('hidden');
    loadResults();
}

async function executeDeleteFile() {
    if (!currentPreviewFile) return;
    const fileName = currentPreviewFile.split('\\').pop().split('/').pop();
    if (confirm(`Move "${fileName}" to Recycle Bin / System Trash?`)) {
        if (pywebview.api.delete_file_item) {
            await pywebview.api.delete_file_item(currentPreviewFile);
        } else {
            await pywebview.api.delete_files([currentPreviewFile]);
        }
        const modal = document.getElementById('preview-modal');
        if (modal) modal.classList.add('hidden');
        loadResults();
    }
}

function formatHighlightedLine(lineText, lineHighlights) {
    if (!lineHighlights || lineHighlights.length === 0) {
        return escapeHtml(lineText) || '&nbsp;';
    }

    const sorted = [...lineHighlights].sort((a, b) => a.start_col - b.start_col);
    let result = '';
    let currIdx = 0;

    sorted.forEach(h => {
        const start = Math.max(currIdx, h.start_col);
        const end = Math.min(lineText.length, h.end_col);
        if (start > currIdx) {
            result += escapeHtml(lineText.substring(currIdx, start));
        }
        if (start < end) {
            const matchSnippet = escapeHtml(lineText.substring(start, end));
            const highlightClass = h.source === 'ai' ? 'pii-highlight pii-highlight-ai' : 'pii-highlight';
            result += `<mark class="${highlightClass}" title="${escapeHtml(h.pattern_name)}: ${matchSnippet}">${matchSnippet}</mark>`;
            currIdx = end;
        }
    });

    if (currIdx < lineText.length) {
        result += escapeHtml(lineText.substring(currIdx));
    }

    return result || '&nbsp;';
}

function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function scrollToCodeLine(lineNum) {
    const el = document.getElementById(`code-line-${lineNum}`);
    const container = document.getElementById('code-viewer-scroll-container');
    if (el && container) {
        const topOffset = el.offsetTop - container.offsetTop - 30;
        container.scrollTo({ top: Math.max(0, topOffset), behavior: 'smooth' });
        el.classList.remove('flash-highlight');
        void el.offsetWidth;
        el.classList.add('flash-highlight');
    }
}

function renderImagePreview(previewData) {
    const body = document.getElementById('preview-body');
    const badgesContainer = document.getElementById('preview-badges');
    const findingsBar = document.getElementById('preview-findings-bar');
    const findingsChips = document.getElementById('preview-findings-chips');
    const reasonText = document.getElementById('preview-status-reason');

    const items = previewData.items || [];
    reasonText.innerText = previewData.reason || 'Image inspected for sensitive content';

    const stage = document.createElement('div');
    stage.className = 'image-stage';

    const wrapper = document.createElement('div');
    wrapper.className = 'image-annotated-wrapper';

    const img = document.createElement('img');
    img.src = previewData.data;
    img.alt = 'Argus Vision Inspection';

    const overlay = document.createElement('div');
    overlay.className = 'annotation-overlay';

    wrapper.appendChild(img);
    wrapper.appendChild(overlay);
    stage.appendChild(wrapper);
    body.innerHTML = '';
    body.appendChild(stage);

    if (items.length > 0) {
        let checksumBadge = '';
        if (previewData.checksum) {
            checksumBadge = `<span class="chip" style="font-size:11px; padding:2px 8px; font-family:monospace;" title="SHA-256 Checksum: ${escapeHtml(previewData.checksum)}"><i class="ph-bold ph-fingerprint"></i> ${escapeHtml(previewData.checksum.slice(0, 8))}...</span>`;
        }
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-leak"><i class="ph-bold ph-eye"></i> ${items.length} ${items.length === 1 ? 'Detection' : 'Detections'}</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Image'}</span>
            ${checksumBadge}
        `;
        findingsBar.classList.remove('hidden');
        findingsChips.innerHTML = '';

        items.forEach(item => {
            const label = item.label || 'Sensitive Item';
            const chip = document.createElement('button');
            chip.className = 'finding-chip chip-ai';
            chip.innerHTML = `<i class="ph-bold ph-bounding-box"></i> ${escapeHtml(label)}`;
            chip.title = item.description || label;
            findingsChips.appendChild(chip);

            if (item.box_2d && Array.isArray(item.box_2d) && item.box_2d.length === 4) {
                const [ymin, xmin, ymax, xmax] = item.box_2d;
                const topPct = (ymin / 10).toFixed(2);
                const leftPct = (xmin / 10).toFixed(2);
                const widthPct = Math.max(4, ((xmax - xmin) / 10)).toFixed(2);
                const heightPct = Math.max(4, ((ymax - ymin) / 10)).toFixed(2);

                const box = document.createElement('div');
                box.className = 'annotation-box';
                box.style.top = `${topPct}%`;
                box.style.left = `${leftPct}%`;
                box.style.width = `${widthPct}%`;
                box.style.height = `${heightPct}%`;

                const tag = document.createElement('div');
                tag.className = 'annotation-tag';
                tag.innerHTML = `<i class="ph-fill ph-warning"></i> ${escapeHtml(label)}`;
                box.appendChild(tag);

                box.title = item.description || label;
                overlay.appendChild(box);

                chip.addEventListener('click', () => {
                    box.style.borderColor = '#ffffff';
                    setTimeout(() => { box.style.borderColor = '#ef4444'; }, 1000);
                });
            } else {
                const circle = document.createElement('div');
                circle.className = 'annotation-circle';
                circle.style.top = '50%';
                circle.style.left = '50%';
                circle.title = item.description || label;
                overlay.appendChild(circle);
            }
        });
    } else {
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-attention"><i class="ph-bold ph-shield-warning"></i> Flagged</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Image'}</span>
        `;
        findingsBar.classList.add('hidden');
    }
}

// ============================================================================
// ARGUS INTERACTIVE ONBOARDING TOUR ENGINE
// ============================================================================

class ArgusTourEngine {
    constructor() {
        this.currentStep = 0;
        this.isActive = false;
        this.isSimulating = false;
        this.simulationTimer = null;
        this.savedResults = [];
        this.savedActiveView = 'dashboard';

        this.maskEl = document.getElementById('tour-spotlight-mask');
        this.spotlightEl = document.getElementById('tour-spotlight-box');
        this.popoverEl = document.getElementById('tour-popover');
        this.badgeEl = document.getElementById('tour-step-badge');
        this.titleEl = document.getElementById('tour-title');
        this.bodyEl = document.getElementById('tour-body');
        this.dotsEl = document.getElementById('tour-dots');
        this.prevBtn = document.getElementById('tour-prev-btn');
        this.nextBtn = document.getElementById('tour-next-btn');
        this.skipBtn = document.getElementById('tour-skip-btn');
        this.closeBtn = document.getElementById('tour-close-btn');

        this.demoTextData = {
            file_path: 'C:\\Projects\\Sentinel_Core\\credentials.env',
            file_name: 'credentials.env',
            file_type: 'Env Secrets',
            content_type: 'text',
            checksum: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            reason: 'High-risk secret leak detected: AWS Access Key, Stripe Secret & Database Password',
            content: `# Argus Sentinel Development Environment Config\nPORT=8080\nNODE_ENV=production\n\n# Database Access Credentials\nDATABASE_URL=postgres://app_admin:P@ssw0rd_SuperSecret2026!@postgres.internal.net:5432/user_db\n\n# Cloud Service Keys\nAWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nAWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n\n# Payment & Authentication Tokens\nSTRIPE_SECRET_KEY=sk_test_51M0000000000000000000000000000000000000000000000000000000000\nJWT_AUTH_SECRET=super_secret_jwt_hmac_sha256_token_string_9988\n`,
            highlights: [
                { line_number: 6, start_col: 13, end_col: 93, match_text: 'postgres://app_admin:P@ssw0rd_SuperSecret2026!@postgres.internal.net:5432/user_db', pattern_name: 'Database Password', source: 'regex' },
                { line_number: 9, start_col: 18, end_col: 38, match_text: 'AKIAIOSFODNN7EXAMPLE', pattern_name: 'AWS Access Key', source: 'regex' },
                { line_number: 10, start_col: 22, end_col: 62, match_text: 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', pattern_name: 'AWS Secret Key', source: 'regex' },
                { line_number: 13, start_col: 18, end_col: 84, match_text: 'sk_test_51M0000000000000000000000000000000000000000000000000000000000', pattern_name: 'Stripe Secret Key', source: 'regex' }
            ]
        };

        this.demoImageData = {
            file_path: 'C:\\Users\\User\\Documents\\identity_driver_license.png',
            file_name: 'identity_driver_license.png',
            file_type: 'PNG Image',
            content_type: 'image',
            checksum: '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4',
            reason: 'Vision AI detected Driver License with Photo ID, DL Number, Address & Signature',
            data: 'assets/demo-driver-license.png',
            items: [
                { label: 'Photo ID (Biometric Portrait)', box_2d: [350, 130, 700, 410], description: 'Primary facial recognition portrait' },
                { label: 'Driver License ID', box_2d: [360, 415, 410, 660], description: 'DL Number: 987654321' },
                { label: 'Full Legal Name', box_2d: [410, 415, 445, 680], description: 'Legal Name: ROSA HARMS' },
                { label: 'Date of Birth (DOB)', box_2d: [445, 415, 480, 655], description: 'DOB: 09/21/1990' },
                { label: 'Residential Address', box_2d: [505, 415, 565, 780], description: '123 SENTINEL WAY, SPRINGFIELD, CA 90210' },
                { label: 'Personal Signature', box_2d: [645, 575, 720, 875], description: 'Handwritten Signature: Rosa Harms' }
            ]
        };

        this.demoResults = [
            {
                file: 'C:\\Projects\\Sentinel_Core\\credentials.env',
                type: '.ENV',
                compromised: true,
                reason: 'AWS Credentials, Stripe Key & DB Password detected',
                needs_ai_verification: false,
                verified_true: true
            },
            {
                file: 'C:\\Users\\User\\Documents\\identity_driver_license.png',
                type: '.PNG',
                compromised: true,
                reason: 'Vision AI detected Driver License with SSN & Photo ID',
                needs_ai_verification: false,
                verified_true: true
            },
            {
                file: 'C:\\Users\\User\\Downloads\\quarterly_payroll.xlsx',
                type: '.XLSX',
                compromised: true,
                reason: 'Multiple Social Security Numbers (SSNs) and Employee Salaries',
                needs_ai_verification: true,
                verified_true: false
            }
        ];

        this.steps = [
            {
                id: 'welcome',
                view: 'dashboard',
                target: '#sidebar-logo-container',
                title: 'Welcome to Argus PII Guard',
                badge: 'Step 1 of 9',
                html: `
                    <p>Argus is your intelligent <strong>On-Device Privacy Sentinel</strong> designed to detect, verify, and neutralize data leaks before they cause harm.</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-lock-key" style="color:var(--argus-teal)"></i>
                            <div><strong>100% On-Device & Private:</strong> Zero cloud telemetry or external uploads. All AI models run locally on your machine.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-files" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Deep Multi-Format Auditing:</strong> Inspects documents, codebases, secrets, and images seamlessly.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-lightning" style="color:var(--argus-green)"></i>
                            <div><strong>High-Speed Smart Caching:</strong> Fast incremental scans that skip safe, unmodified files.</div>
                        </li>
                    </ul>
                    <div class="tour-highlight-box">
                        🚀 <em>Let's take a quick 1-minute guided tour to walk you through protecting your data.</em>
                    </div>
                `,
                nextText: 'Start Guided Tour →'
            },
            {
                id: 'folders',
                view: 'dashboard',
                target: '#target-folders-card',
                title: '1. Select Target Folders',
                badge: 'Step 2 of 9',
                html: `
                    <p>Select which directories or project workspaces you want Argus to guard and inspect.</p>
                    <p>Click the <strong><i class="ph-bold ph-plus-circle" style="color:var(--argus-teal)"></i> Add Folder</strong> button to choose local paths on your machine.</p>
                    <div class="tour-highlight-box">
                        <strong>Supported Formats:</strong><br>
                        PDFs, MS Word (.docx), Excel (.xlsx), PowerPoint (.pptx), Environment secrets (.env, .yaml, .sql), Code (.py, .js, .json), and Images (.jpg, .png, .heic).
                    </div>
                `,
                nextText: 'Next: Scan Modes →'
            },
            {
                id: 'scan-modes',
                view: 'dashboard',
                target: '#scan-card',
                title: '2. Launch Sentinel Inspection',
                badge: 'Step 3 of 9',
                html: `
                    <p>Argus provides two flexible inspection modes tailored to your workflow:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-lightning" style="color:var(--argus-teal)"></i>
                            <div><strong>Smart Scan (Default):</strong> Uses cryptographic SHA-256 checksum tracking to detect altered/modified files between scans while skipping untouched safe files—saving over <strong>95%</strong> scan time.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-arrows-clockwise" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Full Re-scan:</strong> Clears cache and performs exhaustive deep inspection from scratch.</div>
                        </li>
                    </ul>
                    <div class="tour-highlight-box">
                        ⚡ <em>Click <strong>Run Demo Scan</strong> below to watch the live Orbital Radar in action!</em>
                    </div>
                `,
                nextText: 'Run Demo Scan ⚡'
            },
            {
                id: 'radar-progress',
                view: 'dashboard',
                target: '#scan-progress-container',
                title: '3. Real-Time Radar & Engine Telemetry',
                badge: 'Step 4 of 9',
                html: `
                    <p>During scanning, the <strong>Sentinel Orbital Radar</strong> provides live telemetry as files are inspected:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-gauge" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Multi-Threaded Pipeline:</strong> Inspects files concurrently based on your system RAM profile.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-fast-forward" style="color:var(--argus-teal)"></i>
                            <div><strong>Instant Checksum Skipping:</strong> Unmodified safe files bypass expensive LLM calls automatically based on cryptographic integrity.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-warning-octagon" style="color:var(--danger)"></i>
                            <div><strong>Instant Leak Alerts:</strong> Flagged files are captured dynamically the moment they are detected.</div>
                        </li>
                    </ul>
                `,
                nextText: 'Next: Review Findings →'
            },
            {
                id: 'results-table',
                view: 'results',
                target: '#results-list',
                title: '4. Triage & Batch Remediation',
                badge: 'Step 5 of 9',
                html: `
                    <p>When sensitive data (such as API keys, SSNs, credit cards, or passwords) is detected, it is listed here for immediate action:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-eraser" style="color:var(--argus-teal)"></i>
                            <div><strong>Redact Selected:</strong> Sanitizes detected secrets in-place across checked files while preserving surrounding content.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-trash" style="color:var(--danger)"></i>
                            <div><strong>Move to Trash:</strong> Safely moves flagged files to your system Recycle Bin/Trash (recoverable).</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-shield-check" style="color:var(--argus-green)"></i>
                            <div><strong>Mark as Safe (.argusignore):</strong> Adds whitelist exceptions for false positives or intentional secrets.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-funnel" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Results Tabs &amp; Quick Search:</strong> Toggle between Active Findings and Resolved items, or filter in real time.</div>
                        </li>
                    </ul>
                    <div class="tour-highlight-box">
                        👉 <em>Click any file row to launch the Deep Remediation Inspector!</em>
                    </div>
                `,
                nextText: 'Next: Remediation Inspector →',
                onEnter: () => {
                    this.injectDemoResults();
                }
            },
            {
                id: 'deep-preview',
                view: 'results',
                target: '#preview-modal .modal-content',
                placement: 'right',
                title: '5. Deep Remediation Inspector &amp; Hotkeys',
                badge: 'Step 6 of 9',
                html: `
                    <p>The <strong>Argus Remediation Inspector</strong> provides full contextual control over every detected finding:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-list-numbers" style="color:var(--argus-teal)"></i>
                            <div><strong>Inline Finding Action Bars:</strong> Every flagged line features dedicated <kbd>R</kbd> Redact, <kbd>S</kbd> Safe, and <kbd>D</kbd> Trash buttons.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-keyboard" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Power-User Single-Key Shortcuts:</strong> Press <kbd>J</kbd>/<kbd>K</kbd> to jump between findings, <kbd>R</kbd> to redact, <kbd>S</kbd> to whitelist, or <kbd>D</kbd> to trash.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-arrows-clockwise" style="color:var(--argus-green)"></i>
                            <div><strong>Automatic 7-Day Backups:</strong> Pre-redaction originals are archived in <code>.argus_backups/</code> with 1-click restore.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-lock-key" style="color:var(--warning)"></i>
                            <div><strong>Permission &amp; Integrity Guard:</strong> Single-click elevation for read-only files and tamper detection.</div>
                        </li>
                    </ul>
                    <div style="display:flex; gap:8px; margin-top:12px;">
                        <button id="tour-preview-text-btn" class="btn btn-secondary btn-small" style="flex:1; font-size:12px;"><i class="ph-fill ph-file-code"></i> Preview Secrets (.env)</button>
                        <button id="tour-preview-img-btn" class="btn btn-secondary btn-small" style="flex:1; font-size:12px;"><i class="ph-fill ph-image"></i> Preview Vision AI (.png)</button>
                    </div>
                `,
                nextText: 'Next: Smart Secret Detection →',
                onEnter: () => {
                    const modal = document.getElementById('preview-modal');
                    if (modal) modal.classList.add('tour-preview-mode');
                    this.showDemoPreview('text');
                    setTimeout(() => {
                        const btnText = document.getElementById('tour-preview-text-btn');
                        const btnImg = document.getElementById('tour-preview-img-btn');
                        if (btnText) btnText.addEventListener('click', () => this.showDemoPreview('text'));
                        if (btnImg) btnImg.addEventListener('click', () => this.showDemoPreview('image'));
                    }, 50);
                },
                onLeave: () => {
                    const modal = document.getElementById('preview-modal');
                    if (modal) {
                        modal.classList.remove('tour-preview-mode');
                        modal.classList.add('hidden');
                    }
                }
            },
            {
                id: 'smart-secrets',
                view: 'results',
                target: '#tab-active-findings',
                title: '6. Smart Secret & Entropy Detection',
                badge: 'Step 7 of 9',
                html: `
                    <p>Argus now detects high-entropy digital credentials and secrets beyond standard PII:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-key" style="color:var(--argus-teal)"></i>
                            <div><strong>Multi-Tier Detection:</strong> Uses ultra-fast regex for known vendor keys (AWS, Stripe, OpenAI) and Shannon Entropy for generic tokens.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-eye-slash" style="color:var(--argus-green)"></i>
                            <div><strong>Memory-Safe Handling:</strong> Detected secrets are securely masked in memory instantly to prevent accidental logging or exposure.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-eraser" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Safe Remediation:</strong> In-place redaction replaces the sensitive token perfectly using positional masking without breaking file formatting.</div>
                        </li>
                    </ul>
                `,
                nextText: 'Next: Allowed Exceptions & Safety →'
            },
            {
                id: 'settings-config',
                view: 'settings',
                target: '#allowed-exceptions-card',
                title: '7. Allowed Exceptions &amp; Safety Preferences',
                badge: 'Step 8 of 9',
                html: `
                    <p>Customize your remediation safety rules and whitelisted exceptions:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-shield-check" style="color:var(--argus-teal)"></i>
                            <div><strong>Allowed Exceptions (.argusignore):</strong> Manage whitelisted files, paths, and match values to ignore in future scans.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-asterisk-simple" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Masking Style:</strong> Choose between standard <code>[REDACTED]</code>, format-preserving <code>XXX-XX-6789</code>, or <code>[CONFIDENTIAL]</code>.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-recycle" style="color:var(--argus-green)"></i>
                            <div><strong>Safe Deletion Target:</strong> Defaults to system Recycle Bin / Trash rather than permanent unrecoverable deletion.</div>
                        </li>
                    </ul>
                `,
                nextText: 'Next: Local Model Engine →'
            },
            {
                id: 'model-management',
                view: 'settings',
                target: '#model-provider-row',
                title: '8. Local Model Engine & Hardware Profiling',
                badge: 'Step 9 of 9',
                html: `
                    <p>Argus supports <strong>two AI inference engines</strong> for maximum flexibility:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-cloud-arrow-down" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Ollama Server:</strong> Connect to a local or remote Ollama instance with any compatible model.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-hard-drives" style="color:var(--argus-teal)"></i>
                            <div><strong>Built-in Local (GGUF):</strong> Load GGUF model files directly — no Ollama required. Point to a folder and load any model.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-star" style="color:var(--warning)"></i>
                            <div><strong>Hardware-Matched Recommendations:</strong> Argus detects your CPU, RAM, and GPU to suggest the best models for your machine.</div>
                        </li>
                    </ul>
                    <div class="tour-highlight-box" style="border-left-color: var(--argus-green);">
                        🎉 <strong>You're all set!</strong> Click below to start securing your local files.
                    </div>
                `,
                nextText: 'Finish Tour & Guard Files 🎉'
            }
        ];

        this.initEvents();
    }

    initEvents() {
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.exitTour());
        }
        if (this.skipBtn) {
            this.skipBtn.addEventListener('click', () => this.exitTour());
        }
        if (this.prevBtn) {
            this.prevBtn.addEventListener('click', () => this.prev());
        }
        if (this.nextBtn) {
            this.nextBtn.addEventListener('click', () => this.next());
        }

        window.addEventListener('resize', () => {
            if (this.isActive) {
                this.updatePosition();
            }
        });

        window.addEventListener('scroll', () => {
            if (this.isActive) {
                this.updatePosition();
            }
        }, true);

        window.addEventListener('keydown', (e) => {
            if (!this.isActive) return;
            if (e.key === 'Escape') {
                this.exitTour();
            } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
                if (!e.target.matches('input, select, textarea, button')) {
                    this.next();
                }
            } else if (e.key === 'ArrowLeft') {
                if (!e.target.matches('input, select, textarea, button')) {
                    this.prev();
                }
            }
        });
    }

    start() {
        this.isActive = true;
        this.savedActiveView = document.querySelector('.nav-item.active')?.getAttribute('data-target') || 'dashboard';
        this.savedResults = Array.isArray(currentResults) ? [...currentResults] : [];

        this.maskEl.classList.remove('hidden');
        this.spotlightEl.classList.remove('hidden');
        this.popoverEl.classList.remove('hidden');

        this.goToStep(0);
    }

    next() {
        if (this.currentStep === 2) {
            // "Scan Modes" step -> Launch demo scan simulation
            this.runDemoScan();
            return;
        }

        if (this.currentStep < this.steps.length - 1) {
            this.goToStep(this.currentStep + 1);
        } else {
            this.exitTour();
        }
    }

    prev() {
        if (this.currentStep > 0) {
            this.goToStep(this.currentStep - 1);
        }
    }

    goToStep(index) {
        if (index < 0 || index >= this.steps.length) return;

        const prevStep = this.steps[this.currentStep];
        if (prevStep && typeof prevStep.onLeave === 'function') {
            prevStep.onLeave();
        }

        this.currentStep = index;
        const step = this.steps[index];

        // Switch to the step's designated view
        if (step.view) {
            switchView(step.view);
        }

        // Run step enter callback if any
        if (typeof step.onEnter === 'function') {
            step.onEnter();
        }

        // Update Popover Content
        this.badgeEl.innerText = step.badge;
        this.titleEl.innerText = step.title;
        this.bodyEl.innerHTML = step.html;

        // Update Prev Button
        if (index === 0) {
            this.prevBtn.style.display = 'none';
        } else {
            this.prevBtn.style.display = 'inline-flex';
        }

        // Update Next Button
        this.nextBtn.innerHTML = `${step.nextText || 'Next <i class="ph ph-arrow-right"></i>'}`;
        this.nextBtn.disabled = false;

        // Render Dots
        this.renderDots();

        // Position Spotlight & Popover
        setTimeout(() => {
            this.updatePosition();
        }, 60);
    }

    renderDots() {
        if (!this.dotsEl) return;
        this.dotsEl.innerHTML = '';
        this.steps.forEach((s, idx) => {
            const dot = document.createElement('div');
            dot.className = `tour-dot ${idx === this.currentStep ? 'active' : ''}`;
            dot.title = s.title;
            dot.addEventListener('click', () => {
                if (!this.isSimulating) {
                    this.goToStep(idx);
                }
            });
            this.dotsEl.appendChild(dot);
        });
    }

    updatePosition() {
        if (!this.isActive) return;
        const step = this.steps[this.currentStep];
        if (!step) return;

        let targetEl = null;
        if (step.target) {
            targetEl = document.querySelector(step.target);
        }

        const padding = 10;
        let rect = null;

        if (targetEl && targetEl.offsetParent !== null) {
            rect = targetEl.getBoundingClientRect();
        } else {
            // Fallback: center in window
            rect = {
                top: window.innerHeight / 2 - 100,
                left: window.innerWidth / 2 - 200,
                width: 400,
                height: 200,
                bottom: window.innerHeight / 2 + 100,
                right: window.innerWidth / 2 + 200
            };
        }

        // Position Spotlight Box
        const spotTop = Math.max(0, rect.top - padding);
        const spotLeft = Math.max(0, rect.left - padding);
        const spotWidth = Math.min(window.innerWidth - spotLeft, rect.width + padding * 2);
        const spotHeight = Math.min(window.innerHeight - spotTop, rect.height + padding * 2);

        this.spotlightEl.style.top = `${spotTop}px`;
        this.spotlightEl.style.left = `${spotLeft}px`;
        this.spotlightEl.style.width = `${spotWidth}px`;
        this.spotlightEl.style.height = `${spotHeight}px`;

        // Position Popover Card
        const popoverWidth = Math.min(460, window.innerWidth - 36);
        const popoverHeight = this.popoverEl.offsetHeight || 320;

        let popTop = 0;
        let popLeft = 0;

        // Check if step has explicit placement preference
        if (step.placement === 'right' || step.id === 'deep-preview') {
            const gap = 20;
            // Position the tour card directly adjacent to the target/modal with a clean 20px gap
            popLeft = spotLeft + spotWidth + gap;
            
            // If it exceeds viewport bounds, clamp so it stays comfortably within window
            if (popLeft + popoverWidth > window.innerWidth - 18) {
                popLeft = Math.max(18, window.innerWidth - popoverWidth - 18);
            }
            
            // Vertically center the popover relative to the spotlight target, clamped in viewport
            popTop = spotTop + (spotHeight / 2) - (popoverHeight / 2);
            popTop = Math.max(20, Math.min(window.innerHeight - popoverHeight - 20, popTop));
        }
        else if (step.placement === 'bottom') {
            popTop = spotTop + spotHeight + 16;
            popLeft = spotLeft + (spotWidth / 2) - (popoverWidth / 2);
        }
        // Check if there is space below
        else if (window.innerHeight - (spotTop + spotHeight) > popoverHeight + 20) {
            popTop = spotTop + spotHeight + 16;
            popLeft = spotLeft + (spotWidth / 2) - (popoverWidth / 2);
        }
        // Check if there is space to the right
        else if (window.innerWidth - (spotLeft + spotWidth) > popoverWidth + 24) {
            popTop = spotTop + (spotHeight / 2) - (popoverHeight / 2);
            popLeft = spotLeft + spotWidth + 18;
        }
        // Check if there is space to the left
        else if (spotLeft > popoverWidth + 24) {
            popTop = spotTop + (spotHeight / 2) - (popoverHeight / 2);
            popLeft = spotLeft - popoverWidth - 18;
        }
        // Check if there is space above
        else if (spotTop > popoverHeight + 20) {
            popTop = spotTop - popoverHeight - 16;
            popLeft = spotLeft + (spotWidth / 2) - (popoverWidth / 2);
        }
        // Fallback: center in viewport
        else {
            popTop = Math.max(20, (window.innerHeight - popoverHeight) / 2);
            popLeft = Math.max(18, (window.innerWidth - popoverWidth) / 2);
        }

        // Clamp popover within viewport
        popLeft = Math.max(18, Math.min(window.innerWidth - popoverWidth - 18, popLeft));
        popTop = Math.max(18, Math.min(window.innerHeight - popoverHeight - 18, popTop));

        this.popoverEl.style.top = `${popTop}px`;
        this.popoverEl.style.left = `${popLeft}px`;
    }

    runDemoScan() {
        if (this.isSimulating) return;
        this.isSimulating = true;

        const progressContainer = document.getElementById('scan-progress-container');
        const startScanBtn = document.getElementById('start-scan-btn');
        const sidebarScanStatus = document.getElementById('sidebar-scan-status');

        progressContainer.classList.remove('hidden');
        startScanBtn.classList.add('hidden');
        sidebarScanStatus.classList.remove('hidden');

        this.nextBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Inspecting...';
        this.nextBtn.disabled = true;
        this.prevBtn.disabled = true;

        const fillEl = document.getElementById('scan-progress-fill');
        const scannedCountEl = document.getElementById('scan-scanned-count');
        const skippedCountEl = document.getElementById('scan-skipped-count');
        const flaggedCountEl = document.getElementById('scan-flagged-count');
        const currentFileEl = document.getElementById('scan-current-file');

        fillEl.style.width = '0%';
        scannedCountEl.innerText = '0 / 18';
        skippedCountEl.innerText = '(0 skipped)';
        flaggedCountEl.innerText = '0 flagged';
        currentFileEl.innerText = 'Initializing Sentinel Core...';

        // Animate progression
        const steps = [
            { pct: 25, scanned: 5, skipped: 12, flagged: 0, file: 'package.json (Skipped - Cache Hit)' },
            { pct: 55, scanned: 10, skipped: 12, flagged: 1, file: 'credentials.env (Flagged: AWS & Stripe Secret)' },
            { pct: 80, scanned: 15, skipped: 12, flagged: 2, file: 'identity_driver_license.png (Flagged: Vision AI)' },
            { pct: 100, scanned: 18, skipped: 12, flagged: 3, file: 'quarterly_payroll.xlsx (Flagged: SSNs)' }
        ];

        let idx = 0;
        const interval = setInterval(() => {
            if (idx < steps.length) {
                const s = steps[idx];
                fillEl.style.width = `${s.pct}%`;
                scannedCountEl.innerText = `${s.scanned} / 18`;
                skippedCountEl.innerText = `(${s.skipped} skipped)`;
                flaggedCountEl.innerText = `${s.flagged} flagged`;
                currentFileEl.innerText = `Inspecting: ${s.file}`;
                idx++;
            } else {
                clearInterval(interval);
                this.isSimulating = false;
                this.prevBtn.disabled = false;
                this.nextBtn.disabled = false;

                // Advance to radar telemetry step
                this.goToStep(3);
            }
        }, 550);
    }

    injectDemoResults() {
        currentResults = this.demoResults;
        const list = document.getElementById('results-list');
        if (list) {
            list.dataset.count = "-1";
            renderResultsUI(this.demoResults);
        }
    }

    showDemoPreview(type = 'text') {
        const modal = document.getElementById('preview-modal');
        const title = document.getElementById('preview-title');
        const subtitle = document.getElementById('preview-subtitle');

        if (this.isActive && this.steps[this.currentStep]?.id === 'deep-preview') {
            modal.classList.add('tour-preview-mode');
        }

        if (type === 'image') {
            currentPreviewFile = this.demoImageData.file_path;
            title.innerText = this.demoImageData.file_name;
            title.setAttribute('title', this.demoImageData.file_path);
            subtitle.innerText = this.demoImageData.file_path;
            const iconContainer = document.getElementById('preview-file-icon');
            iconContainer.innerHTML = '<i class="ph-fill ph-image" style="color:var(--argus-teal)"></i>';
            renderImagePreview(this.demoImageData);
        } else {
            currentPreviewFile = this.demoTextData.file_path;
            title.innerText = this.demoTextData.file_name;
            title.setAttribute('title', this.demoTextData.file_path);
            subtitle.innerText = this.demoTextData.file_path;
            const iconContainer = document.getElementById('preview-file-icon');
            iconContainer.innerHTML = '<i class="ph-fill ph-file-code" style="color:var(--argus-teal)"></i>';
            renderTextPreview(this.demoTextData);
        }

        modal.classList.remove('hidden');
        setTimeout(() => {
            this.updatePosition();
        }, 80);
    }

    exitTour() {
        this.isActive = false;
        this.isSimulating = false;

        // Hide overlay elements
        this.maskEl.classList.add('hidden');
        this.spotlightEl.classList.add('hidden');
        this.popoverEl.classList.add('hidden');

        // Close preview modal if open
        const modal = document.getElementById('preview-modal');
        if (modal) {
            modal.classList.remove('tour-preview-mode');
            modal.classList.add('hidden');
        }

        // Reset scan progress & summary containers
        resetMainScreen();

        // Restore active view & real results
        switchView(this.savedActiveView || 'dashboard');
        if (window.pywebview?.api?.get_results) {
            loadResults();
        } else if (Array.isArray(this.savedResults)) {
            currentResults = this.savedResults;
            renderResultsUI(this.savedResults);
        }

        // Mark tour completed in persistent local storage & Python settings.json on disk
        localStorage.setItem('argus_tour_completed', 'true');
        if (window.pywebview?.api?.get_settings && window.pywebview?.api?.save_settings) {
            window.pywebview.api.get_settings().then(settings => {
                if (settings) {
                    settings.tour_completed = true;
                    window.pywebview.api.save_settings(settings);
                }
            }).catch(err => console.error("Error saving tour completion to disk:", err));
        }
    }
}

// ============================================================================
// MAIN APPLICATION INITIALIZER
// ============================================================================

function initApp() {
    if (window.appInitialized) return;
    window.appInitialized = true;

    try {
        // Theme Management
        initTheme();

        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = e.currentTarget.getAttribute('data-target');
                if (targetId) {
                    switchView(targetId);
                }
            });
        });

        // Initialize Onboarding Tour Engine
        window.argusTour = new ArgusTourEngine();

        const sidebarTourBtn = document.getElementById('sidebar-tour-btn');
        if (sidebarTourBtn) {
            sidebarTourBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (window.argusTour) window.argusTour.start();
            });
        }

        // Dashboard - Folders
        const addFolderBtn = document.getElementById('add-folder-btn');
        if (addFolderBtn) {
            addFolderBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api?.select_folder) return;
                const folders = await pywebview.api.select_folder();
                if (folders && folders.length > 0) {
                    const settings = await pywebview.api.get_settings();
                    const newFolders = [...new Set([...settings.folders, ...folders])];
                    settings.folders = newFolders;
                    await pywebview.api.save_settings(settings);
                    renderFolders(newFolders);
                }
            });
        }

        // Load initial settings & check tour completion status
        if (window.pywebview?.api) {
            pywebview.api.get_settings().then(settings => {
                renderFolders(settings.folders || []);
                
                // Auto-launch tour ONLY on first-ever launch (if tour_completed is false on disk & local storage)
                const isTourDone = Boolean(settings.tour_completed) || localStorage.getItem('argus_tour_completed') === 'true';
                if (!isTourDone) {
                    setTimeout(() => {
                        if (window.argusTour) window.argusTour.start();
                    }, 600);
                }
                
                // Settings UI
                const addressInput = document.getElementById('ollama-address');
                const toggle = document.getElementById('schedule-toggle');
                const timeInput = document.getElementById('schedule-time');
                const timeRow = document.getElementById('time-setting-row');
                const autoDeleteToggle = document.getElementById('auto-delete-toggle');
                
                // Optimization UI Elements
                const concurrencySelect = document.getElementById('concurrency-select');
                const imageOptSelect = document.getElementById('image-optimization-select');
                const textModeSelect = document.getElementById('text-scan-mode-select');

                // Model Provider UI Elements
                const ollamaPanel = document.getElementById('ollama-provider-panel');
                const localPanel = document.getElementById('local-provider-panel');
                const ollamaVisionModel = document.getElementById('ollama-vision-model');
                const ollamaTextModel = document.getElementById('ollama-text-model');
                const modelsFolderPath = document.getElementById('models-folder-path');
                const redactionMaskSelect = document.getElementById('redaction-mask-select');
                const deletionModeSelect = document.getElementById('deletion-mode-select');
                
                if (addressInput) addressInput.value = settings.ollama_address || "http://127.0.0.1:11434";
                if (autoDeleteToggle) autoDeleteToggle.checked = settings.auto_delete || false;
                if (toggle) toggle.checked = settings.schedule?.enabled || false;
                if (timeInput) timeInput.value = settings.schedule?.time || "02:00";
                
                if (concurrencySelect) concurrencySelect.value = settings.concurrency || "auto";
                if (imageOptSelect) imageOptSelect.value = settings.image_optimization || "medium";
                if (textModeSelect) textModeSelect.value = settings.text_scan_mode || "regex_llm";

                if (redactionMaskSelect) redactionMaskSelect.value = settings.redaction_mask_pattern || "redacted";
                if (deletionModeSelect) deletionModeSelect.value = settings.deletion_mode || "trash";

                function formatAddedDate(addedAt) {
                    if (!addedAt) return 'N/A';
                    if (typeof addedAt === 'number') {
                        const ms = addedAt < 1e11 ? addedAt * 1000 : addedAt;
                        const d = new Date(ms);
                        return isNaN(d.getTime()) ? 'N/A' : d.toLocaleDateString();
                    }
                    const d = new Date(addedAt);
                    return isNaN(d.getTime()) ? String(addedAt) : d.toLocaleDateString();
                }

                // Load Allowed Exceptions
                async function loadAllowedExceptions() {
                    const listEl = document.getElementById('exceptions-list');
                    if (!listEl || !pywebview.api.get_allowed_exceptions) return;
                    try {
                        const exceptions = await pywebview.api.get_allowed_exceptions();
                        if (!exceptions || exceptions.length === 0) {
                            listEl.innerHTML = '<div class="empty-exceptions-state"><i class="ph ph-shield"></i><p>No allowed exceptions configured yet.</p></div>';
                            return;
                        }
                        listEl.innerHTML = exceptions.map(ex => {
                            const targetStr = ex.target || ex.file || ex.filename || ex.match_text || 'Unknown target';
                            const typeStr = ex.type || (ex.match_text ? 'Match Pattern' : 'File Exception');
                            const dateStr = formatAddedDate(ex.added_at);
                            return `
                                <div class="exception-item" id="exception-${ex.id}">
                                    <div class="exception-details">
                                        <span class="exception-path" title="${escapeHtml(targetStr)}">${escapeHtml(targetStr)}</span>
                                        <div class="exception-meta">
                                            <span class="chip" style="font-size:10.5px; padding:1px 6px;">${escapeHtml(typeStr)}</span>
                                            ${ex.pattern_name ? `<span style="font-weight:600; color:var(--argus-teal);">${escapeHtml(ex.pattern_name)}</span>` : ''}
                                            <span>Added: ${dateStr}</span>
                                        </div>
                                    </div>
                                    <button class="btn-icon delete-exception-btn" data-id="${ex.id}" title="Remove rule and resume scanning this target">
                                        <i class="ph ph-trash" style="color:var(--danger)"></i>
                                    </button>
                                </div>
                            `;
                        }).join('');

                        listEl.querySelectorAll('.delete-exception-btn').forEach(btn => {
                            btn.addEventListener('click', async (e) => {
                                e.stopPropagation();
                                const id = btn.getAttribute('data-id');
                                if (pywebview.api.remove_allowed_exception) {
                                    await pywebview.api.remove_allowed_exception(id);
                                    await loadAllowedExceptions();
                                    loadResults();
                                }
                            });
                        });
                    } catch (e) {
                        console.error('Error loading exceptions:', e);
                    }
                }
                loadAllowedExceptions();

                const refreshExceptionsBtn = document.getElementById('refresh-exceptions-btn');
                if (refreshExceptionsBtn) {
                    refreshExceptionsBtn.addEventListener('click', loadAllowedExceptions);
                }

                const pruneBackupsBtn = document.getElementById('prune-backups-btn');
                if (pruneBackupsBtn) {
                    pruneBackupsBtn.addEventListener('click', async () => {
                        if (pywebview.api.prune_backups) {
                            pruneBackupsBtn.disabled = true;
                            pruneBackupsBtn.innerHTML = '<i class="ph ph-spinner spin"></i> Pruning...';
                            const res = await pywebview.api.prune_backups(7);
                            pruneBackupsBtn.disabled = false;
                            pruneBackupsBtn.innerHTML = '<i class="ph ph-broom"></i> Prune Old Backups';
                            alert(`Pruned ${res?.pruned_count || 0} backup files older than 7 days.`);
                        }
                    });
                }

                // Model provider init
                if (ollamaVisionModel) ollamaVisionModel.value = settings.vision_model_name || "gemma4:12b";
                if (ollamaTextModel) ollamaTextModel.value = settings.text_model_name || "gemma4:12b";
                if (modelsFolderPath && settings.models_folder) {
                    modelsFolderPath.textContent = settings.models_folder;
                    modelsFolderPath.title = settings.models_folder;
                }

                // Set initial provider radio
                const providerRadios = document.querySelectorAll('input[name="model-provider"]');
                const currentProvider = settings.model_provider || 'ollama';
                providerRadios.forEach(r => {
                    r.checked = r.value === currentProvider;
                });

                // Show correct panel
                function updateProviderPanels(provider) {
                    if (ollamaPanel) ollamaPanel.classList.toggle('hidden', provider !== 'ollama');
                    if (localPanel) localPanel.classList.toggle('hidden', provider !== 'local_gguf');
                }
                updateProviderPanels(currentProvider);

                // Provider toggle handler
                providerRadios.forEach(radio => {
                    radio.addEventListener('change', (e) => {
                        updateProviderPanels(e.target.value);
                    });
                });
                
                if (timeRow && toggle) {
                    timeRow.style.opacity = toggle.checked ? "1" : "0.5";
                    timeRow.style.pointerEvents = toggle.checked ? "auto" : "none";

                    toggle.addEventListener('change', (e) => {
                        timeRow.style.opacity = e.target.checked ? "1" : "0.5";
                        timeRow.style.pointerEvents = e.target.checked ? "auto" : "none";
                    });
                }

                // ---------------------------------------------------------
                // Hardware Specs Display
                // ---------------------------------------------------------
                if (pywebview.api.get_hardware_specs) {
                    pywebview.api.get_hardware_specs().then(specs => {
                        if (specs && !specs.error) {
                            const cpuEl = document.getElementById('hw-cpu-name');
                            const coresEl = document.getElementById('hw-cpu-cores');
                            const ramTotalEl = document.getElementById('hw-ram-total');
                            const ramAvailEl = document.getElementById('hw-ram-available');
                            const gpuEl = document.getElementById('hw-gpu-name');
                            const vramEl = document.getElementById('hw-gpu-vram');

                            if (cpuEl) cpuEl.textContent = specs.cpu_name || 'Unknown';
                            if (coresEl) coresEl.textContent = `${specs.cpu_cores}C / ${specs.cpu_threads}T`;
                            if (ramTotalEl) ramTotalEl.textContent = `${specs.ram_total_gb} GB`;
                            if (ramAvailEl) ramAvailEl.textContent = `${specs.ram_available_gb} GB`;
                            if (gpuEl) gpuEl.textContent = specs.gpu_name || 'No GPU detected';
                            if (vramEl) vramEl.textContent = specs.gpu_vram_gb ? `${specs.gpu_vram_gb} GB` : 'N/A';
                        }
                    }).catch(err => console.error("Error loading hardware specs:", err));
                }

                // State tracking for discovered local model files & cached recommendations
                const discoveredModelFiles = new Set();
                let cachedRecommendedData = null;

                // ---------------------------------------------------------
                // Recommended Models
                // ---------------------------------------------------------
                function renderRecommendedModels(data) {
                    const grid = document.getElementById('recommended-models-grid');
                    if (!grid || !data || data.error) return;

                    cachedRecommendedData = data;
                    const models = data.models || [];
                    if (models.length === 0) {
                        grid.innerHTML = '<div class="empty-models-state"><i class="ph ph-warning"></i><p>No model recommendations available</p></div>';
                        return;
                    }

                    grid.innerHTML = models.map(m => {
                        const tierClass = m.fit_tier.toLowerCase().replace(' ', '-');
                        const badgeClass = `fit-badge-${tierClass}`;
                        const cardClass = m.fit_tier === 'Too Large' ? 'fit-too-large' : '';
                        const isInstalled = discoveredModelFiles.has(m.filename.toLowerCase());
                        const safeId = m.filename.replace(/[^a-z0-9]/gi, '-');
                        const cardId = `rec-card-${safeId}`;

                        return `
                            <div class="rec-model-card ${cardClass}" id="${cardId}">
                                <div class="rec-model-top">
                                    <span class="rec-model-name">${m.name}</span>
                                    <span class="fit-badge ${badgeClass}">${m.fit_tier} ${m.fit_score > 0 ? m.fit_score : ''}</span>
                                </div>
                                <div class="rec-model-desc">${m.description}</div>
                                <div class="rec-model-meta">
                                    <span class="rec-model-tag">${m.params_b}B params</span>
                                    <span class="rec-model-tag">${m.quant}</span>
                                    <span class="rec-model-tag">${m.size_gb} GB</span>
                                    ${m.vision ? '<span class="rec-model-tag rec-model-tag-vision"><i class="ph-fill ph-eye"></i> Vision</span>' : ''}
                                    <span class="rec-model-tag">Min ${m.min_ram_gb}GB RAM</span>
                                </div>
                                <div class="rec-model-actions">
                                    <a href="${m.url}" target="_blank" class="rec-model-link" title="Open on HuggingFace">
                                        <i class="ph ph-arrow-square-out"></i> HuggingFace
                                    </a>
                                    ${isInstalled ? `
                                        <span class="rec-model-installed-badge"><i class="ph-fill ph-check-circle"></i> Installed</span>
                                    ` : `
                                        <button class="btn btn-primary btn-small rec-model-install-btn" 
                                                data-filename="${m.filename}" 
                                                data-url="${m.download_url || m.url}">
                                            <i class="ph ph-download-simple"></i> Install
                                        </button>
                                    `}
                                </div>
                                <div class="rec-download-progress hidden" id="prog-${cardId}">
                                    <div class="rec-download-bar-track">
                                        <div class="rec-download-bar-fill"></div>
                                    </div>
                                    <div class="rec-download-text">
                                        <span class="dl-status-label">Downloading...</span>
                                        <span class="dl-percent-label">0%</span>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');

                    // Attach Install click listeners
                    grid.querySelectorAll('.rec-model-install-btn').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            e.stopPropagation();
                            const filename = btn.getAttribute('data-filename');
                            const downloadUrl = btn.getAttribute('data-url');
                            if (!filename || !downloadUrl) return;

                            // If models_folder is empty, prompt user to select folder
                            if (!settings.models_folder) {
                                if (pywebview.api.select_models_folder) {
                                    const folder = await pywebview.api.select_models_folder();
                                    if (folder) {
                                        settings.models_folder = folder;
                                        if (modelsFolderPath) {
                                            modelsFolderPath.textContent = folder;
                                            modelsFolderPath.title = folder;
                                        }
                                    } else {
                                        return; // user cancelled folder prompt
                                    }
                                } else {
                                    alert("Please select a models folder first.");
                                    return;
                                }
                            }

                            btn.disabled = true;
                            btn.innerHTML = '<i class="ph ph-spinner spin"></i> Starting...';

                            const res = await pywebview.api.download_recommended_model(filename, downloadUrl);
                            if (res && res.prompt_folder) {
                                const folder = await pywebview.api.select_models_folder();
                                if (folder) {
                                    settings.models_folder = folder;
                                    if (modelsFolderPath) {
                                        modelsFolderPath.textContent = folder;
                                        modelsFolderPath.title = folder;
                                    }
                                    await pywebview.api.download_recommended_model(filename, downloadUrl);
                                } else {
                                    btn.disabled = false;
                                    btn.innerHTML = '<i class="ph ph-download-simple"></i> Install';
                                    return;
                                }
                            } else if (res && !res.success) {
                                alert("Failed to start download: " + (res.error || res.message));
                                btn.disabled = false;
                                btn.innerHTML = '<i class="ph ph-download-simple"></i> Install';
                                return;
                            }

                            // Start status telemetry polling
                            const safeId = filename.replace(/[^a-z0-9]/gi, '-');
                            const cardId = `rec-card-${safeId}`;
                            const progEl = document.getElementById(`prog-${cardId}`);
                            if (progEl) progEl.classList.remove('hidden');

                            const pollInterval = setInterval(async () => {
                                if (!pywebview.api.get_model_download_status) return;
                                const status = await pywebview.api.get_model_download_status();
                                if (!status) return;

                                if (progEl) {
                                    const bar = progEl.querySelector('.rec-download-bar-fill');
                                    const label = progEl.querySelector('.dl-status-label');
                                    const percent = progEl.querySelector('.dl-percent-label');

                                    if (bar) bar.style.width = `${status.percent || 0}%`;
                                    if (percent) percent.textContent = `${status.percent || 0}% (${status.speed_mbps || 0} MB/s)`;

                                    if (status.status === 'downloading') {
                                        if (label) label.textContent = `Downloading ${filename}...`;
                                    } else if (status.status === 'completed') {
                                        clearInterval(pollInterval);
                                        if (label) label.textContent = 'Download Complete!';
                                        setTimeout(async () => {
                                            progEl.classList.add('hidden');
                                            if (pywebview.api.scan_models_folder) {
                                                const scanRes = await pywebview.api.scan_models_folder(settings.models_folder);
                                                if (scanRes && !scanRes.error) {
                                                    renderLocalModels(scanRes.models);
                                                }
                                            }
                                        }, 1000);
                                    } else if (status.status === 'error' || status.status === 'cancelled') {
                                        clearInterval(pollInterval);
                                        if (label) label.textContent = `Error: ${status.error || status.status}`;
                                        btn.disabled = false;
                                        btn.innerHTML = '<i class="ph ph-download-simple"></i> Install';
                                    }
                                }
                            }, 500);
                        });
                    });
                }

                if (pywebview.api.get_recommended_models) {
                    pywebview.api.get_recommended_models().then(data => {
                        renderRecommendedModels(data);
                    }).catch(err => console.error("Error loading recommendations:", err));
                }

                const refreshRecsBtn = document.getElementById('refresh-recommendations-btn');
                if (refreshRecsBtn) {
                    refreshRecsBtn.addEventListener('click', async () => {
                        if (pywebview.api.get_recommended_models) {
                            const data = await pywebview.api.get_recommended_models();
                            renderRecommendedModels(data);
                        }
                    });
                }

                // ---------------------------------------------------------
                // Local Models — Browse, Scan, Load, Unload
                // ---------------------------------------------------------
                function renderLocalModels(models) {
                    const list = document.getElementById('local-models-list');
                    if (!list) return;

                    discoveredModelFiles.clear();
                    if (Array.isArray(models)) {
                        models.forEach(m => {
                            if (m.filename) discoveredModelFiles.add(m.filename.toLowerCase());
                        });
                    }

                    // Re-render recommendations to update Installed badges
                    if (cachedRecommendedData) {
                        renderRecommendedModels(cachedRecommendedData);
                    }

                    if (!models || models.length === 0) {
                        list.innerHTML = '<div class="empty-models-state"><i class="ph ph-file-dashed"></i><p>No .gguf model files found in this folder</p></div>';
                        return;
                    }

                    list.innerHTML = models.map(m => `
                        <div class="local-model-item" data-path="${m.path}">
                            <span class="local-model-name" title="${m.filename}">${m.filename}</span>
                            <span class="local-model-size">${m.size_gb} GB</span>
                            <button class="local-model-load-btn" data-path="${m.path}" title="Load this model">Load</button>
                        </div>
                    `).join('');

                    // Attach load handlers
                    list.querySelectorAll('.local-model-load-btn').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            e.stopPropagation();
                            const modelPath = e.currentTarget.getAttribute('data-path');
                            if (!modelPath || !pywebview.api.load_local_model) return;
                            btn.textContent = 'Loading...';
                            btn.disabled = true;
                            const result = await pywebview.api.load_local_model(modelPath);
                            if (result && result.success) {
                                updateLoadStatus(result.info);
                            } else {
                                alert('Failed to load model: ' + (result?.error || 'Unknown error'));
                            }
                            btn.textContent = 'Load';
                            btn.disabled = false;
                        });
                    });
                }

                function updateLoadStatus(info) {
                    const statusEl = document.getElementById('model-load-status');
                    const nameEl = document.getElementById('loaded-model-name');
                    if (!statusEl) return;

                    if (info && info.status === 'loaded') {
                        statusEl.classList.remove('hidden');
                        if (nameEl) nameEl.textContent = info.filename || 'Model loaded';
                    } else {
                        statusEl.classList.add('hidden');
                        if (nameEl) nameEl.textContent = 'No model loaded';
                    }
                }

                // Browse models folder
                const browseBtn = document.getElementById('browse-models-folder-btn');
                if (browseBtn) {
                    browseBtn.addEventListener('click', async () => {
                        if (!pywebview.api.select_models_folder) return;
                        const folder = await pywebview.api.select_models_folder();
                        if (folder) {
                            if (modelsFolderPath) {
                                modelsFolderPath.textContent = folder;
                                modelsFolderPath.title = folder;
                            }
                            // Scan for models
                            if (pywebview.api.scan_models_folder) {
                                const result = await pywebview.api.scan_models_folder(folder);
                                if (result && !result.error) {
                                    renderLocalModels(result.models);
                                }
                            }
                        }
                    });
                }

                // Refresh models list
                const refreshModelsBtn = document.getElementById('refresh-models-btn');
                if (refreshModelsBtn) {
                    refreshModelsBtn.addEventListener('click', async () => {
                        if (pywebview.api.scan_models_folder) {
                            const result = await pywebview.api.scan_models_folder();
                            if (result && !result.error) {
                                renderLocalModels(result.models);
                            }
                        }
                    });
                }

                // Unload model
                const unloadBtn = document.getElementById('unload-model-btn');
                if (unloadBtn) {
                    unloadBtn.addEventListener('click', async () => {
                        if (pywebview.api.unload_local_model) {
                            await pywebview.api.unload_local_model();
                            updateLoadStatus(null);
                        }
                    });
                }

                // Check for already-loaded model
                if (pywebview.api.get_loaded_model_info) {
                    pywebview.api.get_loaded_model_info().then(info => {
                        if (info) updateLoadStatus(info);
                    }).catch(() => {});
                }

                // Auto-scan models folder if already set
                if (settings.models_folder && pywebview.api.scan_models_folder) {
                    pywebview.api.scan_models_folder(settings.models_folder).then(result => {
                        if (result && !result.error) {
                            renderLocalModels(result.models);
                        }
                    }).catch(() => {});
                }

                // ---------------------------------------------------------
                // Save Settings (expanded)
                // ---------------------------------------------------------
                const saveSettingsBtn = document.getElementById('save-settings-btn');
                if (saveSettingsBtn) {
                    saveSettingsBtn.addEventListener('click', async () => {
                        const currentSettings = pywebview.api.get_settings ? await pywebview.api.get_settings() : settings;
                        currentSettings.ollama_address = addressInput ? addressInput.value.trim() : "http://127.0.0.1:11434";
                        currentSettings.auto_delete = autoDeleteToggle ? autoDeleteToggle.checked : false;
                        currentSettings.schedule = {
                            enabled: toggle ? toggle.checked : false,
                            time: timeInput ? timeInput.value : "02:00"
                        };
                        
                        currentSettings.concurrency = concurrencySelect ? concurrencySelect.value : "auto";
                        currentSettings.image_optimization = imageOptSelect ? imageOptSelect.value : "medium";
                        currentSettings.text_scan_mode = textModeSelect ? textModeSelect.value : "regex_llm";

                        currentSettings.redaction_mask_pattern = redactionMaskSelect ? redactionMaskSelect.value : "redacted";
                        currentSettings.deletion_mode = deletionModeSelect ? deletionModeSelect.value : "trash";

                        // Model provider settings
                        const selectedProvider = document.querySelector('input[name="model-provider"]:checked');
                        currentSettings.model_provider = selectedProvider ? selectedProvider.value : "ollama";

                        // Ollama model names
                        currentSettings.vision_model_name = ollamaVisionModel ? ollamaVisionModel.value.trim() : "gemma4:12b";
                        currentSettings.text_model_name = ollamaTextModel ? ollamaTextModel.value.trim() : "gemma4:12b";

                        // Models folder (already saved on browse, but capture current state)
                        if (modelsFolderPath && modelsFolderPath.textContent !== 'No folder selected') {
                            currentSettings.models_folder = modelsFolderPath.textContent;
                        }
                        
                        await pywebview.api.save_settings(currentSettings);
                        alert('Argus Configuration saved successfully.');
                    });
                }
            }).catch(e => console.error("Error loading settings:", e));
        }

        // Scanning
        const startScanBtn = document.getElementById('start-scan-btn');
        if (startScanBtn) {
            startScanBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api) return;
                
                // First check and start Ollama if needed
                const ollamaStatus = await pywebview.api.check_ollama();
                if (!ollamaStatus.success) {
                    alert("Ollama Error: " + ollamaStatus.message);
                    return;
                }

                const modeInput = document.querySelector('input[name="scan-mode"]:checked');
                const rescanAll = modeInput ? modeInput.value === "full" : false;
                
                startScanBtn.disabled = true;
                const origHtml = startScanBtn.innerHTML;
                startScanBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Initializing...';

                try {
                    const res = await pywebview.api.start_scan(rescanAll);
                    const isSuccess = (res === true) || (res && res.success === true);
                    
                    if (isSuccess) {
                        const summaryContainer = document.getElementById('scan-summary-container');
                        if (summaryContainer) summaryContainer.classList.add('hidden');
                        const modeOptions = document.getElementById('scan-mode-options');
                        if (modeOptions) modeOptions.classList.add('hidden');

                        const prog = document.getElementById('scan-progress-container');
                        if (prog) prog.classList.remove('hidden');
                        const scanStatus = document.getElementById('sidebar-scan-status');
                        if (scanStatus) scanStatus.classList.remove('hidden');
                        startScanBtn.classList.add('hidden');
                        lastScanStats = { scanned_files: 0, flagged_count: 0 };
                        startProgressPolling();
                    } else {
                        const msg = (res && res.message) ? res.message : 'Please add at least one directory to inspect first.';
                        alert(msg);
                    }
                } finally {
                    startScanBtn.disabled = false;
                    startScanBtn.innerHTML = origHtml;
                }
            });
        }

        // Requirement 2: Okay button resets main screen
        const scanSummaryOkBtn = document.getElementById('scan-summary-ok-btn');
        if (scanSummaryOkBtn) {
            scanSummaryOkBtn.addEventListener('click', () => {
                resetMainScreen();
            });
        }

        // View Flagged Files button -> switches view to 'results' (Detections & Reports)
        const scanSummaryViewBtn = document.getElementById('scan-summary-view-btn');
        if (scanSummaryViewBtn) {
            scanSummaryViewBtn.addEventListener('click', () => {
                resetMainScreen();
                switchView('results');
            });
        }

        const stopScanBtn = document.getElementById('stop-scan-btn');
        if (stopScanBtn) {
            stopScanBtn.addEventListener('click', async () => {
                stopScanBtn.disabled = true;
                const origHtml = stopScanBtn.innerHTML;
                stopScanBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Aborting...';

                if (window.pywebview?.api?.stop_scan) {
                    await pywebview.api.stop_scan();
                }

                // Poll briefly until backend is_scanning is confirmed false
                let attempts = 0;
                while (attempts < 15) {
                    try {
                        const prog = await pywebview.api.get_scan_progress();
                        if (!prog || !prog.is_scanning) break;
                    } catch (e) {
                        break;
                    }
                    await new Promise(r => setTimeout(r, 150));
                    attempts++;
                }

                stopScanBtn.disabled = false;
                stopScanBtn.innerHTML = origHtml;
                stopProgressPolling();
            });
        }

        // Results Tabs & Search Filter
        const tabActive = document.getElementById('tab-active-findings');
        const tabResolved = document.getElementById('tab-resolved-findings');
        if (tabActive && tabResolved) {
            tabActive.addEventListener('click', () => {
                currentResultsTab = 'active';
                tabActive.classList.add('active');
                tabResolved.classList.remove('active');
                renderResultsUI(currentResults);
            });
            tabResolved.addEventListener('click', () => {
                currentResultsTab = 'resolved';
                tabResolved.classList.add('active');
                tabActive.classList.remove('active');
                renderResultsUI(currentResults);
            });
        }

        const searchInput = document.getElementById('results-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                resultsSearchQuery = e.target.value.trim();
                renderResultsUI(currentResults);
            });
        }

        // Results Actions
        const refreshBtn = document.getElementById('refresh-results-btn');
        if (refreshBtn) refreshBtn.addEventListener('click', loadResults);
        
        const selectAllCb = document.getElementById('select-all-checkbox');
        if (selectAllCb) {
            selectAllCb.addEventListener('change', (e) => {
                const isChecked = e.target.checked;
                document.querySelectorAll('.result-checkbox').forEach(cb => {
                    cb.checked = isChecked;
                });
            });
        }

        // Batch Redact Selected
        const batchRedactSelectedBtn = document.getElementById('batch-redact-selected-btn');
        if (batchRedactSelectedBtn) {
            batchRedactSelectedBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api) return;
                const selectedFiles = [];
                document.querySelectorAll('.result-checkbox:checked').forEach(cb => {
                    selectedFiles.push(cb.getAttribute('data-file'));
                });

                if (selectedFiles.length === 0) {
                    alert('Please select at least one file to redact.');
                    return;
                }

                batchRedactSelectedBtn.disabled = true;
                batchRedactSelectedBtn.innerHTML = '<i class="ph ph-spinner spin"></i> Redacting...';

                for (const file of selectedFiles) {
                    if (pywebview.api.batch_redact) {
                        await pywebview.api.batch_redact(file);
                    }
                }

                batchRedactSelectedBtn.disabled = false;
                batchRedactSelectedBtn.innerHTML = '<i class="ph-bold ph-eraser"></i> Redact Selected';
                loadResults();
            });
        }

        const markSelectedBtn = document.getElementById('mark-selected-ok-btn');
        if (markSelectedBtn) {
            markSelectedBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api) return;
                const selectedFiles = [];
                document.querySelectorAll('.result-checkbox:checked').forEach(cb => {
                    selectedFiles.push(cb.getAttribute('data-file'));
                });

                if (selectedFiles.length === 0) {
                    alert('Please select at least one file to mark as Safe.');
                    return;
                }
                
                for (const file of selectedFiles) {
                    if (pywebview.api.mark_as_safe) {
                        await pywebview.api.mark_as_safe(file);
                    } else {
                        await pywebview.api.mark_file_ok(file);
                    }
                }
                loadResults();
            });
        }

        const deleteSelectedBtn = document.getElementById('delete-selected-btn');
        if (deleteSelectedBtn) {
            deleteSelectedBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api) return;
                const selectedFiles = [];
                document.querySelectorAll('.result-checkbox:checked').forEach(cb => {
                    selectedFiles.push(cb.getAttribute('data-file'));
                });

                if (selectedFiles.length === 0) return;
                
                if (confirm(`Move ${selectedFiles.length} flagged files to Recycle Bin / Trash?`)) {
                    if (pywebview.api.batch_delete_files) {
                        await pywebview.api.batch_delete_files(selectedFiles);
                    } else {
                        await pywebview.api.delete_files(selectedFiles);
                    }
                    loadResults();
                }
            });
        }

        // Modal Header Batch Redact Button
        const modalBatchRedactBtn = document.getElementById('modal-batch-redact-btn');
        if (modalBatchRedactBtn) {
            modalBatchRedactBtn.addEventListener('click', async () => {
                if (!currentPreviewFile || !pywebview.api.batch_redact) return;
                modalBatchRedactBtn.disabled = true;
                modalBatchRedactBtn.innerHTML = '<i class="ph ph-spinner spin"></i> Redacting...';
                
                const res = await pywebview.api.batch_redact(currentPreviewFile, null, currentPreviewData?.checksum);
                modalBatchRedactBtn.disabled = false;
                modalBatchRedactBtn.innerHTML = '<i class="ph-bold ph-eraser"></i> Redact All in File';
                
                if (res && res.success) {
                    await showPreview(currentPreviewFile);
                    loadResults();
                } else if (res && res.error === 'file_modified') {
                    const alertBanner = document.getElementById('preview-alert-banner');
                    if (alertBanner) {
                        alertBanner.className = 'preview-alert-banner alert-modified';
                        alertBanner.innerHTML = `
                            <span><i class="ph-bold ph-warning"></i> <strong>File Modified:</strong> File was modified externally on disk.</span>
                            <button id="alert-reload-btn" class="btn btn-secondary btn-small"><i class="ph-bold ph-arrows-clockwise"></i> Reload Preview</button>
                        `;
                        alertBanner.classList.remove('hidden');
                        document.getElementById('alert-reload-btn')?.addEventListener('click', () => showPreview(currentPreviewFile));
                    }
                } else {
                    alert(res?.message || 'Redaction failed');
                }
            });
        }

        // Modal footer actions
        const modalMarkOkBtn = document.getElementById('modal-mark-ok-btn');
        if (modalMarkOkBtn) {
            modalMarkOkBtn.addEventListener('click', async () => {
                if (currentPreviewFile && window.pywebview?.api) {
                    if (pywebview.api.mark_as_safe) {
                        await pywebview.api.mark_as_safe(currentPreviewFile);
                    } else {
                        await pywebview.api.mark_file_ok(currentPreviewFile);
                    }
                    const modal = document.getElementById('preview-modal');
                    if (modal) modal.classList.add('hidden');
                    loadResults();
                }
            });
        }

        const modalDeleteBtn = document.getElementById('modal-delete-btn');
        if (modalDeleteBtn) {
            modalDeleteBtn.addEventListener('click', async () => {
                if (currentPreviewFile && window.pywebview?.api) {
                    const fileName = currentPreviewFile.split('\\').pop().split('/').pop();
                    if (confirm(`Move "${fileName}" to Recycle Bin / System Trash?`)) {
                        if (pywebview.api.delete_file_item) {
                            await pywebview.api.delete_file_item(currentPreviewFile);
                        } else {
                            await pywebview.api.delete_files([currentPreviewFile]);
                        }
                        const modal = document.getElementById('preview-modal');
                        if (modal) modal.classList.add('hidden');
                        loadResults();
                    }
                }
            });
        }

        // Modal close
        const closeBtn = document.querySelector('.close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                const modal = document.getElementById('preview-modal');
                if (modal) modal.classList.add('hidden');
            });
        }

        // ---------------------------------------------------------
        // Power Keyboard Shortcuts (R, D, S, J, K, Esc)
        // ---------------------------------------------------------
        window.addEventListener('keydown', async (e) => {
            // Ignore if typing inside input / textarea / select
            const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
            if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
                return;
            }

            const modal = document.getElementById('preview-modal');
            const isModalOpen = modal && !modal.classList.contains('hidden');

            if (isModalOpen) {
                if (e.key === 'Escape') {
                    modal.classList.add('hidden');
                    return;
                }

                if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (currentPreviewData && currentPreviewData.highlights && currentPreviewData.highlights.length > 0) {
                        focusFindingIndex(activeFindingIndex + 1);
                    }
                } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (currentPreviewData && currentPreviewData.highlights && currentPreviewData.highlights.length > 0) {
                        focusFindingIndex(activeFindingIndex - 1);
                    }
                } else if (e.key === 'r' || e.key === 'R') {
                    e.preventDefault();
                    if (currentPreviewData && currentPreviewData.highlights && currentPreviewData.highlights[activeFindingIndex]) {
                        await executeRedactFinding(currentPreviewData.highlights[activeFindingIndex]);
                    }
                } else if (e.key === 's' || e.key === 'S') {
                    e.preventDefault();
                    if (currentPreviewData && currentPreviewData.highlights && currentPreviewData.highlights[activeFindingIndex]) {
                        await executeMarkFindingSafe(currentPreviewData.highlights[activeFindingIndex]);
                    } else {
                        await executeMarkFindingSafe(null);
                    }
                } else if (e.key === 'd' || e.key === 'D') {
                    e.preventDefault();
                    await executeDeleteFile();
                }
            }
        });

        // Initial load of results to update Section 1 counter badge
        if (window.pywebview?.api?.get_results) {
            loadResults();
        }

    } catch (err) {
        console.error("Error initializing Argus application:", err);
    }
}

