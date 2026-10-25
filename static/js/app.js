/**
 * CiteNest Academic Web Application - Frontend Controller
 * Implements client-side routing, API integration, paper editor with inline citations,
 * dynamic bibliography preview, and role-based views.
 */

class CiteNestApp {
  constructor() {
    this.currentUser = null;
    this.sessionId = localStorage.getItem('citenest_session_id') || null;
    this.currentView = 'dashboard';

    // State caches
    this.references = [];
    this.collections = [];
    this.documents = [];
    this.currentDocument = null;
    this.autoSaveTimer = null;
    this.lastSavedContent = '';

    // Bind event listeners
    this.init();
  }

  async init() {
    // Check if session exists
    if (this.sessionId) {
      const valid = await this.verifySession();
      if (valid) {
        this.navigateTo(this.currentUser.role === 'Administrator' ? 'dashboard' : 'dashboard');
      } else {
        this.navigateTo('auth');
      }
    } else {
      this.navigateTo('auth');
    }

    // Setup global click handler for inline citation delete buttons
    document.addEventListener('click', (e) => {
      if (e.target && e.target.classList.contains('cite-del-btn')) {
        e.preventDefault();
        e.stopPropagation();
        const token = e.target.closest('.citenest-citation');
        if (token && this.currentDocument) {
          const citationId = token.getAttribute('data-citation-id');
          if (citationId) {
            this.handleRemoveCitation(citationId);
          }
        }
      }
    });
  }

  // --- API Helper ---
  async api(endpoint, options = {}) {
    const headers = options.headers || {};
    if (this.sessionId) {
      headers['Authorization'] = `Bearer ${this.sessionId}`;
      headers['X-Session-ID'] = this.sessionId;
    }
    if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }
    options.headers = headers;

