"""
Data Models and Entity Definitions for CiteNest.
Reconciled with Lab 2, Lab 4, Lab 5, and Annex A/D/E specifications.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid
import datetime


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


class ReferenceSource(str, Enum):
    """Identifies which database a reference lives in."""
    CENTRAL = "CENTRAL"    # Shared catalog inside citenest.db (isShared=1)
    PERSONAL = "PERSONAL"  # User's personal SQLite DB (user_databases/<userId>.db)


class ReferenceLifecycleState(str, Enum):
    ENTERING = "Entering"
    VALIDATING = "Validating"
    STORED = "Stored"
    IN_COLLECTION = "InCollection"
    CITED = "Cited"


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


# --- Pydantic Schemas for API & Entities ---

class User(BaseModel):
    userId: str
    name: str
    email: str
    passwordHash: str
    role: UserRole
    accountStatus: AccountStatus = AccountStatus.ACTIVE
    createdDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class UserPublic(BaseModel):
    userId: str
    name: str
    email: str
    role: UserRole
    accountStatus: AccountStatus
    createdDate: str


class Session(BaseModel):
    sessionId: str
    userId: str
    startedAt: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class Reference(BaseModel):
    referenceId: str
    ownerId: str
    type: ReferenceType
    title: str
    authors: Optional[str] = ""
    year: Optional[str] = ""
    journalName: Optional[str] = None
    volumeIssue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    editionPlace: Optional[str] = None
    siteName: Optional[str] = None
    url: Optional[str] = None
    accessDate: Optional[str] = None
    keywords: Optional[str] = ""
    lifecycleState: ReferenceLifecycleState = ReferenceLifecycleState.STORED
    createdDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class Collection(BaseModel):
    collectionId: str
    name: str
    ownerId: str
    createdDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class CollectionMembership(BaseModel):
    membershipId: str
    collectionId: str
    referenceSource: str = "CENTRAL"   # "CENTRAL" or "PERSONAL"
    referenceId: str


class Citation(BaseModel):
    citationId: str
    documentId: str
    referenceId: str
    inTextText: str = ""


class Bibliography(BaseModel):
    documentId: str
    entries: List[Dict[str, Any]] = []
    isStale: bool = False


class Document(BaseModel):
    documentId: str
    title: str
    ownerId: str
    citationStyle: CitationStyle = CitationStyle.APA
    content: str = ""
    state: DocumentLifecycleState = DocumentLifecycleState.DRAFT
    createdDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    lastModifiedDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class ExportedFile(BaseModel):
    fileId: str
    documentId: str
    format: str  # "PDF" | "TXT"
    generatedDate: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    fileName: str


class AuditLog(BaseModel):
    logId: str
    actorId: str
    action: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
