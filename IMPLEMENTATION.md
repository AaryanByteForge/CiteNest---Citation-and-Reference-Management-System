# CiteNest — End-to-End Implementation Reference

> **One file. Everything.**
> File structure, data models, module interfaces, business rules, API contracts, frontend architecture, citation formatting algorithms, export pipeline, and deployment workflow.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [File Structure](#2-file-structure)
3. [Technology Stack & Dependencies](#3-technology-stack--dependencies)
4. [Data Layer — Models & Schema](#4-data-layer--models--schema)
5. [Authentication Module — `IAuth`](#5-authentication-module--iauth)
6. [Reference Management — `IReference` + `ReferenceValidator`](#6-reference-management--ireference--referencevalidator)
7. [Collection Module — `ICollection`](#7-collection-module--icollection)
8. [Document Editor — `IDocument` / `DocumentEditor`](#8-document-editor--idocument--documenteditor)
9. [Citation Engine — Strategy Pattern (`ICitation`)](#9-citation-engine--strategy-pattern-icitation)
10. [Bibliography Module — `IBibliography`](#10-bibliography-module--ibibliography)
11. [Export Module — `IExport` / `ExportService`](#11-export-module--iexport--exportservice)
12. [Dashboard & Admin — `Administrator` / `AuditLog`](#12-dashboard--admin--administrator--auditlog)
13. [REST API Contract — All Endpoints](#13-rest-api-contract--all-endpoints)
14. [Frontend Architecture](#14-frontend-architecture)
15. [Pre-Seeded Demo Data](#15-pre-seeded-demo-data)
16. [End-to-End Workflows (Use Cases)](#16-end-to-end-workflows-use-cases)
17. [Business Rules Summary](#17-business-rules-summary)
18. [Setup & Deployment](#18-setup--deployment)
19. [Git & Version Control](#19-git--version-control)

---

## 1. Project Overview

**CiteNest** is a production-ready, modular web-based academic Citation & Reference Management System.

### What it does
- Lets academic users (Students, Researchers) store and manage references (Journal Articles, Books, Websites).
- Provides an in-app academic **Paper Editor** with interactive inline citation tokens.
- Dynamically formats in-text citations and bibliographies using a **Strategy Pattern** (APA, MLA, IEEE).
- Compiles, deduplicates, and live-updates the bibliography as citations are inserted or removed.
- Exports formatted documents and bibliographies to **PDF** and **TXT**.
- Gives **Administrators** a portal to manage users, view system-wide metrics, and read immutable audit logs.

### Architecture Pattern
```
Client (SPA) ←→ FastAPI REST API ←→ Service Layer ←→ SQLite (persistent)
                                          │
                           Strategy Pattern Formatters
                          (APAFormatter, MLAFormatter, IEEEFormatter)
```

---

## 2. File Structure

```
Prototype/
│
├── main.py                        # FastAPI app, all REST endpoints, session middleware
├── models.py                      # Pydantic schemas, Enums (UserRole, RefType, DocState...)
├── database.py                    # SQLite init, schema creation, password hashing, demo seeder
├── validators.py                  # ReferenceValidator — per-type field validation (Annex A FR-007)
├── formatters.py                  # Strategy Pattern: CitationStyleFormatter, APA/MLA/IEEE subclasses
├── requirements.txt               # All pip dependencies (pinned versions)
├── README.md                      # Project overview and quickstart
├── IMPLEMENTATION.md              # ← This file
│
├── services/
│   ├── auth_service.py            # AuthService: register, login, verifySession, logout
│   ├── reference_service.py       # ReferenceService: CRUD, search/filter, cascade delete
│   ├── collection_service.py      # CollectionService: collections + memberships
│   ├── document_service.py        # DocumentService: editor, citation insert/remove, bibliography compile
│   ├── export_service.py          # ExportService: PDF (ReportLab) + TXT generation
│   └── admin_service.py           # AdminService: dashboard stats, user management, audit logs
│
├── static/
│   ├── index.html                 # Single-Page Application shell (all views + modals)
│   ├── css/
│   │   └── app.css                # Complete design system (HSL palette, glassmorphism, animations)
│   └── js/
│       └── app.js                 # CiteNestApp class: state, API calls, editor, routing
│
├── .agents/
│   └── rules/
│       └── dependencies.md        # Workspace rule: all packages installed in .venv only
│
├── .gitignore                     # Excludes .venv/, *.db, __pycache__, .env
├── citenest.db                    # SQLite database (auto-created, excluded from git)
└── .venv/                         # Python virtual environment (excluded from git)
```

---

## 3. Technology Stack & Dependencies

### Backend
| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.162.0 | REST API framework |
| `uvicorn` | 0.54.0 | ASGI server |
| `pydantic` | 2.14.1 | Data validation & serialisation |
| `reportlab` | 5.1.0 | Academic PDF generation |
| `python-multipart` | 0.0.32 | Multipart form support |
| `starlette` | 1.10.0 | ASGI toolkit (used by FastAPI) |

### Frontend
| Technology | Purpose |
|---|---|
| Vanilla HTML5 | Single-Page Application shell |
| Vanilla CSS3 | Complete design system (no Tailwind, no Bootstrap) |
| Vanilla JavaScript (ES2020) | `CiteNestApp` class — all interactivity |
| Google Fonts (Inter, Outfit, Cormorant Garamond, JetBrains Mono) | Academic typography |

### Database
- **SQLite** via Python's built-in `sqlite3` module.
- ACID-compliant, foreign keys enforced with `PRAGMA foreign_keys = ON`.
- No ORM — raw SQL for precise control over cascade rules.

### All dependencies are installed exclusively into `.venv/` (workspace policy).

---

## 4. Data Layer — Models & Schema

### 4.1 Enumerations (`models.py`)

```python
class UserRole(str, Enum):
    STUDENT = "Student"
    RESEARCHER = "Researcher/Faculty"
    ADMINISTRATOR = "Administrator"

class AccountStatus(str, Enum):
    ACTIVE = "Active"
    SUSPENDED = "Suspended"

class ReferenceType(str, Enum):
    JOURNAL_ARTICLE = "Journal Article"
    BOOK = "Book"
    WEBSITE = "Website"

class ReferenceLifecycleState(str, Enum):
    ENTERING = "Entering"       # Form is open, not yet saved
    VALIDATING = "Validating"   # Save clicked, running validation
    STORED = "Stored"           # Saved in library, no collection, not cited
    IN_COLLECTION = "InCollection"  # Member of at least one collection
    CITED = "Cited"             # Cited in at least one document

class DocumentLifecycleState(str, Enum):
    DRAFT = "Draft"
    IN_PROGRESS = "In Progress"
    CITATIONS_INSERTED = "Citation(s) Inserted"
    BIBLIOGRAPHY_GENERATED = "Bibliography Generated"
    EXPORTED = "Exported"

class CitationStyle(str, Enum):
    APA = "APA"
    MLA = "MLA"
    IEEE = "IEEE"
```

### 4.2 SQLite Schema (`database.py`)

```sql
-- Users
CREATE TABLE users (
    userId TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    passwordHash TEXT NOT NULL,       -- PBKDF2-SHA256, never plain text
    role TEXT NOT NULL,
    accountStatus TEXT NOT NULL DEFAULT 'Active',
    createdDate TEXT NOT NULL
);

-- Sessions
CREATE TABLE sessions (
    sessionId TEXT PRIMARY KEY,
    userId TEXT NOT NULL,
    startedAt TEXT NOT NULL,
    FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE
);

-- References
CREATE TABLE references_tab (
    referenceId TEXT PRIMARY KEY,
    ownerId TEXT NOT NULL,            -- Data isolation: only owner can access
    type TEXT NOT NULL,               -- "Journal Article" | "Book" | "Website"
    title TEXT NOT NULL,
    authors TEXT,
    year TEXT,
    journalName TEXT,                 -- Required for Journal Article
    volumeIssue TEXT,
    pages TEXT,
    publisher TEXT,                   -- Required for Book
    editionPlace TEXT,
    siteName TEXT,                    -- Optional for Website (required if no authors)
    url TEXT,                         -- Required for Website
    accessDate TEXT,                  -- Required for Website
    keywords TEXT,
    lifecycleState TEXT NOT NULL DEFAULT 'Stored',
    createdDate TEXT NOT NULL,
    FOREIGN KEY (ownerId) REFERENCES users(userId) ON DELETE CASCADE
);

-- Collections
CREATE TABLE collections (
    collectionId TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ownerId TEXT NOT NULL,
    createdDate TEXT NOT NULL,
    FOREIGN KEY (ownerId) REFERENCES users(userId) ON DELETE CASCADE
);

-- Collection Memberships (Composition with Collection)
CREATE TABLE collection_memberships (
    membershipId TEXT PRIMARY KEY,
    collectionId TEXT NOT NULL,
    referenceId TEXT NOT NULL,
    FOREIGN KEY (collectionId) REFERENCES collections(collectionId) ON DELETE CASCADE,
    FOREIGN KEY (referenceId) REFERENCES references_tab(referenceId) ON DELETE CASCADE,
    UNIQUE (collectionId, referenceId)
);

-- Documents
CREATE TABLE documents (
    documentId TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ownerId TEXT NOT NULL,
    citationStyle TEXT NOT NULL DEFAULT 'APA',
    content TEXT,                     -- HTML string with embedded citation tokens
    state TEXT NOT NULL DEFAULT 'Draft',
    createdDate TEXT NOT NULL,
    lastModifiedDate TEXT NOT NULL,
    FOREIGN KEY (ownerId) REFERENCES users(userId) ON DELETE CASCADE
);

-- Citations (Composition with Document — deleting doc deletes citations)
CREATE TABLE citations (
    citationId TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    referenceId TEXT NOT NULL,
    inTextText TEXT,                  -- Dynamically computed, e.g. "(Goodfellow et al., 2016)"
    FOREIGN KEY (documentId) REFERENCES documents(documentId) ON DELETE CASCADE,
    FOREIGN KEY (referenceId) REFERENCES references_tab(referenceId) ON DELETE CASCADE
);

-- Bibliographies (Composition with Document, 1-to-1)
CREATE TABLE bibliographies (
    documentId TEXT PRIMARY KEY,
    entries TEXT NOT NULL DEFAULT '[]',  -- JSON array of formatted entries
    isStale INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (documentId) REFERENCES documents(documentId) ON DELETE CASCADE
);

-- Exported Files
CREATE TABLE exported_files (
    fileId TEXT PRIMARY KEY,
    documentId TEXT NOT NULL,
    format TEXT NOT NULL,             -- "PDF" | "TXT"
    generatedDate TEXT NOT NULL,
    fileName TEXT NOT NULL
);

-- Audit Log (Immutable — no UPDATE/DELETE ever issued against this table)
CREATE TABLE audit_logs (
    logId TEXT PRIMARY KEY,
    actorId TEXT NOT NULL,
    action TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

### 4.3 Password Security (`database.py`)

```python
def hash_password(password: str) -> str:
    salt = "citenest_salt_lnmiit_2026"
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000           # 100,000 iterations
    ).hex()

def verify_password(plain_password: str, password_hash: str) -> bool:
    return hash_password(plain_password) == password_hash
```

---

## 5. Authentication Module — `IAuth`

**File**: `services/auth_service.py`

### Registration (`UC-001`, `FR-001`, `FR-002`)
1. Validate: name not empty, email contains `@`, password ≥ 6 chars, role is `Student` or `Researcher/Faculty`.
2. Check uniqueness: `SELECT userId FROM users WHERE LOWER(email) = ?`.
3. Hash password with PBKDF2-SHA256 before storing — never store plain text (`BR-007`, `NFR-005`).
4. Auto-generate sequential `userId` (e.g., `U103`).
5. Insert user + write AuditLog entry.

### Login (`UC-002`, `FR-003`, `FR-004`)
1. Look up user by email.
2. If no user found or `verify_password()` fails → return `"Invalid email or password"` (non-revealing, `FR-004`).
3. If `accountStatus == "Suspended"` → return suspension message.
4. On success: create `sessionId = "SESS-{uuid}"`, insert into `sessions`, write AuditLog entry.
5. Return user data + `sessionId` to client.

### Session Verification (`verifySession`)
```python
# Called on every protected API endpoint via FastAPI Depends()
def verify_session(session_id: str) -> Optional[Dict]:
    # JOIN sessions + users, check accountStatus != Suspended
    # Returns full user dict or None
```

The `get_current_user` dependency is injected into every protected route:
```python
# Reads from: Authorization: Bearer <token> OR X-Session-ID header OR ?session_id query
def get_current_user(authorization, x_session_id, session_id) -> Dict:
    token = extract_token(...)
    user = AuthService.verify_session(token)
    if not user:
        raise HTTPException(401, "Session expired or invalid.")
    return user
```

### Logout (`FR-005`, `UC-021`)
- `DELETE FROM sessions WHERE sessionId = ?`
- Write AuditLog entry.

---

## 6. Reference Management — `IReference` + `ReferenceValidator`

**Files**: `services/reference_service.py`, `validators.py`

### Validation Rules (`ReferenceValidator.validate`, Annex A FR-007)

| Field | Journal Article | Book | Website |
|---|---|---|---|
| `title` | ✅ Required | ✅ Required | ✅ Required |
| `authors` | ✅ Required | ✅ Required | ⚠️ Required unless `siteName` provided |
| `year` | ✅ Required (4-digit) | ✅ Required | ✅ Required |
| `journalName` | ✅ Required | — | — |
| `volumeIssue` | Optional | — | — |
| `pages` | Optional | — | — |
| `publisher` | — | ✅ Required | — |
| `editionPlace` | — | Optional | — |
| `siteName` | — | — | Optional (required if no authors) |
| `url` | — | — | ✅ Required (must start with `http`) |
| `accessDate` | — | — | ✅ Required |
| `keywords` | Optional | Optional | Optional |

### Add Reference Flow (`UC-004`)
```
User opens "Add Reference" modal
    → State: Entering
User selects type → form dynamically shows type-specific fields
User clicks Save
    → State: Validating
    → ReferenceValidator.validate(data)
    → If errors: highlight fields, return errors dict, keep form open (Entering)
    → If valid: INSERT into references_tab, State: Stored
    → If collectionId provided: INSERT membership → State: InCollection
    → Write AuditLog
    → Return created reference
```

### Edit Reference Flow (`UC-005`, `FR-009`)
```
Re-run ReferenceValidator.validate(data)
If valid:
    UPDATE references_tab SET ...
    _refresh_citing_documents(owner_id, reference_id)
        → For each document that cites this reference:
            → DocumentService.recompile_document_citations(owner_id, doc_id)
            → Re-renders all inline tokens with updated author/year/title
            → Recompiles bibliography
```

### Search & Filter (`SearchService`, `FR-015`, `FR-016`)
```python
# SQL filters applied server-side:
WHERE ownerId = ?                          # Data isolation
  AND type = ? (if ref_type filter)
  AND year = ? (if year filter)

# Then HAVING clause for collection filter:
  HAVING INSTR(',' || collectionIds || ',', ',' || collectionId || ',') > 0

# In-memory keyword search (FR-015) applied after fetch:
# Matches query against: title, authors, year, keywords, journalName, siteName
```

### Cascading Delete (`UC-006`, `FR-010`, `BR-009`)
```
User clicks Delete on reference R
    → GET /api/references/{id}/cascade-check
    → SELECT documentId, title FROM documents WHERE citation.referenceId = R

If NOT cited:
    Standard confirmation dialog
    → On confirm: DELETE membership links, DELETE reference

If CITED in docs [D1, D2, ...]:
    Modal shows: "Are you sure? These documents cite this reference and citations will be removed."
    Lists: "📄 D1 Title", "📄 D2 Title"
    → On confirm:
        DELETE FROM citations WHERE referenceId = R
        DELETE FROM collection_memberships WHERE referenceId = R
        DELETE FROM references_tab WHERE referenceId = R
        For each affected doc:
            → Strip inline tokens for R from doc.content (regex)
            → DocumentService.recompile_document_citations(owner_id, docId)
            → If doc now has 0 citations → state = "In Progress"
    → On cancel: nothing changes
```

### Lifecycle State Transitions for References
```
Entering → (user fills form)
Validating → (save clicked)
    ↓ validation fails → Entering
    ↓ validation passes
Stored → (in library, not in collection, not cited)
    ↓ added to collection
InCollection → (in at least one collection)
    ↓ cited in a document
Cited → (cited in at least one document — highest priority state)
```

---

## 7. Collection Module — `ICollection`

**File**: `services/collection_service.py`

### Composition Rule (Annex D)
> Deleting a `Collection` **automatically deletes** all its `CollectionMembership` records (via `ON DELETE CASCADE`), but **never** deletes the underlying `Reference` records from the user's library.

### Lifecycle Re-evaluation After Collection Delete
```python
for r_id in refs_previously_in_collection:
    if still_cited_in_any_document(r_id):
        state = "Cited"
    elif in_another_collection(r_id):
        state = "InCollection"
    else:
        state = "Stored"
    UPDATE references_tab SET lifecycleState = state WHERE referenceId = r_id
```

### Remove Reference from Collection
- Always permitted, even if it is the reference's last collection.
- Citations pull from the user's full library — collection membership has no bearing on citability.
- Re-evaluates lifecycle state after removal.

---

## 8. Document Editor — `IDocument` / `DocumentEditor`

**File**: `services/document_service.py`, `static/js/app.js`

### Document Lifecycle States
```
Draft
  ↓ (user types content)
In Progress
  ↓ (citation inserted)
Citation(s) Inserted  →  Bibliography Generated  →  Exported
  ↑___________________________↑ (removing all citations goes back to "In Progress")
```

### Rich-Text Editor (Browser-Side)
- Uses native `contenteditable="true"` `<div>` (the `.paper-sheet` element).
- Formatting commands via `document.execCommand()`:
  - Bold: `execCommand('bold')`
  - Italic: `execCommand('italic')`
  - H1/H2/H3: `execCommand('formatBlock', false, 'h1')`
  - Paragraph: `execCommand('formatBlock', false, 'p')`
- Auto-save: triggered 2.5 seconds after the user stops typing.

### Inline Citation Token (HTML structure inside document content)
```html
<span
  class="citenest-citation"
  data-citation-id="CT40"
  data-ref-id="R55"
  contenteditable="false">
  <span class="cite-text">(Goodfellow et al., 2016)</span>
  <button type="button" class="cite-del-btn" title="Remove citation">×</button>
</span>
```
- `data-citation-id` → links to the `citations` table row.
- `data-ref-id` → links to the `references_tab` row.
- The `cite-text` content is dynamically regenerated on every recompile.

### Insert Citation Flow (`UC-015`, Annex D & E)
```
User places cursor in editor
User clicks "Insert Citation" → Citation Picker Drawer focuses
    → If library is empty: show "No references — Add one first" (UC-015 Alt Flow)
User types in picker search box → filters references in real-time
User clicks a reference in the picker:
    1. JS captures current cursor position via window.getSelection()
    2. Inserts text placeholder "__NEW_CITATION_TOKEN__" at cursor
    3. Reads editor innerHTML (includes placeholder)
    4. POST /api/documents/{docId}/citations { referenceId, contentWithToken }
    5. Server:
        a. Generates citationId (e.g., CT41)
        b. Computes preliminary in-text text from formatter
        c. Inserts citation row into citations table
        d. Marks reference lifecycleState = "Cited"
        e. Replaces placeholder in contentWithToken with full token HTML
        f. Saves updated content to document
        g. Calls recompile_document_citations()
        h. Updates document state → "Bibliography Generated"
    6. Client receives updated document, re-renders editor + bibliography
```

### Remove Citation Flow
```
User clicks × on a citation token
    → DELETE /api/documents/{docId}/citations/{citationId}
Server:
    DELETE FROM citations WHERE citationId = ?
    Strip token from content via regex:
        <span[^>]*data-citation-id="CT40"[^>]*>.*?</span>
    If 0 citations remain in doc → state = "In Progress"
    Re-evaluate reference lifecycleState (Cited → InCollection/Stored)
    recompile_document_citations()
Client re-renders.
```

---

## 9. Citation Engine — Strategy Pattern (`ICitation`)

**File**: `formatters.py`

### Class Hierarchy
```
CitationStyleFormatter  (Abstract Base Class)
    ├── APAFormatter
    ├── MLAFormatter
    └── IEEEFormatter

CitationEngine          (Context / Dispatcher)
    .get_formatter(style: CitationStyle) → CitationStyleFormatter
```

### `parse_authors(authors_str)` — Shared Author Parser
Parses strings like `"Goodfellow, I., Bengio, Y., & Courville, A."` into:
```python
[
  {"last": "Goodfellow", "first": "I."},
  {"last": "Bengio",     "first": "Y."},
  {"last": "Courville",  "first": "A."}
]
```
Handles: comma-separated, ampersand-joined, "and"-joined, corporate/org names (single token).

### APA Formatter (`APAFormatter`)

**In-text rules:**
```
1 author  →  (LastName, Year)                      e.g. (Smith, 2020)
2 authors →  (LastName1 & LastName2, Year)         e.g. (Smith & Jones, 2020)
3+ authors → (FirstAuthorLastName et al., Year)    e.g. (Goodfellow et al., 2016)
No authors → (SiteName or ShortTitle, Year)
```

**Bibliography entry format:**
```
Journal:  Author(s). (Year). Title. *Journal Name*, Volume/Issue, Pages.
Book:     Author(s). (Year). *Title* (Edition/Place). Publisher.
Website:  Author(s). (Year). Title. Site Name. Retrieved AccessDate, from URL
```

**Sort**: Alphabetically by first author's last name.

### MLA Formatter (`MLAFormatter`)

**In-text rules:**
```
1 author  →  (LastName Pages) or (LastName) if no pages
2 authors →  (LastName1 and LastName2 Pages)
3+ authors → (FirstAuthor et al. Pages)
```

**Bibliography entry format:**
```
Journal:  Author(s). "Title." *Journal Name*, vol./no., Year, pp. Pages.
Book:     Author(s). *Title*. Edition/Place, Publisher, Year.
Website:  Author(s). "Title." *Site Name*, Year, URL. Accessed AccessDate.
```

**Sort**: Alphabetically by first author's last name.

### IEEE Formatter (`IEEEFormatter`)

**In-text rules:**
```
First appearance of reference R → assign index n (1, 2, 3, ...)
Subsequent appearances of same R → reuse same [n]
Result: [1], [2], [3], etc.
```
*Index assignment is computed during `recompile_document_citations()` by scanning the document HTML for tokens in order.*

**Bibliography entry format:**
```
Journal:  [n] Author(s), "Title," *Journal Name*, vol./issue, pp. Pages, Year.
Book:     [n] Author(s), *Title*, Edition/Place. Publisher, Year.
Website:  [n] Author(s), "Title," *Site Name*, Year. [Online]. Available: URL. [Accessed: AccessDate].
```

**Sort**: Numerically `[1]`, `[2]`, ... in order of appearance.

---

## 10. Bibliography Module — `IBibliography`

**Core function**: `DocumentService.recompile_document_citations(owner_id, document_id)`

### Recompile Algorithm (called after every insert, remove, style change, or edit)
```
1. Fetch document from DB (content, citationStyle)
2. Regex-scan document HTML for all citenest-citation tokens in order of appearance:
      Pattern: <span ... class="citenest-citation" ... data-citation-id="..." data-ref-id="..." ...>
3. Build ordered list of (citation_id, reference_id) tuples
4. For IEEE: assign appearance-order indices {referenceId → n}
5. Fetch all referenced Reference records from DB
6. For each token in document:
      context = {ieee_index: n}
      new_in_text = formatter.format_in_text(ref_data, context)
      Rebuild token HTML with updated <span class="cite-text">new_in_text</span>
      Replace old token HTML in document content string
      UPDATE citations SET inTextText = new_in_text WHERE citationId = ?
7. Build deduplicated bibliography (AC-07):
      unique_rids_ordered = deduplicated list preserving first-appearance order
      For each unique rid:
          entry = formatter.format_bibliography_entry(ref_data, context)
          raw_bib_entries.append(entry)
8. Sort: formatter.sort_bibliography(entries, refs_by_id)
      APA/MLA: sort by first author last name (alphabetical)
      IEEE: sort by index (numeric, in-order)
9. UPSERT bibliographies SET entries = JSON(sorted_entries), isStale = 0
10. Determine new document state:
      0 citations → "In Progress" (or "Draft" if content short)
      1+ citations → "Bibliography Generated"
11. UPDATE documents SET content = new_content, state = new_state
```

### Deduplication Rule (AC-07)
> If the same reference is cited multiple times in a document, **each citation point** gets its own inline token (e.g., multiple `[1]` or `(Smith, 2020)` tokens), but the bibliography contains exactly **one** formatted entry for that reference.

---

## 11. Export Module — `IExport` / `ExportService`

**File**: `services/export_service.py`

### Pre-Export Pipeline (Annex C)
```
User clicks "Export" → choose format (PDF | TXT) + scope (Full | Bibliography Only)
→ Auto-save document if unsaved (DocumentService.save_document)
→ Recompile bibliography if stale (recompile_document_citations)
→ Fetch fresh document + bibliography
→ Build file
→ Trigger download
→ INSERT exported_files record
→ UPDATE document state = "Exported"
```

### TXT Export
```
Full Document:
    {title}
    Citation Style: {style}
    Date: {date}
    ============================================================

    {body — HTML stripped to plain text, headings become line breaks}

    ----------------------------------------
    REFERENCES ({style})
    ----------------------------------------

    {bibliography entries — each entry.text on its own line}

Standalone Bibliography:
    BIBLIOGRAPHY ({style} Style)
    Document: {title}
    {entries}
```

### PDF Export (ReportLab)

**Custom paragraph styles defined:**
```
AcademicTitle   — Helvetica-Bold, 20pt, centered, dark slate
AcademicMeta    — Helvetica, 10pt, centered, muted grey
AcademicH1      — Helvetica-Bold, 15pt
AcademicH2      — Helvetica-Bold, 13pt
AcademicH3      — Helvetica-Bold, 11pt
AcademicBody    — Times-Roman, 11pt, 18pt first-line indent
AcademicBibEntry— Times-Roman, 10pt, 24pt hanging indent (leftIndent=24, firstLineIndent=-24)
```

**HTML-to-PDF conversion:**
1. Strip citation `<span>` tokens, keeping only inner `cite-text` content.
2. Split body HTML by `<h1>`, `<h2>`, `<h3>`, `<p>` blocks.
3. Map each block tag to the corresponding paragraph style.
4. Bibliography entries rendered with `<i>...</i>` preserved (ReportLab supports this).
5. `<a href>` tags stripped (PDF links not supported in basic flow).

### No-Citations Branch (`UC-018` Alt Flow)
> If `len(bib_entries) == 0`, the export omits the "References / Bibliography" section entirely from both PDF and TXT outputs.

---

## 12. Dashboard & Admin — `Administrator` / `AuditLog`

**File**: `services/admin_service.py`

### User Dashboard (`FR-031`, `UC-020`)
```python
{
  "totalReferences": int,
  "totalCollections": int,
  "totalDocuments": int,
  "typeBreakdown": {
      "Journal Article": int,
      "Book": int,
      "Website": int
  },
  "collections": [{"collectionId", "name", "refCount"}],
  "recentDocuments": [last 5 by lastModifiedDate],
  "recentReferences": [last 5 by createdDate]
}
```

### Admin System Metrics (`FR-032`)
```python
{
  "totalUsers": int,
  "activeUsers": int,
  "suspendedUsers": int,
  "totalReferences": int,
  "totalCollections": int,
  "totalDocuments": int,
  "totalExports": int,
  "totalLogs": int
}
```

### Admin User Management
- **Toggle status**: `UPDATE users SET accountStatus = ?` + if Suspended → `DELETE FROM sessions WHERE userId = ?` (immediate session invalidation).
- **Change role**: `UPDATE users SET role = ?` + AuditLog.
- **Delete user**: `DELETE FROM users WHERE userId = ?` — cascades to all their sessions, documents, references, collections.
- **Guard**: Admin cannot delete or suspend their own account.

### Audit Log (`NFR-019`)
- **Immutable**: No `UPDATE` or `DELETE` ever issued against `audit_logs`.
- Events logged: registration, login, logout, reference add/edit/delete, document create/delete, export, admin actions.
- Searchable via `LIKE` across `logId`, `actorId`, `action`.

---

## 13. REST API Contract — All Endpoints

**Base URL**: `http://127.0.0.1:8000`  
**Auth header**: `Authorization: Bearer <sessionId>` (or `X-Session-ID: <sessionId>`)

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | None | Register new user (Student/Researcher only) |
| `POST` | `/api/auth/login` | None | Login; returns `{user: {..., sessionId}}` |
| `GET` | `/api/auth/me` | ✅ | Get current session user data |
| `POST` | `/api/auth/logout` | ✅ | Terminate session |
| `POST` | `/api/auth/reset-demo` | None | Reset DB to Lab 4 demo state |

### Dashboard
| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/dashboard` | ✅ | User dashboard statistics |

### References

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/references` | ✅ | List user's references (query params: `query`, `type`, `year`, `collectionId`) |
| `GET` | `/api/references/{id}` | ✅ | Get single reference |
| `POST` | `/api/references` | ✅ | Create reference (validates, returns errors on 422) |
| `PUT` | `/api/references/{id}` | ✅ | Edit reference (re-validates, refreshes citing docs) |
| `GET` | `/api/references/{id}/cascade-check` | ✅ | Check if reference is cited before delete |
| `DELETE` | `/api/references/{id}` | ✅ | Delete with cascade cleanup |

### Collections

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/collections` | ✅ | List user's collections |
| `POST` | `/api/collections` | ✅ | Create collection |
| `PUT` | `/api/collections/{id}` | ✅ | Rename collection |
| `DELETE` | `/api/collections/{id}` | ✅ | Delete collection (preserves references) |
| `POST` | `/api/collections/{cid}/references/{rid}` | ✅ | Add reference to collection |
| `DELETE` | `/api/collections/{cid}/references/{rid}` | ✅ | Remove reference from collection |

### Documents

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/documents` | ✅ | List user's documents |
| `GET` | `/api/documents/{id}` | ✅ | Get document with citations + bibliography |
| `POST` | `/api/documents` | ✅ | Create document |
| `PUT` | `/api/documents/{id}` | ✅ | Save document (title, content, citationStyle) |
| `DELETE` | `/api/documents/{id}` | ✅ | Delete document (cascades citations + bibliography) |
| `POST` | `/api/documents/{id}/citations` | ✅ | Insert citation at cursor |
| `DELETE` | `/api/documents/{id}/citations/{cid}` | ✅ | Remove inline citation |
| `POST` | `/api/documents/{id}/style` | ✅ | Switch citation style (APA/MLA/IEEE) |

### Export

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/documents/{id}/export?format=PDF&standalone=false` | ✅ | Download PDF or TXT file |

### Admin (Administrator role only)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/admin/metrics` | 🔒 Admin | System-wide metrics |
| `GET` | `/api/admin/users` | 🔒 Admin | All registered users |
| `PUT` | `/api/admin/users/{id}/status` | 🔒 Admin | Toggle Active/Suspended |
| `PUT` | `/api/admin/users/{id}/role` | 🔒 Admin | Change role |
| `DELETE` | `/api/admin/users/{id}` | 🔒 Admin | Delete user account |
| `GET` | `/api/admin/audit-logs?query=&limit=100` | 🔒 Admin | Searchable audit log |

### Validation Error Response Format
```json
{
  "success": false,
  "message": "Validation failed. Please correct the highlighted errors.",
  "errors": {
    "journalName": "Journal Name is required for Journal Articles.",
    "year": "Year must be a 4-digit year (e.g., 2024) or 'n.d.'."
  }
}
```

---

## 14. Frontend Architecture

**Files**: `static/index.html`, `static/css/app.css`, `static/js/app.js`

### SPA Routing (No page reloads)
```javascript
class CiteNestApp {
    navigateTo(viewName) {
        // Hide all views, show target view
        // Update navbar active link
        // Call refreshCurrentView()
    }

    refreshCurrentView() {
        // Routes to the appropriate load function:
        'dashboard'    → loadDashboard()
        'references'   → loadCollections() + loadReferences()
        'collections'  → loadCollectionsView()
        'editor'       → loadEditorView()
        'admin'        → loadAdminPortal()  (checks role === Administrator)
    }
}
```

### State Management
```javascript
this.currentUser      // Active session user (null if logged out)
this.sessionId        // Stored in localStorage
this.references       // Cached reference array
this.collections      // Cached collection array
this.documents        // Cached document list
this.currentDocument  // Full document object with citations + bibliography
this.autoSaveTimer    // setTimeout ref for 2.5s auto-save
```

### API Helper
```javascript
async api(endpoint, options = {}) {
    // Injects Authorization: Bearer <sessionId> header automatically
    // Detects Content-Disposition: attachment → returns {isBlob: true, blob, response}
    // Throws on non-2xx responses
}
```

### Five Views (all in `index.html`, toggled via `display: none/block`)
1. `#view-auth` — Login + Register + 1-Click Demo Switchers
2. `#view-dashboard` — Stat cards + Recent Docs + Collections
3. `#view-references` — Filter bar + Reference list + Add/Edit/Delete actions
4. `#view-collections` — Collection cards + Create/Rename/Delete
5. `#view-editor` — Split pane (paper canvas left, bibliography + picker right)
6. `#view-admin` — Metrics + Users table + Audit log table

### Six Modals (all in `index.html`)
1. `#modal-reference` — Add/Edit Reference with dynamic type-specific fields
2. `#modal-cascade-delete` — Delete confirmation with citing documents warning
3. `#modal-collection` — Create/Rename Collection
4. `#modal-assign-collection` — Checkbox assignment of reference to collections
5. `#modal-export` — Format (PDF/TXT) + Scope (Full/Bibliography) selection
6. `#modal-admin-role` — Admin role change selector

### Design System (`app.css`)
- **Color palette**: HSL-based dark slate (`--bg-main: #0B0F19`, `--primary: #6366F1` indigo)
- **Glassmorphism**: `backdrop-filter: blur(12px)`, translucent card backgrounds
- **Typography**: Inter (UI), Outfit (headings), Cormorant Garamond (paper body), JetBrains Mono (IDs/code)
- **Transitions**: 0.18s fast / 0.28s normal `cubic-bezier(0.4, 0, 0.2, 1)`
- **Micro-interactions**: card hover lift (`translateY(-3px)`), button press shadow, modal scale-in animation
- **Toast notifications**: 4s auto-dismiss, slide-in from right, color-coded by severity

---

## 15. Pre-Seeded Demo Data

**Function**: `database.py:seed_demo_data(force_reset=False)`  
Triggered automatically on first run. Re-triggerable via `POST /api/auth/reset-demo`.

### Accounts

| userId | Name | Email | Password | Role |
|---|---|---|---|---|
| `U101` | Aaryan Verma | `aaryan@lnmiit.ac.in` | `password123` | Student |
| `U102` | Earth Agarwal | `earth@lnmiit.ac.in` | `password123` | Researcher/Faculty |
| `U999` | Adeshwar Singh (Admin) | `admin@lnmiit.ac.in` | `admin123` | Administrator |

### References (owner: U101)

| ID | Type | Title | Key Fields | State |
|---|---|---|---|---|
| `R55` | Book | Deep Learning | Goodfellow et al. (2016), MIT Press, Cambridge MA | `Cited` |
| `R56` | Journal Article | Attention Is All You Need | Vaswani et al. (2017), NIPS, 30(1), pp.5998-6008 | `InCollection` |
| `R57` | Website | APA Style Common Reference Examples Guide | American Psychological Association (2024), apastyle.apa.org | `Stored` |

### Collections (owner: U101)

| ID | Name | Members |
|---|---|---|
| `C10` | ML Research Papers | `R55` (M20), `R56` (M21) |

### Document (owner: U101)

| ID | Title | Style | State |
|---|---|---|---|
| `D30` | Literature Review | APA | Bibliography Generated |

**Document body** contains inline citation token `CT40` referencing `R55`, formatted as `(Goodfellow et al., 2016)`.  
**Bibliography** contains the APA-formatted entry for `R55`.

---

## 16. End-to-End Workflows (Use Cases)

### UC-004 Add Reference
```
1. GET /api/collections            → populate collection dropdown
2. User opens modal, selects type
3. handleRefTypeChange(type)       → toggle field visibility
4. User fills fields
5. POST /api/references {data}
   → validate()
   → If errors → highlight + show messages
   → If valid  → insert + return reference
6. loadReferences()                → refresh list
```

### UC-005 Edit Reference
```
1. User clicks ✏️ Edit on reference card
2. openEditReferenceModal(refId)   → pre-fill all fields
3. User modifies fields
4. PUT /api/references/{id} {data}
   → validate()
   → UPDATE references_tab
   → _refresh_citing_documents()  → recompile all citing docs
5. loadReferences()
```

### UC-006 Delete Reference (Cascading)
```
1. User clicks 🗑️ Delete
2. GET /api/references/{id}/cascade-check
3. If isCited:
      Modal shows citing document titles
      User confirms
      DELETE /api/references/{id}
      Server: strip tokens from docs, recompile, delete
4. If not cited:
      Standard confirm prompt
      DELETE /api/references/{id}
5. loadReferences()
```

### UC-015 Insert Citation
```
1. User is in editor, places cursor
2. Clicks "➕ Insert Citation"
3. Citation picker drawer focused (sidebar)
4. User types in picker search → filterPickerReferences()
5. User clicks a reference
6. insertCitationFromPicker(referenceId):
      Capture cursor via window.getSelection()
      Insert "__NEW_CITATION_TOKEN__" placeholder
      Read editor innerHTML
      POST /api/documents/{id}/citations {referenceId, contentWithToken}
7. Server compiles token, recompiles bibliography
8. Client receives updated document, re-renders
```

### UC-016 Switch Citation Style
```
1. User changes #editor-style-select dropdown
2. handleStyleChange(newStyle)
3. POST /api/documents/{id}/style {citationStyle: "IEEE"}
4. Server:
      UPDATE documents SET citationStyle = "IEEE"
      recompile_document_citations()
      → All tokens re-rendered: (Goodfellow et al., 2016) → [1]
      → Bibliography re-formatted and re-ordered
5. Client re-renders editor + bibliography panel
```

### UC-018 Export Document
```
1. saveCurrentDocument(autoSave=true)  ← pre-build auto-save
2. recompile_document_citations()      ← stale check
3. Fetch fresh document
4. Build file (PDF or TXT):
      If 0 citations: no References section
      If citations: format + append bibliography
5. Return as binary response with Content-Disposition: attachment
6. Client: URL.createObjectURL(blob), programmatic <a> click, download
7. INSERT exported_files record
8. UPDATE document state = "Exported"
```

---

## 17. Business Rules Summary

| Rule | Description |
|---|---|
| `BR-002` | Only 3 reference types: Journal Article, Book, Website |
| `BR-004` | Citations use references from the user's own library only |
| `BR-005` | Removing last citation of a reference removes it from bibliography |
| `BR-006` | Users can only access their own data (strict ownerId isolation) |
| `BR-007` | Passwords must be stored hashed, never plain text |
| `BR-008` | Admin portal accessible only to users with role = Administrator |
| `BR-009` | Deleting a cited reference requires explicit user confirmation with document list |
| `BR-010` | Export formats: PDF and TXT only (no DOCX) |
| `AC-04` | APA/MLA bibliography sorted alphabetically; IEEE sorted numerically by appearance |
| `AC-07` | Same reference cited multiple times → single deduplicated bibliography entry |
| `NFR-004` | Every protected operation must verify the active session before executing |
| `NFR-005` | Passwords stored with a secure hash algorithm (PBKDF2-SHA256) |
| `NFR-018` | Strict data isolation — users never see each other's data |
| `NFR-019` | Audit log is immutable — no modifications permitted |

---

## 18. Setup & Deployment

### Prerequisites
- Python 3.10+ installed and on PATH.
- Git installed.
- Internet access (for Google Fonts in the browser).

### First-Time Setup
```powershell
# 1. Clone the repository
git clone https://github.com/LNMIIT-CS314-2026/T059.git
cd T059

# 2. Create virtual environment (all packages stay local)
python -m venv .venv

# 3. Activate virtual environment
.\.venv\Scripts\Activate.ps1          # PowerShell
# or
.\.venv\Scripts\activate.bat          # CMD

# 4. Install dependencies (into .venv only — workspace policy)
.\.venv\Scripts\pip.exe install -r requirements.txt

# 5. Run the application
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open **`http://127.0.0.1:8000/`** in any browser.

### What happens on first run
1. `init_db()` creates all tables in `citenest.db` (SQLite, local file).
2. `seed_demo_data(force_reset=False)` seeds 3 users, 3 references, 1 collection, 2 memberships, 1 document, 1 citation, 1 bibliography, and 4 audit log entries.
3. FastAPI serves the SPA from `static/index.html`.

### Restarting the Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```
Database persists across restarts — no data is lost.

### Resetting Demo Data
Click **"🔄 Reset Demo Data"** in the navbar, or:
```powershell
curl -X POST http://127.0.0.1:8000/api/auth/reset-demo
```

---

## 19. Git & Version Control

### Repository
```
Remote:  https://github.com/LNMIIT-CS314-2026/T059.git
Branch:  main
```

### What is tracked (committed)
```
.agents/rules/dependencies.md   ← workspace dependency policy
.gitignore
README.md
IMPLEMENTATION.md               ← this file
requirements.txt
models.py
database.py
validators.py
formatters.py
main.py
services/auth_service.py
services/reference_service.py
services/collection_service.py
services/document_service.py
services/export_service.py
services/admin_service.py
static/index.html
static/css/app.css
static/js/app.js
```

### What is excluded (`.gitignore`)
```
.venv/          ← virtual environment (recreated via requirements.txt)
*.db            ← SQLite database (auto-created on first run)
*.sqlite3
__pycache__/
*.py[cod]
.env
.env.local
.vscode/
.idea/
```

### Typical Commit Flow
```powershell
git add .
git commit -m "feat: describe your change here"
git push origin main
```
