import re

with open('IMPLEMENTATION.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace all em dashes with hyphen
text = text.replace('\u2014', ' - ')

# 1. Update Architecture in Section 1
old_s1 = """### Architecture Pattern
```
Client (SPA) \u2190\u2192 FastAPI REST API \u2190\u2192 Service Layer \u2190\u2192 SQLite (persistent)
                                          \u2502
                           Strategy Pattern Formatters
                          (APAFormatter, MLAFormatter, IEEEFormatter)
```"""

new_s1 = """### Architecture Pattern (Four Logical Layers & Two-Level Databases)

```text
[1. PRESENTATION LAYER] (static/)
     Single-Page Application (HTML5, CSS3, ES2020 JavaScript)
     - Interactive Dashboard, Unified Search with Source Badges (Central vs Personal)
     - Collections Manager, Rich-Text Paper Editor with Inline Citation Tokens
     - Zero direct database access; strictly uses REST API contracts
                                   \u2193 \u2191 REST API (JSON)
[2. APPLICATION LAYER] (services/ & main.py)
     FastAPI Route Controllers & Service Classes
     - AuthService: PBKDF2-SHA256 authentication, session verification & RBAC
     - ReferenceSearchService: Unified search across Central Catalog & Personal Databases
     - ReferenceService: Reference CRUD coordination & cascading citation safeguards
     - PersonalReferenceService: CRUD in isolated per-user SQLite databases
     - CollectionService: Hybrid collection memberships without foreign key coupling
     - DocumentService: Cross-source citation resolution & dynamic sync
     - ExportService: Academic ReportLab PDF and plain text TXT exporter
     - AdminService: Combined multi-source analytics, audit logs & user management
                                   \u2193 \u2191
[3. DOMAIN LAYER] (models.py, validators.py, formatters.py)
     Core Business Entities, Validation Rules & Strategy Formatters
     - models.py: Pydantic models, Enums, ReferenceSource (CENTRAL / PERSONAL)
     - validators.py: ReferenceValidator strict per-type field requirements
     - formatters.py: Strategy Pattern Formatters (APA 7th, MLA 9th, IEEE)
                                   \u2193 \u2191
[4. DATA ACCESS LAYER] (database.py)
     Two-Level SQLite Persistence
     - Central Application Database (citenest.db): Shared catalog references (isShared=1),
       users, active sessions, collections, documents, citations, bibliographies, audit logs
     - Individual User Databases (user_databases/<userId>.db): Private isolated personal
       references, zero authentication secrets, path isolation derived solely from user ID
```"""

text = text.replace(old_s1, new_s1)

# 2. Update models.py enums in Section 4.1
old_enums = """class ReferenceType(str, Enum):
    JOURNAL_ARTICLE = "Journal Article"
    BOOK = "Book"
    WEBSITE = "Website"

class ReferenceLifecycleState(str, Enum):"""

new_enums = """class ReferenceType(str, Enum):
    JOURNAL_ARTICLE = "Journal Article"
    BOOK = "Book"
    WEBSITE = "Website"

class ReferenceSource(str, Enum):
    \"\"\"Identifies which database a reference lives in.\"\"\"
    CENTRAL = "CENTRAL"    # Shared catalog inside citenest.db (isShared=1)
    PERSONAL = "PERSONAL"  # User's personal SQLite DB (user_databases/<userId>.db)

class ReferenceLifecycleState(str, Enum):"""

text = text.replace(old_enums, new_enums)

# Update CollectionMembership model
old_col_model = """class CollectionMembership(BaseModel):
    membershipId: str
    collectionId: str
    referenceId: str"""

new_col_model = """class CollectionMembership(BaseModel):
    membershipId: str
    collectionId: str
    referenceId: str
    referenceSource: str = "CENTRAL"   # "CENTRAL" or "PERSONAL" """

text = text.replace(old_col_model, new_col_model)

# 3. Update SQLite Schema in Section 4.2
old_schema_ref = """-- References
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
);"""

new_schema_ref = """-- References (Central Application Database: citenest.db)
-- isShared = 1: Shared reference available in the Central Catalog for all users
-- isShared = 0: Legacy central personal reference
CREATE TABLE references_tab (
    referenceId TEXT PRIMARY KEY,
    ownerId TEXT NOT NULL,            -- Owner ID or Admin who seeded/added the record
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
    isShared INTEGER NOT NULL DEFAULT 0,
    createdDate TEXT NOT NULL,
    FOREIGN KEY (ownerId) REFERENCES users(userId) ON DELETE CASCADE
);

-- Individual User Personal References (user_databases/<userId>.db)
-- Isolated SQLite file per user; zero auth secrets; accessed only by authenticated owner
CREATE TABLE personal_references (
    referenceId  TEXT PRIMARY KEY,    -- Generated with 'PR-' prefix
    type         TEXT NOT NULL,
    title        TEXT NOT NULL,
    authors      TEXT,
    year         TEXT,
    journalName  TEXT,
    volumeIssue  TEXT,
    pages        TEXT,
    publisher    TEXT,
    editionPlace TEXT,
    siteName     TEXT,
    url          TEXT,
    accessDate   TEXT,
    keywords     TEXT,
    createdDate  TEXT NOT NULL
);"""

text = text.replace(old_schema_ref, new_schema_ref)

# Update Collection Memberships in Section 4.2
old_schema_cm = """-- Collection Memberships (Composition with Collection)
CREATE TABLE collection_memberships (
    membershipId TEXT PRIMARY KEY,
    collectionId TEXT NOT NULL,
    referenceId TEXT NOT NULL,
    FOREIGN KEY (collectionId) REFERENCES collections(collectionId) ON DELETE CASCADE,
    FOREIGN KEY (referenceId) REFERENCES references_tab(referenceId) ON DELETE CASCADE,
    UNIQUE (collectionId, referenceId)
);"""

new_schema_cm = """-- Collection Memberships (Composition with Collection)
-- Supports both Central and Personal references across two databases
-- Note: referenceId validation is enforced by Application Services rather than
-- rigid SQL foreign keys because references reside in separate SQLite files.
CREATE TABLE collection_memberships (
    membershipId TEXT PRIMARY KEY,
    collectionId TEXT NOT NULL,
    referenceId TEXT NOT NULL,
    referenceSource TEXT NOT NULL DEFAULT 'CENTRAL', -- 'CENTRAL' | 'PERSONAL'
    FOREIGN KEY (collectionId) REFERENCES collections(collectionId) ON DELETE CASCADE,
    UNIQUE (collectionId, referenceId)
);"""

text = text.replace(old_schema_cm, new_schema_cm)

# 4. Update Section 6: Reference Management
old_s6 = """## 6. Reference Management - `IReference` + `ReferenceValidator`

**Files**: `services/reference_service.py`, `validators.py`"""

new_s6 = """## 6. Reference Management - Multi-Source & Search (`ReferenceSearchService` + `PersonalReferenceService`)

**Files**: `services/reference_service.py`, `services/personal_reference_service.py`, `validators.py`

### 6.1 Two-Level Reference Storage Architecture
CiteNest separates shared central catalog data from private user libraries:
1. **Central Application Database (`citenest.db`)**: Stores shared reference catalog entries (`isShared = 1`). Visible to all authenticated users. Managed and curated centrally.
2. **Personal Reference Databases (`user_databases/<userId>.db`)**: Lightweight, private SQLite databases automatically initialized when a user creates personal references. Never contains authentication credentials or passwords. Path is strictly computed from authenticated `user_id`, preventing any traversal or unauthorized cross-user access.

### 6.2 Unified Reference Search Service (`ReferenceSearchService`)
Even though references are stored across separate database files, users experience them as one seamless reference management system:
1. **Central Search**: Queries `references_tab` where `(isShared = 1 OR ownerId = user_id)`. Tags records with `referenceSource = 'CENTRAL'`.
2. **Personal Search**: Queries `personal_references` in `user_databases/<userId>.db`. Tags records with `referenceSource = 'PERSONAL'`.
3. **Membership Hydration**: Reads `collection_memberships` from `citenest.db` and attaches collection tags to both central and personal references.
4. **Combination & Filtering**: Combines both sources, applies facet filters (`type`, `year`, `collectionId`, `query`), and applies pagination limits.
5. **UI Badging**: Returns unified results rendered with distinct badges (`Central Catalog` vs `Personal Library`) in the UI."""

text = text.replace(old_s6, new_s6)

# 5. Update Section 7: Collections
old_s7 = """## 7. Collection Module - `ICollection`

**File**: `services/collection_service.py`"""

new_s7 = """## 7. Collection Module - `ICollection` (Hybrid Central & Personal Memberships)

**File**: `services/collection_service.py`

CiteNest collections allow grouping references from either source (Central Catalog or Personal Library):
- **Cross-Source Membership**: `collection_memberships` stores `(membershipId, collectionId, referenceId, referenceSource)`.
- **Application-Level Validation**: Because references reside in two different databases, membership validity is checked by application services (`PersonalReferenceService` for personal references, Central DB for shared references) rather than an inflexible SQL foreign key constraint.
- **Privacy Enforcement**: A user cannot add another user's private personal reference to a collection. Only the user's own personal database is queried.
- **Composition Integrity**: Removing a reference from a collection or deleting a collection deletes the membership record, but **never** deletes the underlying reference from either database."""

text = text.replace(old_s7, new_s7)

# 6. Update Section 8 & 9: Document Editor & Citation Engine
old_s8 = """### Inline Citation Token (HTML structure inside document content)"""

new_s8 = """### Cross-Source Citation Resolution (`_resolve_reference`)
Citations inside documents can cite either Central Catalog references or private Personal Library references:
1. When inserting a citation, `DocumentService._resolve_reference(owner_id, reference_id)` resolves metadata first from the user's personal database, then from the central catalog.
2. Cross-user access is strictly prevented: a user can only cite central shared references or references from their own personal database.
3. Bibliography generation (`IBibliography`) compiles, deduplicates (AC-07), and styles entries uniformly regardless of which database the original reference was stored in.

### Inline Citation Token (HTML structure inside document content)"""

text = text.replace(old_s8, new_s8)

# 7. Update Section 18: Testing & Verification
old_s18 = """### First-Time Setup"""

new_s18 = """### Automated Architectural Verification (13/13 Tests Passing)
Run the automated test suite verifying all 13 criteria for the layered architecture and two-level database model:
```powershell
.\\.venv\\Scripts\\python.exe test_layered_architecture.py
```
Verified criteria:
1. Authentication works with PBKDF2-SHA256 password hashing.
2. Users can create and retrieve personal references.
3. Each user receives an isolated personal database file (`user_databases/<userId>.db`).
4. Strict database isolation: User B cannot access User A's personal references.
5. Central references remain accessible according to access rules.
6. Personal references do not automatically enter the central catalog.
7. Search displays central and personal references together with source badges.
8. Collections support both central and personal references.
9. Central and personal references can both be cited in documents.
10. APA, MLA, and IEEE citation formatting works dynamically.
11. Bibliography compilation and deduplication functions seamlessly.
12. PDF and TXT export operations execute reliably.
13. Existing pre-seeded demo data (D30, R55, collections) is preserved intact.

### First-Time Setup"""

text = text.replace(old_s18, new_s18)

# Final safety check: clean up all em dashes and double spaces
text = text.replace('\u2014', ' - ')
text = re.sub(r' + - +', ' - ', text)

with open('IMPLEMENTATION.md', 'w', encoding='utf-8') as f:
    f.write(text)

print('IMPLEMENTATION.md updated successfully!')
