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

function startProgressPolling() {
    if (scanInterval) clearInterval(scanInterval);
    scanInterval = setInterval(async () => {
        const data = await pywebview.api.get_scan_progress();
        
        if (data.flagged_files) {
            renderResultsUI(data.flagged_files);
        }

        if (!data.is_scanning) {
            stopProgressPolling();
            loadResults();
            return;
        }

        const p = data.progress;
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
        const fileName = filePath ? filePath.split('\\\\').pop().split('/').pop() : 'Inspecting...';
        document.getElementById('scan-current-file').innerText = fileName ? `Inspecting: ${fileName}` : 'Inspecting...';
        
    }, 800);
}

function stopProgressPolling() {
    if (scanInterval) clearInterval(scanInterval);
    document.getElementById('scan-progress-container').classList.add('hidden');
    document.getElementById('sidebar-scan-status').classList.add('hidden');
    document.getElementById('start-scan-btn').classList.remove('hidden');
}

async function loadResults() {
    const results = await pywebview.api.get_results();
    currentResults = results;
    document.getElementById('select-all-checkbox').checked = false;
    document.getElementById('results-list').dataset.count = "-1"; // Force render
    renderResultsUI(results);
}

function renderResultsUI(results) {
    const list = document.getElementById('results-list');
    
    // Optimization to prevent re-rendering when counts haven't changed
    if (list.dataset.count === String(results.length)) {
        return;
    }
    list.dataset.count = results.length;
    
    if (results.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="ph-fill ph-shield-check" style="font-size: 52px; color: var(--argus-teal);"></i>
                <p style="margin-top: 14px; font-weight: 700; font-size: 16px; color: var(--text-main);">All Inspected Files are SECURE</p>
                <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">No PII leaks or compromised data detected.</p>
            </div>
        `;
        return;
    }

    list.innerHTML = '';
    results.forEach(res => {
        const row = document.createElement('div');
        row.className = 'result-row';
        const isDeleted = res.auto_deleted;
        const needsVerification = res.needs_ai_verification;
        const isVerified = res.verified_true;
        
        let checkboxHtml = '';
        if (isDeleted) {
            checkboxHtml = `<span class="danger-text" style="font-size: 11px; font-weight: 700; white-space: nowrap; margin-left: -4px;">DELETED</span>`;
        } else {
            checkboxHtml = `<input type="checkbox" class="result-checkbox" data-file="${res.file.replace(/"/g, '&quot;')}">`;
        }
        
        // Status Badge from Argus Component Library
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
            actionsHtml += `<button class="mark-ok-btn" data-file="${res.file.replace(/"/g, '&quot;')}" title="Mark as false positive (clear & skip)"><i class="ph-bold ph-check"></i> Mark OK</button>`;
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

    // Add click handler for file preview
    document.querySelectorAll('.col-file:not(.deleted)').forEach(el => {
        el.addEventListener('click', async (e) => {
            const filePath = e.currentTarget.getAttribute('data-file');
            showPreview(filePath);
        });
    });

    // Add click handler for Mark OK buttons
    document.querySelectorAll('.mark-ok-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const filePath = e.currentTarget.getAttribute('data-file');
            await pywebview.api.mark_file_ok(filePath);
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

async function showPreview(filePath) {
    currentPreviewFile = filePath;
    const modal = document.getElementById('preview-modal');
    const body = document.getElementById('preview-body');
    const title = document.getElementById('preview-title');
    const subtitle = document.getElementById('preview-subtitle');
    const iconContainer = document.getElementById('preview-file-icon');
    const badgesContainer = document.getElementById('preview-badges');
    const findingsBar = document.getElementById('preview-findings-bar');
    const findingsChips = document.getElementById('preview-findings-chips');
    const reasonText = document.getElementById('preview-status-reason');

    const fileName = filePath.split('\\').pop().split('/').pop();
    title.innerText = fileName;
    title.setAttribute('title', filePath);
    subtitle.innerText = filePath;
    badgesContainer.innerHTML = '';
    findingsChips.innerHTML = '';
    findingsBar.classList.add('hidden');
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

    const highlights = previewData.highlights || [];
    const content = previewData.content || '';
    reasonText.innerText = previewData.reason || '';

    // Badges & Findings bar
    if (highlights.length > 0) {
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-leak"><i class="ph-bold ph-warning"></i> ${highlights.length} ${highlights.length === 1 ? 'Finding' : 'Findings'}</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Document'}</span>
        `;
        findingsBar.classList.remove('hidden');
        findingsChips.innerHTML = '';

        highlights.forEach(h => {
            const chip = document.createElement('button');
            chip.className = `finding-chip ${h.source === 'ai' ? 'chip-ai' : ''}`;
            const icon = h.source === 'ai' ? 'ph-magic-wand' : 'ph-crosshair';
            chip.innerHTML = `<i class="ph-bold ${icon}"></i> Line ${h.line_number}: ${escapeHtml(h.pattern_name)}`;
            chip.title = `Jump to line ${h.line_number} ("${h.match_text}")`;
            chip.addEventListener('click', () => {
                scrollToCodeLine(h.line_number);
            });
            findingsChips.appendChild(chip);
        });
    } else {
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-secure"><i class="ph-bold ph-check-circle"></i> Clean</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Document'}</span>
        `;
        findingsBar.classList.add('hidden');
    }

    // Render code viewer
    const lines = content.split('\n');
    const wrapper = document.createElement('div');
    wrapper.className = 'code-viewer-wrapper';
    wrapper.id = 'code-viewer-scroll-container';

    const table = document.createElement('div');
    table.className = 'code-viewer-table';

    const lineHighlightsMap = {};
    highlights.forEach(h => {
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
    });

    wrapper.appendChild(table);
    body.innerHTML = '';
    body.appendChild(wrapper);

    if (highlights.length > 0) {
        setTimeout(() => {
            scrollToCodeLine(highlights[0].line_number);
        }, 80);
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
        badgesContainer.innerHTML = `
            <span class="status-indicator badge-leak"><i class="ph-bold ph-eye"></i> ${items.length} ${items.length === 1 ? 'Detection' : 'Detections'}</span>
            <span class="chip" style="font-size:11px; padding:2px 8px;">${previewData.file_type || 'Image'}</span>
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
                badge: 'Step 1 of 8',
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
                badge: 'Step 2 of 8',
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
                badge: 'Step 3 of 8',
                html: `
                    <p>Argus provides two flexible inspection modes tailored to your workflow:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-lightning" style="color:var(--argus-teal)"></i>
                            <div><strong>Smart Scan (Default):</strong> Uses cryptographic SHA-256 state hashing to skip unmodified, verified files—saving over <strong>95%</strong> scan time.</div>
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
                badge: 'Step 4 of 8',
                html: `
                    <p>During scanning, the <strong>Sentinel Orbital Radar</strong> provides live telemetry as files are inspected:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-gauge" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>Multi-Threaded Pipeline:</strong> Inspects files concurrently based on your system RAM profile.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-fast-forward" style="color:var(--argus-teal)"></i>
                            <div><strong>Instant Cache Skipping:</strong> Unmodified safe files bypass expensive LLM calls automatically.</div>
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
                title: '4. Triage & Remediate Detections',
                badge: 'Step 5 of 8',
                html: `
                    <p>When sensitive data (such as API keys, SSNs, credit cards, or passwords) is detected, it is listed here:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-magic-wand" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>AI Verify:</strong> Triggers a high-precision secondary AI model to verify ambiguous regex pattern hits.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-check-circle" style="color:var(--argus-teal)"></i>
                            <div><strong>Mark OK (Whitelist):</strong> Marks false positives as safe. Argus remembers your decision permanently.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-trash" style="color:var(--danger)"></i>
                            <div><strong>Delete Selected:</strong> Safely purges compromised files from your disk.</div>
                        </li>
                    </ul>
                    <div class="tour-highlight-box">
                        👉 <em>Clicking any file row opens the Deep Visualizer preview!</em>
                    </div>
                `,
                nextText: 'Next: Deep Visualizer →',
                onEnter: () => {
                    this.injectDemoResults();
                }
            },
            {
                id: 'deep-preview',
                view: 'results',
                target: '#preview-modal .modal-content',
                placement: 'right',
                title: '5. Deep Visualizer & Bounding Boxes',
                badge: 'Step 6 of 8',
                html: `
                    <p>The <strong>Argus Deep Visualizer</strong> reveals the exact locations of detected PII leaks:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-highlighter" style="color:var(--warning)"></i>
                            <div><strong>Line-by-Line Regex Highlights:</strong> Text and code files highlight matched secrets with exact column precision.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-bounding-box" style="color:var(--danger)"></i>
                            <div><strong>Vision AI Bounding Boxes:</strong> Identifies ID cards, driver licenses, SSN numbers, and signatures on scanned photos.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-crosshair" style="color:var(--argus-teal)"></i>
                            <div><strong>Quick-Jump Finding Chips:</strong> Click any chip at the top to jump directly to the detection.</div>
                        </li>
                    </ul>
                    <div style="display:flex; gap:8px; margin-top:12px;">
                        <button id="tour-preview-text-btn" class="btn btn-secondary btn-small" style="flex:1; font-size:12px;"><i class="ph-fill ph-file-code"></i> Preview Secrets (.env)</button>
                        <button id="tour-preview-img-btn" class="btn btn-secondary btn-small" style="flex:1; font-size:12px;"><i class="ph-fill ph-image"></i> Preview Vision AI (.png)</button>
                    </div>
                `,
                nextText: 'Next: Settings & Hardware →',
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
                id: 'settings-config',
                view: 'settings',
                target: '#settings .settings-card',
                title: '6. Hardware Profiling & Automation',
                badge: 'Step 7 of 8',
                html: `
                    <p>Argus adapts to your computer's resources:</p>
                    <ul class="tour-feature-list">
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-cpu" style="color:var(--argus-periwinkle)"></i>
                            <div><strong>RAM Auto-Tuning:</strong> Automatically allocates parallel threads and optimal image downscaling (1024px) for your hardware.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-clock" style="color:var(--argus-teal)"></i>
                            <div><strong>Daily Scheduled Scans:</strong> Runs automated background sentinel sweeps at your chosen time.</div>
                        </li>
                        <li class="tour-feature-item">
                            <i class="ph-fill ph-shield-check" style="color:var(--argus-green)"></i>
                            <div><strong>Automatic Remediation:</strong> Option to automatically delete verified compromised files.</div>
                        </li>
                    </ul>
                `,
                nextText: 'Next: Local Model Engine →'
            },
            {
                id: 'model-management',
                view: 'settings',
                target: '#model-provider-row',
                title: '7. Local Model Engine & Recommendations',
                badge: 'Step 8 of 8',
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

        // Reset scan progress container
        const progressContainer = document.getElementById('scan-progress-container');
        const startScanBtn = document.getElementById('start-scan-btn');
        const sidebarScanStatus = document.getElementById('sidebar-scan-status');

        if (progressContainer) progressContainer.classList.add('hidden');
        if (startScanBtn) startScanBtn.classList.remove('hidden');
        if (sidebarScanStatus) sidebarScanStatus.classList.add('hidden');

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
                
                if (addressInput) addressInput.value = settings.ollama_address || "http://127.0.0.1:11434";
                if (autoDeleteToggle) autoDeleteToggle.checked = settings.auto_delete || false;
                if (toggle) toggle.checked = settings.schedule?.enabled || false;
                if (timeInput) timeInput.value = settings.schedule?.time || "02:00";
                
                if (concurrencySelect) concurrencySelect.value = settings.concurrency || "auto";
                if (imageOptSelect) imageOptSelect.value = settings.image_optimization || "medium";
                if (textModeSelect) textModeSelect.value = settings.text_scan_mode || "regex_llm";

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
                        settings.ollama_address = addressInput ? addressInput.value.trim() : "http://127.0.0.1:11434";
                        settings.auto_delete = autoDeleteToggle ? autoDeleteToggle.checked : false;
                        settings.schedule = {
                            enabled: toggle ? toggle.checked : false,
                            time: timeInput ? timeInput.value : "02:00"
                        };
                        
                        settings.concurrency = concurrencySelect ? concurrencySelect.value : "auto";
                        settings.image_optimization = imageOptSelect ? imageOptSelect.value : "medium";
                        settings.text_scan_mode = textModeSelect ? textModeSelect.value : "regex_llm";

                        // Model provider settings
                        const selectedProvider = document.querySelector('input[name="model-provider"]:checked');
                        settings.model_provider = selectedProvider ? selectedProvider.value : "ollama";

                        // Ollama model names
                        settings.vision_model_name = ollamaVisionModel ? ollamaVisionModel.value.trim() : "gemma4:12b";
                        settings.text_model_name = ollamaTextModel ? ollamaTextModel.value.trim() : "gemma4:12b";

                        // Models folder (already saved on browse, but capture current state)
                        if (modelsFolderPath && modelsFolderPath.textContent !== 'No folder selected') {
                            settings.models_folder = modelsFolderPath.textContent;
                        }
                        
                        await pywebview.api.save_settings(settings);
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
                const success = await pywebview.api.start_scan(rescanAll);
                if (success) {
                    const prog = document.getElementById('scan-progress-container');
                    if (prog) prog.classList.remove('hidden');
                    const scanStatus = document.getElementById('sidebar-scan-status');
                    if (scanStatus) scanStatus.classList.remove('hidden');
                    startScanBtn.classList.add('hidden');
                    startProgressPolling();
                } else {
                    alert('Please add at least one directory to inspect first.');
                }
            });
        }

        const stopScanBtn = document.getElementById('stop-scan-btn');
        if (stopScanBtn) {
            stopScanBtn.addEventListener('click', async () => {
                if (window.pywebview?.api?.stop_scan) {
                    await pywebview.api.stop_scan();
                }
                stopProgressPolling();
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

        const markSelectedBtn = document.getElementById('mark-selected-ok-btn');
        if (markSelectedBtn) {
            markSelectedBtn.addEventListener('click', async () => {
                if (!window.pywebview?.api) return;
                const selectedFiles = [];
                document.querySelectorAll('.result-checkbox:checked').forEach(cb => {
                    selectedFiles.push(cb.getAttribute('data-file'));
                });

                if (selectedFiles.length === 0) {
                    alert('Please select at least one file to mark as OK.');
                    return;
                }
                
                await pywebview.api.mark_files_ok(selectedFiles);
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
                
                if (confirm(`Permanently delete ${selectedFiles.length} flagged files from disk?`)) {
                    await pywebview.api.delete_files(selectedFiles);
                    loadResults();
                }
            });
        }

        // Modal actions
        const modalMarkOkBtn = document.getElementById('modal-mark-ok-btn');
        if (modalMarkOkBtn) {
            modalMarkOkBtn.addEventListener('click', async () => {
                if (currentPreviewFile && window.pywebview?.api) {
                    await pywebview.api.mark_file_ok(currentPreviewFile);
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
                    if (confirm(`Permanently delete "${fileName}"?`)) {
                        await pywebview.api.delete_files([currentPreviewFile]);
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

    } catch (err) {
        console.error("Error initializing Argus application:", err);
    }
}