    try {
      const response = await fetch(endpoint, options);

      // Handle download responses
      const disposition = response.headers.get('Content-Disposition');
      if (disposition && disposition.includes('attachment')) {
        if (!response.ok) {
          const errData = await response.json();
          throw new Error(errData.detail || 'Download failed');
        }
        const blob = await response.blob();
        return { isBlob: true, blob, response };
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.message || 'API request failed');
      }
      return data;
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  }

  // --- Session & Auth (IAuth) ---
  async verifySession() {
    try {
      const res = await this.api('/api/auth/me');
      if (res.success && res.user) {
        this.currentUser = res.user;
        this.renderUserProfile();
        return true;
      }
    } catch (e) {
      this.sessionId = null;
      localStorage.removeItem('citenest_session_id');
      this.currentUser = null;
    }
    return false;
  }

  renderUserProfile() {
    const badge = document.getElementById('user-profile-badge');
    const links = document.getElementById('navbar-links');
    const adminLink = document.getElementById('nav-admin');

    if (this.currentUser) {
      badge.style.display = 'flex';
      links.style.display = 'flex';

      document.getElementById('user-display-name').textContent = this.currentUser.name;
      const initial = (this.currentUser.name || 'U').charAt(0).toUpperCase();
      document.getElementById('user-avatar-initial').textContent = initial;

      const roleBadge = document.getElementById('user-role-badge');
      roleBadge.textContent = this.currentUser.role;
      roleBadge.className = 'badge';
      if (this.currentUser.role === 'Student') roleBadge.classList.add('badge-student');
      else if (this.currentUser.role === 'Researcher/Faculty') roleBadge.classList.add('badge-researcher');
      else if (this.currentUser.role === 'Administrator') roleBadge.classList.add('badge-admin');

      // Admin tab visibility (BR-008)
      if (this.currentUser.role === 'Administrator') {
        adminLink.style.display = 'flex';
      } else {
        adminLink.style.display = 'none';
      }
    } else {
      badge.style.display = 'none';
      links.style.display = 'none';
      adminLink.style.display = 'none';
    }
  }

  async quickLogin(email, password) {
    document.getElementById('login-email').value = email;
    document.getElementById('login-password').value = password;
    this.switchAuthTab('login');
    await this.handleLogin(new Event('submit'));
  }

  async handleLogin(e) {
    if (e && e.preventDefault) e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errBox = document.getElementById('login-error-msg');
    errBox.style.display = 'none';

    try {
      const res = await this.api('/api/auth/login', {
        method: 'POST',
        body: { email, password }
      });

      if (res.success && res.user) {
        this.sessionId = res.user.sessionId;
        localStorage.setItem('citenest_session_id', this.sessionId);
        this.currentUser = res.user;
        this.renderUserProfile();
        this.showToast(`Welcome back, ${res.user.name}!`, 'success');
        this.navigateTo('dashboard');
      }
    } catch (err) {
      errBox.textContent = err.message || 'Invalid email or password';
      errBox.style.display = 'block';
    }
  }

  async handleRegister(e) {
    if (e) e.preventDefault();
    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value.trim();
    const role = document.getElementById('reg-role').value;
    const errBox = document.getElementById('reg-error-msg');
    errBox.style.display = 'none';

    try {
      const res = await this.api('/api/auth/register', {
        method: 'POST',
        body: { name, email, password, role }
      });

      if (res.success) {
        this.showToast('Registration successful! Please sign in.', 'success');
        this.switchAuthTab('login');
        document.getElementById('login-email').value = email;
        document.getElementById('login-password').value = password;
      }
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = 'block';
    }
  }

  async logout() {
    try {
      if (this.sessionId) {
        await this.api('/api/auth/logout', { method: 'POST' });
      }
    } catch (e) {
      console.warn('Logout notification error:', e);
    }
    this.sessionId = null;
    localStorage.removeItem('citenest_session_id');
    this.currentUser = null;
    this.renderUserProfile();
    this.showToast('Logged out successfully.', 'info');
    this.navigateTo('auth');
  }

  async resetDemoData() {
    if (!confirm('Reset CiteNest database to the standard Lab 4 Object Diagram & Annex F pre-seeded demo state?')) {
      return;
    }
    try {
      const res = await this.api('/api/auth/reset-demo', { method: 'POST' });
      this.showToast(res.message, 'success');
      // If logged in, refresh current view; otherwise prefill Aaryan
      if (this.sessionId && this.currentUser) {
        await this.refreshCurrentView();
      } else {
        this.quickLogin('aaryan@lnmiit.ac.in', 'password123');
      }
    } catch (err) {
      this.showToast(`Failed to reset demo: ${err.message}`, 'danger');
    }
  }

  switchAuthTab(tab) {
    const loginForm = document.getElementById('form-login');
    const regForm = document.getElementById('form-register');
    const tabLogin = document.getElementById('tab-auth-login');
    const tabReg = document.getElementById('tab-auth-register');

    if (tab === 'login') {
      loginForm.style.display = 'block';
      regForm.style.display = 'none';
      tabLogin.style.background = 'var(--primary)';
      tabLogin.style.color = 'white';
      tabReg.style.background = 'transparent';
      tabReg.style.color = 'var(--text-main)';
    } else {
      loginForm.style.display = 'none';
      regForm.style.display = 'block';
      tabReg.style.background = 'var(--primary)';
      tabReg.style.color = 'white';
      tabLogin.style.background = 'transparent';
      tabLogin.style.color = 'var(--text-main)';
    }
  }

  // --- View Routing ---
  async navigateTo(viewName) {
    // Protect views if unauthenticated
    if (!this.currentUser && viewName !== 'auth') {
      this.currentView = 'auth';
    } else {
      this.currentView = viewName;
    }

    const views = ['auth', 'dashboard', 'references', 'collections', 'editor', 'admin'];
    views.forEach(v => {
      const el = document.getElementById(`view-${v}`);
      if (el) el.style.display = (v === this.currentView) ? 'block' : 'none';

      const navBtn = document.getElementById(`nav-${v}`);
      if (navBtn) {
        if (v === this.currentView) navBtn.classList.add('active');
        else navBtn.classList.remove('active');
      }
    });

    await this.refreshCurrentView();
  }

  async refreshCurrentView() {
    if (!this.currentUser) return;

    if (this.currentView === 'dashboard') {
      await this.loadDashboard();
    } else if (this.currentView === 'references') {
      await this.loadCollections();
      await this.loadReferences();
    } else if (this.currentView === 'collections') {
      await this.loadCollectionsView();
    } else if (this.currentView === 'editor') {
      await this.loadEditorView();
    } else if (this.currentView === 'admin') {
      if (this.currentUser.role === 'Administrator') {
        await this.loadAdminPortal();
      } else {
        this.showToast('Access denied: Administrator privileges required.', 'danger');
        this.navigateTo('dashboard');
      }
    }
  }

  // --- Dashboard Module (UC-020, FR-031) ---
  async loadDashboard() {
    try {
      const res = await this.api('/api/dashboard');
      if (res.success && res.data) {
        const d = res.data;
        document.getElementById('stat-total-references').textContent = d.totalReferences;
        document.getElementById('stat-total-collections').textContent = d.totalCollections;
        document.getElementById('stat-total-documents').textContent = d.totalDocuments;

        const tb = d.typeBreakdown || {};
        document.getElementById('stat-type-breakdown').textContent = 
          `Journal: ${tb['Journal Article'] || 0} | Book: ${tb['Book'] || 0} | Web: ${tb['Website'] || 0}`;

        document.getElementById('dashboard-welcome-text').textContent = 
          `Logged in as ${this.currentUser.name} (${this.currentUser.role}) • Strict library isolation active`;

        // Render Recent Documents
        const docsContainer = document.getElementById('dashboard-recent-docs-list');
        if (d.recentDocuments && d.recentDocuments.length > 0) {
          docsContainer.innerHTML = d.recentDocuments.map(doc => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid var(--border-subtle);">
              <div>
                <div style="font-weight: 600; color: var(--text-main);">${this.escape(doc.title)}</div>
                <div style="font-size: 0.8rem; color: var(--text-dim);">Style: ${doc.citationStyle} • State: <span class="badge ${this.getDocBadgeClass(doc.state)}">${doc.state}</span></div>
              </div>
              <button class="btn btn-sm btn-secondary" onclick="appState.openDocumentInEditor('${doc.documentId}')">
                Open ➔
              </button>
            </div>
          `).join('');
        } else {
          docsContainer.innerHTML = `<p style="color: var(--text-dim); font-size: 0.9rem;">No documents created yet. Click "+ New Paper" to begin!</p>`;
        }

        // Render Collections
        const colsContainer = document.getElementById('dashboard-collections-list');
        if (d.collections && d.collections.length > 0) {
          colsContainer.innerHTML = d.collections.map(col => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid var(--border-subtle);">
              <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span>📁</span>
                <span style="font-weight: 500;">${this.escape(col.name)}</span>
              </div>
              <span class="badge" style="background: var(--bg-glass-strong);">${col.refCount} references</span>
            </div>
          `).join('');
        } else {
          colsContainer.innerHTML = `<p style="color: var(--text-dim); font-size: 0.9rem;">No collections created yet.</p>`;
        }
      }
    } catch (err) {
      this.showToast(`Failed to load dashboard: ${err.message}`, 'danger');
    }
  }

  // --- Reference Management Module (IReference + ReferenceValidator + SearchService) ---
  async loadReferences() {
    const q = document.getElementById('input-ref-search').value.trim();
    const type = document.getElementById('select-ref-type').value;
    const colId = document.getElementById('select-ref-collection').value;

    let url = `/api/references?`;
    if (q) url += `query=${encodeURIComponent(q)}&`;
    if (type && type !== 'All') url += `type=${encodeURIComponent(type)}&`;
    if (colId && colId !== 'All') url += `collectionId=${encodeURIComponent(colId)}&`;

    try {
      const res = await this.api(url);
      if (res.success) {
        this.references = res.references || [];
        this.renderReferencesList();
      }
    } catch (err) {
      this.showToast(`Error fetching references: ${err.message}`, 'danger');
    }
  }

  renderReferencesList() {
    const container = document.getElementById('references-list-container');
    if (!this.references || this.references.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align: center; padding: 3rem 1rem;">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📚</div>
          <h3 style="font-size: 1.2rem; font-weight: 600;">No references found</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.35rem;">
            Add citations or adjust your search filter criteria.
          </p>
          <button class="btn btn-primary" onclick="appState.openAddReferenceModal()" style="margin-top: 1rem;">
            ➕ Add First Reference
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = this.references.map(ref => {
      let icon = '📄';
      if (ref.type === 'Book') icon = '📖';
      else if (ref.type === 'Website') icon = '🌐';

      let detailsHtml = '';
      if (ref.type === 'Journal Article') {
        detailsHtml = `<b>Journal:</b> ${this.escape(ref.journalName || '')}`;
        if (ref.volumeIssue) detailsHtml += ` • <b>Vol:</b> ${this.escape(ref.volumeIssue)}`;
        if (ref.pages) detailsHtml += ` • <b>Pages:</b> ${this.escape(ref.pages)}`;
      } else if (ref.type === 'Book') {
        detailsHtml = `<b>Publisher:</b> ${this.escape(ref.publisher || '')}`;
        if (ref.editionPlace) detailsHtml += ` • <b>Place/Edition:</b> ${this.escape(ref.editionPlace)}`;
      } else if (ref.type === 'Website') {
        detailsHtml = `<b>Site:</b> ${this.escape(ref.siteName || 'Web Page')} • <b>URL:</b> <a href="${this.escape(ref.url)}" target="_blank" style="color: var(--accent);">${this.escape(ref.url)}</a> • <b>Accessed:</b> ${this.escape(ref.accessDate || '')}`;
      }

      const collectionBadges = (ref.collections || []).map(c => 
        `<span class="badge" style="background: rgba(14, 165, 233, 0.15); color: #38BDF8;">📁 ${this.escape(c.name)}</span>`
      ).join(' ');

      const keywordsHtml = ref.keywords ? ref.keywords.split(',').map(k => 
        `<span class="keyword-tag">#${this.escape(k.trim())}</span>`
      ).join('') : '';

      const stateBadge = `<span class="badge ${this.getRefBadgeClass(ref.lifecycleState)}">${ref.lifecycleState}</span>`;

      return `
        <div class="reference-item">
          <div class="ref-main">
            <div class="ref-top">
              <span class="badge" style="background: var(--bg-surface-elevated);">${icon} ${ref.type}</span>
              ${stateBadge}
              <span style="font-size: 0.8rem; color: var(--text-dim); font-family: var(--font-mono);">${ref.referenceId}</span>
              ${collectionBadges}
            </div>
            <div class="ref-title">${this.escape(ref.title)}</div>
            <div class="ref-authors">${this.escape(ref.authors || ref.siteName || 'No authors listed')} (${ref.year || 'n.d.'})</div>
            <div class="ref-details">${detailsHtml}</div>
            ${keywordsHtml ? `<div class="ref-keywords">${keywordsHtml}</div>` : ''}
          </div>
          <div class="ref-actions">
            <button class="btn btn-sm btn-outline" onclick="appState.openEditReferenceModal('${ref.referenceId}')" title="Edit reference">
              ✏️ Edit
            </button>
            <button class="btn btn-sm btn-secondary" onclick="appState.openManageMembershipsModal('${ref.referenceId}')" title="Add to collection">
              📁 Collections
            </button>
            <button class="btn btn-sm btn-danger" onclick="appState.requestDeleteReference('${ref.referenceId}')" title="Delete reference">
              🗑️ Delete
            </button>
          </div>
        </div>
      `;
    }).join('');
  }

  filterReferences() {
    this.loadReferences();
  }

  clearRefFilters() {
    document.getElementById('input-ref-search').value = '';
    document.getElementById('select-ref-type').value = 'All';
    document.getElementById('select-ref-collection').value = 'All';
    this.loadReferences();
  }

  // --- Add / Edit Reference Modal (UC-004, UC-005, Annex A) ---
  openAddReferenceModal() {
    document.getElementById('modal-ref-title').textContent = 'Add Reference';
    document.getElementById('ref-field-id').value = '';
    document.getElementById('ref-field-type').value = 'Journal Article';
    document.getElementById('ref-field-title').value = '';
    document.getElementById('ref-field-authors').value = '';
    document.getElementById('ref-field-year').value = '';
    document.getElementById('ref-field-journalName').value = '';
    document.getElementById('ref-field-volumeIssue').value = '';
    document.getElementById('ref-field-pages').value = '';
    document.getElementById('ref-field-publisher').value = '';
    document.getElementById('ref-field-editionPlace').value = '';
    document.getElementById('ref-field-siteName').value = '';
    document.getElementById('ref-field-url').value = '';
    document.getElementById('ref-field-accessDate').value = new Date().toISOString().split('T')[0];
    document.getElementById('ref-field-keywords').value = '';

    // Populate collections dropdown
    const colSelect = document.getElementById('ref-field-collectionId');
    colSelect.innerHTML = `<option value="">None (Library Root)</option>` + 
      this.collections.map(c => `<option value="${c.collectionId}">${this.escape(c.name)}</option>`).join('');
    document.getElementById('group-initial-collection').style.display = 'block';

    this.clearValidationErrors();
    this.handleRefTypeChange('Journal Article');
    this.openModal('modal-reference');
  }

  openEditReferenceModal(refId) {
    const ref = this.references.find(r => r.referenceId === refId);
    if (!ref) return;

    document.getElementById('modal-ref-title').textContent = `Edit Reference (${ref.referenceId})`;
    document.getElementById('ref-field-id').value = ref.referenceId;
    document.getElementById('ref-field-type').value = ref.type;
    document.getElementById('ref-field-title').value = ref.title || '';
    document.getElementById('ref-field-authors').value = ref.authors || '';
    document.getElementById('ref-field-year').value = ref.year || '';
    document.getElementById('ref-field-journalName').value = ref.journalName || '';
    document.getElementById('ref-field-volumeIssue').value = ref.volumeIssue || '';
    document.getElementById('ref-field-pages').value = ref.pages || '';
    document.getElementById('ref-field-publisher').value = ref.publisher || '';
    document.getElementById('ref-field-editionPlace').value = ref.editionPlace || '';
    document.getElementById('ref-field-siteName').value = ref.siteName || '';
    document.getElementById('ref-field-url').value = ref.url || '';
    document.getElementById('ref-field-accessDate').value = ref.accessDate || '';
    document.getElementById('ref-field-keywords').value = ref.keywords || '';

    document.getElementById('group-initial-collection').style.display = 'none';

    this.clearValidationErrors();
    this.handleRefTypeChange(ref.type);
    this.openModal('modal-reference');
  }

  handleRefTypeChange(refType) {
    const journalDiv = document.getElementById('fields-journal');
    const bookDiv = document.getElementById('fields-book');
    const webDiv = document.getElementById('fields-website');
    const reqAuthors = document.getElementById('req-authors');

    journalDiv.style.display = (refType === 'Journal Article') ? 'block' : 'none';
    bookDiv.style.display = (refType === 'Book') ? 'block' : 'none';
    webDiv.style.display = (refType === 'Website') ? 'block' : 'none';

    // Website allows blank authors if siteName provided
    if (refType === 'Website') {
      reqAuthors.textContent = ' (Optional if Site Name provided)';
    } else {
      reqAuthors.textContent = '*';
    }
  }

  clearValidationErrors() {
    const errorEls = document.querySelectorAll('.invalid-feedback');
    errorEls.forEach(el => { el.textContent = ''; el.style.display = 'none'; });
    const inputs = document.querySelectorAll('.form-control');
    inputs.forEach(el => el.classList.remove('is-invalid'));
  }

  showValidationErrors(errors) {
    this.clearValidationErrors();
    for (const [field, message] of Object.entries(errors)) {
      const errEl = document.getElementById(`err-${field}`);
      const inputEl = document.getElementById(`ref-field-${field}`);
      if (errEl) {
        errEl.textContent = message;
        errEl.style.display = 'block';
      }
      if (inputEl) {
        inputEl.classList.add('is-invalid');
      }
    }
  }

  async handleSaveReference(e) {
    if (e) e.preventDefault();
    const refId = document.getElementById('ref-field-id').value;
    const refData = {
      type: document.getElementById('ref-field-type').value,
      title: document.getElementById('ref-field-title').value.trim(),
      authors: document.getElementById('ref-field-authors').value.trim(),
      year: document.getElementById('ref-field-year').value.trim(),
      journalName: document.getElementById('ref-field-journalName').value.trim(),
      volumeIssue: document.getElementById('ref-field-volumeIssue').value.trim(),
      pages: document.getElementById('ref-field-pages').value.trim(),
      publisher: document.getElementById('ref-field-publisher').value.trim(),
      editionPlace: document.getElementById('ref-field-editionPlace').value.trim(),
      siteName: document.getElementById('ref-field-siteName').value.trim(),
      url: document.getElementById('ref-field-url').value.trim(),
      accessDate: document.getElementById('ref-field-accessDate').value.trim(),
      keywords: document.getElementById('ref-field-keywords').value.trim(),
      collectionId: document.getElementById('ref-field-collectionId').value || null
    };

    try {
      let res;
      if (refId) {
        res = await this.api(`/api/references/${refId}`, {
          method: 'PUT',
          body: refData
        });
      } else {
        res = await this.api('/api/references', {
          method: 'POST',
          body: refData
        });
      }

      if (res.success) {
        this.showToast(res.message, 'success');
        this.closeModal('modal-reference');
        await this.loadReferences();
      } else if (res.errors) {
        this.showValidationErrors(res.errors);
        this.showToast(res.message || 'Validation failed. Check fields.', 'warning');
      }
    } catch (err) {
      this.showToast(`Error saving reference: ${err.message}`, 'danger');
    }
  }

  // --- Cascading Delete Reference Logic (UC-006, BR-009, Annex B & E) ---
  async requestDeleteReference(refId) {
    try {
      const res = await this.api(`/api/references/${refId}/cascade-check`);
      if (!res.success || !res.cascade) return;

      const cascade = res.cascade;
      const ref = this.references.find(r => r.referenceId === refId);
      const title = ref ? ref.title : refId;

      const contentBox = document.getElementById('cascade-delete-content');
      const confirmBtn = document.getElementById('btn-confirm-cascade-delete');

      if (cascade.isCited && cascade.citingDocuments.length > 0) {
        // CITED IN DOCUMENTS (Annex B & E)
        const docTags = cascade.citingDocuments.map(d => 
          `<span class="citing-doc-tag">📄 ${this.escape(d.title)} (${d.documentId})</span>`
        ).join(' ');

        contentBox.innerHTML = `
          <div class="alert-warning-box">
            <h4 style="color: var(--danger); font-size: 1rem; margin-bottom: 0.5rem;">⚠️ Cascading Citation Warning</h4>
            <p style="font-size: 0.9rem; margin-bottom: 0.75rem;">
              <b>Are you sure you want to delete?</b> These documents cite this reference and the citations will be removed:
            </p>
            <div style="margin-bottom: 0.75rem;">${docTags}</div>
            <p style="font-size: 0.85rem; color: var(--text-dim);">
              Deleting will remove all inline citations of <b>"${this.escape(title)}"</b> from the listed papers, recalculate their bibliographies, and permanently delete the reference.
            </p>
          </div>
        `;
        confirmBtn.textContent = 'Confirm & Clean Citations';
      } else {
        // NOT CITED
        contentBox.innerHTML = `
          <p style="font-size: 0.95rem; margin-bottom: 0.75rem;">
            Are you sure you want to delete the reference <b>"${this.escape(title)}"</b>?
          </p>
          <p style="font-size: 0.85rem; color: var(--text-muted);">
            This reference is not currently cited in any papers. Any collection membership links will be removed.
          </p>
        `;
        confirmBtn.textContent = 'Delete Reference';
      }

      confirmBtn.onclick = () => this.executeDeleteReference(refId);
      this.openModal('modal-cascade-delete');

    } catch (err) {
      this.showToast(`Error checking reference citations: ${err.message}`, 'danger');
    }
  }

  async executeDeleteReference(refId) {
    try {
      const res = await this.api(`/api/references/${refId}`, { method: 'DELETE' });
      if (res.success) {
        this.showToast(res.message, 'success');
        this.closeModal('modal-cascade-delete');
        await this.loadReferences();
      }
    } catch (err) {
      this.showToast(`Failed to delete reference: ${err.message}`, 'danger');
    }
  }

  // --- Collections Module (ICollection) ---
  async loadCollections() {
    try {
      const res = await this.api('/api/collections');
      if (res.success) {
        this.collections = res.collections || [];

        // Update dropdown filter in library
        const colSelect = document.getElementById('select-ref-collection');
        colSelect.innerHTML = `<option value="All">All Collections</option>` + 
          this.collections.map(c => `<option value="${c.collectionId}">${this.escape(c.name)}</option>`).join('');
      }
    } catch (e) {
      console.warn('Error loading collections:', e);
    }
  }

  async loadCollectionsView() {
    await this.loadCollections();
    const container = document.getElementById('collections-list-container');
    if (!this.collections || this.collections.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align: center; padding: 3rem 1rem; grid-column: 1 / -1;">
          <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📁</div>
          <h3 style="font-size: 1.2rem; font-weight: 600;">No collections yet</h3>
          <p style="color: var(--text-muted); font-size: 0.9rem; margin-top: 0.35rem;">
            Create project collections to categorize your references.
          </p>
          <button class="btn btn-primary" onclick="appState.openCreateCollectionModal()" style="margin-top: 1rem;">
            📁➕ Create First Collection
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = this.collections.map(col => `
      <div class="card stat-card" style="flex-direction: column; align-items: stretch;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.4rem;">📁</span>
            <h3 style="font-size: 1.15rem; color: var(--text-main); text-transform: none;">${this.escape(col.name)}</h3>
          </div>
          <span class="badge" style="background: var(--bg-glass-strong); font-size: 0.75rem;">${col.referenceCount} refs</span>
        </div>
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 1.25rem;">
          ID: ${col.collectionId} • Created: ${col.createdDate ? col.createdDate.split('T')[0] : ''}
        </div>
        <div style="display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: auto;">
          <button class="btn btn-sm btn-outline" onclick="appState.openRenameCollectionModal('${col.collectionId}', '${this.escape(col.name)}')">
            Rename
          </button>
          <button class="btn btn-sm btn-danger" onclick="appState.handleDeleteCollection('${col.collectionId}')">
            Delete
          </button>
        </div>
      </div>
    `).join('');
  }

  openCreateCollectionModal() {
    document.getElementById('modal-col-title').textContent = 'Create Collection';
    document.getElementById('col-field-id').value = '';
    document.getElementById('col-field-name').value = '';
    this.openModal('modal-collection');
  }

  openRenameCollectionModal(colId, currentName) {
    document.getElementById('modal-col-title').textContent = 'Rename Collection';
    document.getElementById('col-field-id').value = colId;
    document.getElementById('col-field-name').value = currentName;
    this.openModal('modal-collection');
  }

  async handleSaveCollection(e) {
    if (e) e.preventDefault();
    const colId = document.getElementById('col-field-id').value;
    const name = document.getElementById('col-field-name').value.trim();
    if (!name) return;

    try {
      let res;
      if (colId) {
        res = await this.api(`/api/collections/${colId}`, {
          method: 'PUT',
          body: { name }
        });
      } else {
        res = await this.api('/api/collections', {
          method: 'POST',
          body: { name }
        });
      }

      if (res.success) {
        this.showToast(res.message, 'success');
        this.closeModal('modal-collection');
        await this.loadCollectionsView();
      }
    } catch (err) {
      this.showToast(`Error: ${err.message}`, 'danger');
    }
  }

  async handleDeleteCollection(colId) {
    if (!confirm('Are you sure you want to delete this collection? Note: Underlying references will NOT be deleted from your library.')) {
      return;
    }
    try {
      const res = await this.api(`/api/collections/${colId}`, { method: 'DELETE' });
      if (res.success) {
        this.showToast(res.message, 'success');
        await this.loadCollectionsView();
      }
    } catch (err) {
      this.showToast(`Failed to delete collection: ${err.message}`, 'danger');
    }
  }

  async openManageMembershipsModal(refId) {
    const ref = this.references.find(r => r.referenceId === refId);
    if (!ref) return;

    document.getElementById('assign-ref-title-display').innerHTML = `Assign <b>"${this.escape(ref.title)}"</b> to collections:`;
    const container = document.getElementById('assign-collections-checkboxes');

    const activeColIds = (ref.collections || []).map(c => c.collectionId);

    if (this.collections.length === 0) {
      container.innerHTML = `<p style="font-size: 0.85rem; color: var(--text-dim);">No collections created yet. Create a collection first.</p>`;
    } else {
      container.innerHTML = this.collections.map(col => {
        const checked = activeColIds.includes(col.collectionId) ? 'checked' : '';
        return `
          <label style="display: flex; align-items: center; gap: 0.6rem; padding: 0.45rem 0; cursor: pointer; border-bottom: 1px solid var(--border-subtle);">
            <input type="checkbox" ${checked} onchange="appState.toggleCollectionMembership('${col.collectionId}', '${refId}', this.checked)">
            <span>📁 ${this.escape(col.name)}</span>
          </label>
        `;
      }).join('');
    }

    this.openModal('modal-assign-collection');
  }

  async toggleCollectionMembership(colId, refId, shouldAdd) {
    try {
      if (shouldAdd) {
        await this.api(`/api/collections/${colId}/references/${refId}`, { method: 'POST' });
        this.showToast('Added to collection.', 'success');
      } else {
        await this.api(`/api/collections/${colId}/references/${refId}`, { method: 'DELETE' });
        this.showToast('Removed from collection.', 'info');
      }
      await this.loadReferences();
    } catch (err) {
      this.showToast(`Membership update failed: ${err.message}`, 'danger');
    }
  }

  // --- Document Editor Module (IDocument / DocumentEditor & IBibliography) ---
  async loadEditorView() {
    try {
      const res = await this.api('/api/documents');
      if (res.success) {
        this.documents = res.documents || [];
        const selector = document.getElementById('editor-doc-selector');

        if (this.documents.length === 0) {
          // Auto create first document
          await this.createNewDocument('My Research Paper');
          return;
        }

        selector.innerHTML = this.documents.map(d => 
          `<option value="${d.documentId}">${this.escape(d.title)} (${d.citationStyle})</option>`
        ).join('');

        // If no active doc or deleted, pick first
        if (!this.currentDocument || !this.documents.find(d => d.documentId === this.currentDocument.documentId)) {
          await this.switchActiveDocument(this.documents[0].documentId);
        } else {
          await this.switchActiveDocument(this.currentDocument.documentId);
        }
      }
    } catch (err) {
      this.showToast(`Error loading documents: ${err.message}`, 'danger');
    }
  }

  async switchActiveDocument(docId) {
    try {
      const res = await this.api(`/api/documents/${docId}`);
      if (res.success && res.document) {
        this.currentDocument = res.document;
        this.renderActiveDocument();
      }
    } catch (err) {
      this.showToast(`Failed to open document: ${err.message}`, 'danger');
    }
  }

  renderActiveDocument() {
    if (!this.currentDocument) return;

    document.getElementById('editor-doc-selector').value = this.currentDocument.documentId;
    document.getElementById('editor-doc-title-input').value = this.currentDocument.title;
    document.getElementById('editor-style-select').value = this.currentDocument.citationStyle;

    const sheet = document.getElementById('editor-sheet');
    sheet.innerHTML = this.currentDocument.content || '<h1>Title</h1><p>Start writing your paper...</p>';
    this.lastSavedContent = sheet.innerHTML;

    // Lifecycle badge
    const badge = document.getElementById('editor-state-badge');
    badge.textContent = this.currentDocument.state;
    badge.className = `badge ${this.getDocBadgeClass(this.currentDocument.state)}`;

    // Render live bibliography
    this.renderLiveBibliography();

    // Populate citation picker drawer
    this.populateCitationPicker();
  }

  renderLiveBibliography() {
    const container = document.getElementById('bib-entries-container');
    const indicator = document.getElementById('bib-style-indicator');
    const style = this.currentDocument ? this.currentDocument.citationStyle : 'APA';

    if (style === 'IEEE') indicator.textContent = 'Style: IEEE (Numbered in order of appearance)';
    else if (style === 'MLA') indicator.textContent = 'Style: MLA 9th (Alphabetical by author)';
    else indicator.textContent = 'Style: APA 7th (Alphabetical by author)';

    const bib = (this.currentDocument && this.currentDocument.bibliography) ? this.currentDocument.bibliography : { entries: [] };
    const entries = bib.entries || [];

    if (entries.length === 0) {
      container.innerHTML = `
        <div style="color: var(--text-dim); text-align: center; padding: 2rem 0.5rem; font-style: italic;">
          No citations inserted yet.<br>Click "➕ Insert Citation" or use the picker drawer.
        </div>
      `;
      return;
    }

    container.innerHTML = entries.map(entry => `
      <div class="bib-entry-item">
        ${entry.html || entry.text}
      </div>
    `).join('');
  }

  populateCitationPicker() {
    const container = document.getElementById('picker-references-list');
    const q = (document.getElementById('input-picker-search').value || '').toLowerCase().trim();

    const filtered = this.references.filter(r => {
      if (!q) return true;
      return (r.title && r.title.toLowerCase().includes(q)) ||
             (r.authors && r.authors.toLowerCase().includes(q)) ||
             (r.year && r.year.toString().includes(q));
    });

    if (filtered.length === 0) {
      // No references guard (UC-015 Alt Flow)
      container.innerHTML = `
        <div style="padding: 1rem; text-align: center; color: var(--text-dim); font-size: 0.85rem;">
          No references found.<br>
          <button class="btn btn-sm btn-primary" onclick="appState.openAddReferenceModal()" style="margin-top: 0.5rem;">
            ➕ Add Reference First
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(r => `
      <div class="ref-picker-item" onclick="appState.insertCitationFromPicker('${r.referenceId}')">
        <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-main);">${this.escape(r.title)}</div>
        <div style="font-size: 0.75rem; color: var(--text-muted);">${this.escape(r.authors || r.siteName || '')} (${r.year || 'n.d.'})</div>
      </div>
    `).join('');
  }

  filterPickerReferences() {
    this.populateCitationPicker();
  }

  openCitationPickerDrawer() {
    document.getElementById('input-picker-search').focus();
    this.showToast('Select a reference from the drawer to insert at cursor position.', 'info');
  }

  async insertCitationFromPicker(referenceId) {
    if (!this.currentDocument) return;

    // Capture cursor position / inject placeholder
    const sheet = document.getElementById('editor-sheet');
    sheet.focus();

    const placeholder = '__NEW_CITATION_TOKEN__';
    let insertedIntoDom = false;

    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && sheet.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      const node = document.createTextNode(placeholder);
      range.insertNode(node);
      range.collapse(false);
      insertedIntoDom = true;
    }

    const currentHtml = sheet.innerHTML;

    try {
      const res = await this.api(`/api/documents/${this.currentDocument.documentId}/citations`, {
        method: 'POST',
        body: {
          referenceId,
          contentWithToken: insertedIntoDom ? currentHtml : null
        }
      });

      if (res.success && res.document) {
        this.currentDocument = res.document;
        this.renderActiveDocument();
        this.showToast('Citation inserted and bibliography synchronized!', 'success');
      }
    } catch (err) {
      this.showToast(`Failed to insert citation: ${err.message}`, 'danger');
      if (insertedIntoDom) {
        sheet.innerHTML = sheet.innerHTML.replace(placeholder, '');
      }
    }
  }

  async handleRemoveCitation(citationId) {
    if (!this.currentDocument) return;
    if (!confirm('Remove this inline citation from the document?')) return;

    try {
      const res = await this.api(`/api/documents/${this.currentDocument.documentId}/citations/${citationId}`, {
        method: 'DELETE'
      });

      if (res.success && res.document) {
        this.currentDocument = res.document;
        this.renderActiveDocument();
        this.showToast('Citation removed.', 'info');
      }
    } catch (err) {
      this.showToast(`Error removing citation: ${err.message}`, 'danger');
    }
  }

  async handleStyleChange(newStyle) {
    if (!this.currentDocument) return;
    try {
      const res = await this.api(`/api/documents/${this.currentDocument.documentId}/style`, {
        method: 'POST',
        body: { citationStyle: newStyle }
      });

      if (res.success && res.document) {
        this.currentDocument = res.document;
        this.renderActiveDocument();
        this.showToast(`Citation style switched to ${newStyle}!`, 'success');
      }
    } catch (err) {
      this.showToast(`Error switching style: ${err.message}`, 'danger');
    }
  }

  handleEditorInput() {
    clearTimeout(this.autoSaveTimer);
    this.autoSaveTimer = setTimeout(() => {
      this.saveCurrentDocument(true); // Background auto-save
    }, 2500);
  }

  async saveCurrentDocument(isAutoSave = false) {
    if (!this.currentDocument) return;

    const title = document.getElementById('editor-doc-title-input').value.trim() || this.currentDocument.title;
    const content = document.getElementById('editor-sheet').innerHTML;
    const style = document.getElementById('editor-style-select').value;

    try {
      const res = await this.api(`/api/documents/${this.currentDocument.documentId}`, {
        method: 'PUT',
        body: {
          title,
          content,
          citationStyle: style
        }
      });

      if (res.success && res.document) {
        this.currentDocument = res.document;
        this.lastSavedContent = content;
        if (!isAutoSave) {
          this.showToast('Document saved successfully.', 'success');
        }
        // Update document title in selector
        const sel = document.getElementById('editor-doc-selector');
        const opt = sel.querySelector(`option[value="${res.document.documentId}"]`);
        if (opt) opt.textContent = `${res.document.title} (${res.document.citationStyle})`;
      }
    } catch (err) {
      if (!isAutoSave) this.showToast(`Save failed: ${err.message}`, 'danger');
    }
  }

  createNewDocumentPrompt() {
    const title = prompt('Enter title for the new academic document:');
    if (title && title.trim()) {
      this.createNewDocument(title.trim());
    }
  }

  async createNewDocument(title) {
    try {
      const res = await this.api('/api/documents', {
        method: 'POST',
        body: { title, citationStyle: 'APA' }
      });

      if (res.success && res.document) {
        this.showToast('New document created.', 'success');
        this.currentDocument = res.document;
        this.navigateTo('editor');
      }
    } catch (err) {
      this.showToast(`Error creating document: ${err.message}`, 'danger');
    }
  }

  openDocumentInEditor(docId) {
    this.navigateTo('editor');
    this.switchActiveDocument(docId);
  }

  formatDoc(cmd, val = null) {
    document.execCommand(cmd, false, val);
    document.getElementById('editor-sheet').focus();
    this.handleEditorInput();
  }

  formatHeading(tag) {
    document.execCommand('formatBlock', false, tag);
    document.getElementById('editor-sheet').focus();
    this.handleEditorInput();
  }

  // --- Export Module (IExport / ExportService) ---
  openExportModal(standaloneBibliography = false) {
    if (!this.currentDocument) {
      this.showToast('Please open or save a document first.', 'warning');
      return;
    }

    const titleEl = document.getElementById('modal-export-title');
    const scopeGroup = document.getElementById('group-export-scope');

    if (standaloneBibliography) {
      titleEl.textContent = 'Export Standalone Bibliography (FR-030)';
      document.querySelector('input[name="export-scope"][value="bib"]').checked = true;
      scopeGroup.style.display = 'none';
    } else {
      titleEl.textContent = 'Export Academic Document';
      document.querySelector('input[name="export-scope"][value="full"]').checked = true;
      scopeGroup.style.display = 'block';
    }

    this.openModal('modal-export');
  }

  async triggerExportDownload() {
    if (!this.currentDocument) return;

    // Auto-save before export (Annex C)
    await this.saveCurrentDocument(true);

    const format = document.querySelector('input[name="export-format"]:checked').value;
    const scope = document.querySelector('input[name="export-scope"]:checked').value;
    const standalone = (scope === 'bib');

    const downloadBtn = document.getElementById('btn-trigger-download');
    downloadBtn.disabled = true;
    downloadBtn.innerHTML = `<span class="spinner"></span> Exporting...`;

    try {
      const url = `/api/documents/${this.currentDocument.documentId}/export?format=${format}&standalone=${standalone}`;
      const res = await this.api(url);

      if (res.isBlob) {
        // Trigger browser file download
        const blob = res.blob;
        const link = document.createElement('a');
        link.href = window.URL.createObjectURL(blob);

        let filename = 'CiteNest_Export';
        const disposition = res.response.headers.get('Content-Disposition');
        if (disposition) {
          const match = disposition.match(/filename="?([^";]+)"?/);
          if (match && match[1]) filename = match[1];
        }
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(link.href);

        this.showToast(`Exported ${filename} successfully!`, 'success');
        this.closeModal('modal-export');

        // Refresh doc state to Exported
        await this.switchActiveDocument(this.currentDocument.documentId);
      }
    } catch (err) {
      this.showToast(`Export failed: ${err.message}`, 'danger');
    } finally {
      downloadBtn.disabled = false;
      downloadBtn.innerHTML = `<span>📥</span> Download File`;
    }
  }

  // --- Administrator & Audit Portal Module (UC-003, FR-032, FR-033, NFR-019) ---
  async loadAdminPortal() {
    try {
      // 1. Metrics
      const mRes = await this.api('/api/admin/metrics');
      if (mRes.success && mRes.metrics) {
        const m = mRes.metrics;
        document.getElementById('admin-metrics-container').innerHTML = `
          <div class="stat-card">
            <div class="stat-icon">👥</div>
            <div class="stat-content">
              <h3>Total Users</h3>
              <div class="stat-value">${m.totalUsers} <span style="font-size: 0.9rem; font-weight: normal; color: var(--success);">${m.activeUsers} Active</span></div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">📚</div>
            <div class="stat-content">
              <h3>System References</h3>
              <div class="stat-value">${m.totalReferences}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">📝</div>
            <div class="stat-content">
              <h3>Documents</h3>
              <div class="stat-value">${m.totalDocuments}</div>
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-icon">🛡️</div>
            <div class="stat-content">
              <h3>Audit Records</h3>
              <div class="stat-value">${m.totalLogs}</div>
            </div>
          </div>
        `;
      }

      // 2. Users Table
      const uRes = await this.api('/api/admin/users');
      if (uRes.success && uRes.users) {
        const tbody = document.getElementById('admin-users-table-body');
        tbody.innerHTML = uRes.users.map(u => {
          const isMe = (u.userId === this.currentUser.userId);
          const toggleStatusBtn = isMe ? '' : `
            <button class="btn btn-sm ${u.accountStatus === 'Active' ? 'btn-danger' : 'btn-primary'}" onclick="appState.toggleUserStatus('${u.userId}', '${u.accountStatus}')">
              ${u.accountStatus === 'Active' ? 'Suspend' : 'Activate'}
            </button>
          `;
          const changeRoleBtn = isMe ? '' : `
            <button class="btn btn-sm btn-outline" onclick="appState.openChangeRoleModal('${u.userId}', '${u.role}')">
              Role
            </button>
          `;
          const deleteBtn = isMe ? '' : `
            <button class="btn btn-sm btn-danger" onclick="appState.deleteUserAccount('${u.userId}', '${this.escape(u.name)}')">
              Delete
            </button>
          `;

          return `
            <tr>
              <td><code>${u.userId}</code></td>
              <td><b>${this.escape(u.name)}</b> ${isMe ? '<span class="badge badge-admin">(You)</span>' : ''}</td>
              <td>${this.escape(u.email)}</td>
              <td><span class="badge ${this.getRoleBadgeClass(u.role)}">${u.role}</span></td>
              <td><span class="badge ${u.accountStatus === 'Active' ? 'badge-active' : 'badge-suspended'}">${u.accountStatus}</span></td>
              <td>${u.referenceCount}</td>
              <td>${u.documentCount}</td>
              <td>
                <div style="display: flex; gap: 0.35rem;">
                  ${toggleStatusBtn}
                  ${changeRoleBtn}
                  ${deleteBtn}
                </div>
              </td>
            </tr>
          `;
        }).join('');
      }

      // 3. Audit Logs
      await this.loadAuditLogs();

    } catch (err) {
      this.showToast(`Admin portal error: ${err.message}`, 'danger');
    }
  }

  async loadAuditLogs(q = '') {
    try {
      const url = q ? `/api/admin/audit-logs?query=${encodeURIComponent(q)}` : `/api/admin/audit-logs`;
      const res = await this.api(url);
      if (res.success && res.logs) {
        const tbody = document.getElementById('admin-logs-table-body');
        tbody.innerHTML = res.logs.map(log => `
          <tr>
            <td><code>${log.logId}</code></td>
            <td><code>${log.actorId}</code></td>
            <td>${this.escape(log.action)}</td>
            <td style="font-size: 0.8rem; color: var(--text-dim);">${log.timestamp}</td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.warn('Error loading audit logs:', e);
    }
  }

  filterAuditLogs(query) {
    this.loadAuditLogs(query);
  }

  async toggleUserStatus(targetUserId, currentStatus) {
    const newStatus = (currentStatus === 'Active') ? 'Suspended' : 'Active';
    if (!confirm(`Are you sure you want to change user ${targetUserId} status to ${newStatus}?`)) return;

    try {
      const res = await this.api(`/api/admin/users/${targetUserId}/status`, {
        method: 'PUT',
        body: { accountStatus: newStatus }
      });
      if (res.success) {
        this.showToast(res.message, 'success');
        await this.loadAdminPortal();
      }
    } catch (err) {
      this.showToast(`Failed to update user status: ${err.message}`, 'danger');
    }
  }

  openChangeRoleModal(targetUserId, currentRole) {
    document.getElementById('admin-target-user-id').value = targetUserId;
    document.getElementById('admin-select-role').value = currentRole;
    this.openModal('modal-admin-role');
  }

  async handleAdminRoleChange(e) {
    if (e) e.preventDefault();
    const targetUserId = document.getElementById('admin-target-user-id').value;
    const role = document.getElementById('admin-select-role').value;

    try {
      const res = await this.api(`/api/admin/users/${targetUserId}/role`, {
        method: 'PUT',
        body: { role }
      });
      if (res.success) {
        this.showToast(res.message, 'success');
        this.closeModal('modal-admin-role');
        await this.loadAdminPortal();
      }
    } catch (err) {
      this.showToast(`Error changing role: ${err.message}`, 'danger');
    }
  }

  async deleteUserAccount(targetUserId, userName) {
    if (!confirm(`Are you sure you want to permanently delete user account '${userName}' (${targetUserId})? All associated references, collections, and papers will be removed.`)) {
      return;
    }
    try {
      const res = await this.api(`/api/admin/users/${targetUserId}`, { method: 'DELETE' });
      if (res.success) {
        this.showToast(res.message, 'success');
        await this.loadAdminPortal();
      }
    } catch (err) {
      this.showToast(`Failed to delete user: ${err.message}`, 'danger');
    }
  }

  // --- Modal Helpers ---
  openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
  }

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  }

  // --- Toast Notifications ---
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    else if (type === 'danger') icon = '❌';
    else if (type === 'warning') icon = '⚠️';

    toast.innerHTML = `
      <span style="font-size: 1.1rem;">${icon}</span>
      <div style="flex: 1; font-size: 0.875rem;">${message}</div>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- Utility Formatting Helpers ---
  escape(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  getRoleBadgeClass(role) {
    if (role === 'Student') return 'badge-student';
    if (role === 'Researcher/Faculty') return 'badge-researcher';
    if (role === 'Administrator') return 'badge-admin';
    return '';
  }

  getRefBadgeClass(state) {
    if (state === 'Stored') return 'badge-stored';
    if (state === 'InCollection') return 'badge-incollection';
    if (state === 'Cited') return 'badge-cited';
    return 'badge-stored';
  }

  getDocBadgeClass(state) {
    if (state === 'Draft') return 'badge-draft';
    if (state === 'In Progress') return 'badge-inprogress';
    if (state === 'Citation(s) Inserted') return 'badge-citsinserted';
    if (state === 'Bibliography Generated') return 'badge-bibgenerated';
    if (state === 'Exported') return 'badge-exported';
    return 'badge-draft';
  }
}

// Global Application Instance
const appState = new CiteNestApp();
