# CiteNest - Citation & Reference Management System

**CiteNest** is an academic citation and reference management platform featuring an integrated academic paper editor, automatic in-text citation generator, dynamic bibliography compiler, and PDF/TXT exporter. It is organized into a four-layer architecture with a two-level database model (central application database + isolated per-user personal databases).

---

## Architecture Overview (Four-Layer Design)

1. **Presentation Layer (`static/`)**:
   - Single-Page Application (`index.html`, `css/app.css`, `js/app.js`).
   - Dynamic user dashboard, multi-facet reference search, collection manager, and rich-text paper editor.
   - Distinct source badges identifying references as either **Central Catalog** or **Personal Library**.
   - Strictly communicates via REST API; zero direct database access.

2. **Application Layer (`services/`)**:
   - **`AuthService`**: Session management, user registration, and authentication.
   - **`ReferenceSearchService`**: Unified multi-source search combining central catalog and personal references.
   - **`ReferenceService`**: CRUD coordination, cascading citation safeguards.
   - **`PersonalReferenceService`**: Manages isolated per-user SQLite databases (`user_databases/<userId>.db`).
   - **`CollectionService`**: Cross-database collection memberships supporting both central and personal references without SQL foreign-key coupling.
   - **`DocumentService`**: Cross-source reference resolution, inline citation insertion, dynamic bibliography compilation.
   - **`ExportService`**: Academic PDF and TXT generation.
   - **`AdminService`**: Combined metrics across central and personal libraries, audit logs, and user management.

3. **Domain Layer (`models.py`, `validators.py`, `formatters.py`)**:
   - **`models.py`**: Data schemas and enums including `ReferenceSource` (`CENTRAL`, `PERSONAL`), `CollectionMembership` with `referenceSource`, `ReferenceType`, `CitationStyle`, and lifecycle states.
   - **`validators.py`**: Strict per-type validation rules (`Journal Article`, `Book`, `Website`).
   - **`formatters.py`**: Strategy-pattern citation formatters (APA 7th, MLA 9th, IEEE).

4. **Data Access Layer (`database.py`)**:
   - **Central Application Database (`citenest.db`)**: Stores shared catalog references (`isShared=1`), users, sessions, collections, documents, citations, bibliographies, and audit logs.
   - **Personal Databases (`user_databases/<userId>.db`)**: Lightweight, isolated SQLite databases created per user on first use. Zero auth credentials or secrets stored here. Path derived solely from authenticated user ID.

---

## Features

- **Authentication & RBAC (`IAuth`)**:
  - Secure PBKDF2 with SHA-256 password hashing.
  - Role-Based Access Control (`Student`, `Researcher/Faculty`, `Administrator`).
  - Active session verification on all protected endpoints.
- **Two-Level Database Reference Management (`IReference` + `PersonalReferenceService`)**:
  - Validation rules for `Journal Article`, `Book`, and `Website` types.
  - Personal references stored in private per-user databases (`user_databases/<userId>.db`).
  - Shared reference catalog stored centrally in `citenest.db` (`isShared=1`).
  - Strict privacy: Users cannot access or query another user's personal database.
- **Unified Reference Search (`ReferenceSearchService`)**:
  - Searches central catalog and authenticated user's personal database simultaneously.
  - Combines and tags each record with its source (`CENTRAL` or `PERSONAL`).
  - Multi-facet search across titles, authors, publication years, keywords, and collections.
- **Hybrid Project Collections (`ICollection`)**:
  - Organize references into project groupings from both Central and Personal sources.
  - Validates reference existence and permissions via application services without rigid SQL foreign keys.
  - Composition integrity: Deleting a collection removes memberships while preserving underlying library references.
- **Integrated Academic Paper Editor (`IDocument` / `DocumentEditor`)**:
  - In-app rich text formatting (Bold, Italic, Headings H1/H2/H3).
  - Cross-source citation insertion: Citations can reference either Central or Personal references.
  - Inline interactive citation tokens with cursor insertion.
  - Strategy-pattern citation formatters:
    - **APA 7th**: In-text `(LastName, Year)` / `(FirstAuthor et al., Year)`, bibliography sorted alphabetically by first author.
    - **MLA 9th**: In-text `(LastName)` / `(FirstAuthor et al.)`, bibliography sorted alphabetically by author.
    - **IEEE**: In-text `[1]`, `[2]`, ... dynamically calculated in order of document appearance, bibliography sorted numerically.
  - Real-time style switching with zero page reloads.
  - Deduplication (`AC-07`): Multiple citations of the same reference generate a single bibliography entry.
- **Document & Bibliography Exporter (`IExport`)**:
  - Downloadable **PDF** (rendered via `ReportLab` with academic typography and hanging indents) and **Plain Text (`.txt`)**.
  - Full document export or standalone bibliography export.
  - Automatic pre-build save and stale bibliography synchronization.
  - Clean omission of References section if no citations exist.
- **Admin Portal & Audit Logging (`Administrator`, `AuditLog`)**:
  - System metrics and combined resource counters.
  - User management (Active/Suspended toggle, role management, account deletion).
  - Searchable immutable audit logs.

---

## Quick Start

### 1. Prerequisites
- Python 3.10+ installed.

### 2. Setup Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Run Automated Architectural Tests
```powershell
.\.venv\Scripts\python.exe test_layered_architecture.py
```

### 4. Run the Application
```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open your browser at **`http://127.0.0.1:8000/`**.

---

## Pre-Seeded Demo Accounts

The login screen includes 1-click login buttons for instant testing:

| Role | Name | Email | Password |
|---|---|---|---|
| **Student** | Aaryan Verma | `aaryan@lnmiit.ac.in` | `password123` |
| **Researcher/Faculty** | Earth Agarwal | `earth@lnmiit.ac.in` | `password123` |
| **Administrator** | Adeshwar Singh | `admin@lnmiit.ac.in` | `admin123` |
