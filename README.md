# CiteNest — Citation & Reference Management System

**CiteNest** is an academic citation and reference management platform featuring an integrated academic paper editor, automatic in-text citation generator, dynamic bibliography compiler, and PDF/TXT exporter.

---

## Features

- **Authentication & RBAC (`IAuth`)**:
  - Secure PBKDF2 with SHA-256 password hashing.
  - Role-Based Access Control (`Student`, `Researcher/Faculty`, `Administrator`).
  - Active session verification on all protected endpoints.
- **Strict Per-Type Reference Management (`IReference` + `ReferenceValidator`)**:
  - Validation rules for `Journal Article`, `Book`, and `Website` types.
  - Multi-facet search across titles, authors, publication years, and keywords.
  - Filter by reference type, publication year, and collection.
  - Cascading deletion warning modal listing citing documents before cleanup.
- **Project Collections (`ICollection`)**:
  - Organize references into project groupings.
  - Composition integrity: Deleting a collection removes memberships while preserving underlying library references.
- **Integrated Academic Paper Editor (`IDocument` / `DocumentEditor`)**:
  - In-app rich text formatting (Bold, Italic, Headings H1/H2/H3).
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
  - System metrics and resource counters.
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

### 3. Run the Application
```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open your browser at **`http://127.0.0.1:8000/`**.

---

## Pre-Seeded Demo Accounts (Lab 4 Verification)

The login screen includes 1-click login buttons for instant testing:

| Role | Name | Email | Password |
|---|---|---|---|
| **Student** | Aaryan Verma | `aaryan@lnmiit.ac.in` | `password123` |
| **Researcher/Faculty** | Earth Agarwal | `earth@lnmiit.ac.in` | `password123` |
| **Administrator** | Adeshwar Singh | `admin@lnmiit.ac.in` | `admin123` |

