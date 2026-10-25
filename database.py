"""
Database and Persistence Layer for CiteNest.
Provides SQLite storage, schema initialization, and demo data seeder.
"""

import sqlite3
import hashlib
import json
import os
import datetime
from typing import Dict, Any, List, Optional
import uuid

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "citenest.db")


def hash_password(password: str) -> str:
    """Hashes password using PBKDF2 with SHA-256."""
    salt = "citenest_salt_lnmiit_2026"
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return hash_password(plain_password) == password_hash


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            userId TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            passwordHash TEXT NOT NULL,
            role TEXT NOT NULL,
            accountStatus TEXT NOT NULL DEFAULT 'Active',
            createdDate TEXT NOT NULL
        );
        """)

        # Sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            sessionId TEXT PRIMARY KEY,
            userId TEXT NOT NULL,
            startedAt TEXT NOT NULL,
            FOREIGN KEY (userId) REFERENCES users (userId) ON DELETE CASCADE
        );
        """)

        # References table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS references_tab (
            referenceId TEXT PRIMARY KEY,
            ownerId TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            authors TEXT,
            year TEXT,
            journalName TEXT,
            volumeIssue TEXT,
            pages TEXT,
            publisher TEXT,
            editionPlace TEXT,
            siteName TEXT,
            url TEXT,
            accessDate TEXT,
            keywords TEXT,
            lifecycleState TEXT NOT NULL DEFAULT 'Stored',
            createdDate TEXT NOT NULL,
            FOREIGN KEY (ownerId) REFERENCES users (userId) ON DELETE CASCADE
        );
        """)

        # Collections table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            collectionId TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ownerId TEXT NOT NULL,
            createdDate TEXT NOT NULL,
            FOREIGN KEY (ownerId) REFERENCES users (userId) ON DELETE CASCADE
        );
        """)

        # Collection Membership table (Composition with Collection)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_memberships (
            membershipId TEXT PRIMARY KEY,
            collectionId TEXT NOT NULL,
            referenceId TEXT NOT NULL,
            FOREIGN KEY (collectionId) REFERENCES collections (collectionId) ON DELETE CASCADE,
            FOREIGN KEY (referenceId) REFERENCES references_tab (referenceId) ON DELETE CASCADE,
            UNIQUE (collectionId, referenceId)
        );
        """)

        # Documents table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            documentId TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            ownerId TEXT NOT NULL,
            citationStyle TEXT NOT NULL DEFAULT 'APA',
            content TEXT,
            state TEXT NOT NULL DEFAULT 'Draft',
            createdDate TEXT NOT NULL,
            lastModifiedDate TEXT NOT NULL,
            FOREIGN KEY (ownerId) REFERENCES users (userId) ON DELETE CASCADE
        );
        """)

        # Citations table (Composition with Document)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS citations (
            citationId TEXT PRIMARY KEY,
            documentId TEXT NOT NULL,
            referenceId TEXT NOT NULL,
            inTextText TEXT,
            FOREIGN KEY (documentId) REFERENCES documents (documentId) ON DELETE CASCADE,
            FOREIGN KEY (referenceId) REFERENCES references_tab (referenceId) ON DELETE CASCADE
        );
        """)

        # Bibliographies table (Composition with Document, 1 to 1)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bibliographies (
            documentId TEXT PRIMARY KEY,
            entries TEXT NOT NULL DEFAULT '[]',
            isStale INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (documentId) REFERENCES documents (documentId) ON DELETE CASCADE
        );
        """)

        # ExportedFiles table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS exported_files (
            fileId TEXT PRIMARY KEY,
            documentId TEXT NOT NULL,
            format TEXT NOT NULL,
            generatedDate TEXT NOT NULL,
            fileName TEXT NOT NULL
        );
        """)

        # AuditLog table (Immutable)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            logId TEXT PRIMARY KEY,
            actorId TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        """)

        conn.commit()


def seed_demo_data(force_reset: bool = False):
    """
    Seeds database with exact pre-seeded demo data from Lab 4 Object Diagram & Annex F.
    If force_reset is True, purges and repopulates all tables.
    """
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users;")
        user_count = cursor.fetchone()[0]

        if user_count > 0 and not force_reset:
            # Already seeded
            return

        if force_reset:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cursor.execute("DELETE FROM audit_logs;")
            cursor.execute("DELETE FROM exported_files;")
            cursor.execute("DELETE FROM bibliographies;")
            cursor.execute("DELETE FROM citations;")
            cursor.execute("DELETE FROM documents;")
            cursor.execute("DELETE FROM collection_memberships;")
            cursor.execute("DELETE FROM collections;")
            cursor.execute("DELETE FROM references_tab;")
            cursor.execute("DELETE FROM sessions;")
            cursor.execute("DELETE FROM users;")
            cursor.execute("PRAGMA foreign_keys = ON;")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 1. Pre-seeded Users
        users = [
            ("U101", "Aaryan Verma", "aaryan@lnmiit.ac.in", hash_password("password123"), "Student", "Active", now),
            ("U102", "Earth Agarwal", "earth@lnmiit.ac.in", hash_password("password123"), "Researcher/Faculty", "Active", now),
            ("U999", "Adeshwar Singh (Admin)", "admin@lnmiit.ac.in", hash_password("admin123"), "Administrator", "Active", now),
        ]
        cursor.executemany("""
            INSERT INTO users (userId, name, email, passwordHash, role, accountStatus, createdDate)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, users)

        # 2. Pre-seeded Collections
        cursor.execute("""
            INSERT INTO collections (collectionId, name, ownerId, createdDate)
            VALUES (?, ?, ?, ?);
        """, ("C10", "ML Research Papers", "U101", now))

        # 3. Pre-seeded References
        references = [
            (
                "R55", "U101", "Book", "Deep Learning",
                "Goodfellow, I., Bengio, Y., & Courville, A.", "2016",
                None, None, None,
                "MIT Press", "Cambridge, MA",
                None, None, None,
                "deep learning, neural networks, machine learning",
                "Cited", now
            ),
            (
                "R56", "U101", "Journal Article", "Attention Is All You Need",
                "Vaswani, A., Shazeer, N., & Parmar, N.", "2017",
                "Advances in Neural Information Processing Systems", "30(1)", "5998-6008",
                None, None,
                None, None, None,
                "transformers, attention mechanism, deep learning, NLP",
                "InCollection", now
            ),
            (
                "R57", "U101", "Website", "APA Style Common Reference Examples Guide",
                "American Psychological Association", "2024",
                None, None, None,
                None, None,
                "APA Style", "https://apastyle.apa.org/instructional-aids/reference-examples.pdf", "2026-10-25",
                "citation style, APA guide, reference manual",
                "Stored", now
            ),
        ]
        cursor.executemany("""
            INSERT INTO references_tab (
                referenceId, ownerId, type, title, authors, year,
                journalName, volumeIssue, pages, publisher, editionPlace,
                siteName, url, accessDate, keywords, lifecycleState, createdDate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, references)

        # 4. Collection Memberships
        memberships = [
            ("M20", "C10", "R55"),
            ("M21", "C10", "R56")
        ]
        cursor.executemany("""
            INSERT INTO collection_memberships (membershipId, collectionId, referenceId)
            VALUES (?, ?, ?);
        """, memberships)

        # 5. Pre-seeded Document & Inline Citation & Bibliography
        doc_content = (
            "<h1>Introduction to Deep Learning Paradigms</h1>"
            "<p>Modern artificial intelligence relies fundamentally on deep representation learning. "
            "In recent foundational literature, deep feedforward networks and optimization algorithms have established "
            "state-of-the-art benchmarks across diverse perceptual domains <span class=\"citenest-citation\" "
            "data-citation-id=\"CT40\" data-ref-id=\"R55\" contenteditable=\"false\">(Goodfellow et al., 2016)</span>. "
            "This literature review examines the structural progression of multilayer architectures and their application to scalable reasoning systems.</p>"
            "<h2>Architectural Evolution</h2>"
            "<p>Subsequent architectural developments transitioned from convolutional hierarchies toward self-attention mechanisms, "
            "further accelerating sequence-to-sequence transformation capabilities.</p>"
        )

        cursor.execute("""
            INSERT INTO documents (
                documentId, title, ownerId, citationStyle, content, state, createdDate, lastModifiedDate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, ("D30", "Literature Review", "U101", "APA", doc_content, "Bibliography Generated", now, now))

        cursor.execute("""
            INSERT INTO citations (citationId, documentId, referenceId, inTextText)
            VALUES (?, ?, ?, ?);
        """, ("CT40", "D30", "R55", "(Goodfellow et al., 2016)"))

        initial_bib_entry = [{
            "referenceId": "R55",
            "html": "Goodfellow, I., Bengio, Y., & Courville, A. (2016). <i>Deep Learning</i> (Cambridge, MA). MIT Press.",
            "text": "Goodfellow, I., Bengio, Y., & Courville, A. (2016). Deep Learning (Cambridge, MA). MIT Press.",
            "style": "APA"
        }]

        cursor.execute("""
            INSERT INTO bibliographies (documentId, entries, isStale)
            VALUES (?, ?, ?);
        """, ("D30", json.dumps(initial_bib_entry), 0))

        # 6. Audit Logs
        audit_entries = [
            ("LOG-001", "SYSTEM", "CiteNest database initialized and demo data seeded", now),
            ("LOG-002", "U101", "User registered and account activated", now),
            ("LOG-003", "U101", "Created document D30 'Literature Review'", now),
            ("LOG-004", "U101", "Inserted inline citation CT40 (R55) into document D30", now),
        ]
        cursor.executemany("""
            INSERT INTO audit_logs (logId, actorId, action, timestamp)
            VALUES (?, ?, ?, ?);
        """, audit_entries)

        conn.commit()


# Automatically initialize and seed if database is new
init_db()
seed_demo_data(force_reset=False)
