"""
Reference Management Module (IReference + ReferenceValidator) and SearchService for CiteNest.
Handles unified search across Central and Personal databases, CRUD operations,
cascading citation cleanup, and multi-facet filtering.
"""

import uuid
import datetime
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from database import get_db
from models import ReferenceLifecycleState, DocumentLifecycleState, CitationStyle, ReferenceSource
from validators import ReferenceValidator
from formatters import CitationEngine
from services.personal_reference_service import PersonalReferenceService


class ReferenceSearchService:
    """
    Unified Search Service combining Central Catalog and Personal Library.
    Enforces Requirement 4:
      1. Searches the central reference catalog.
      2. Searches the authenticated user's personal database.
      3. Combines both result sets.
      4. Identifies each result as either CENTRAL or PERSONAL.
      5. Returns a unified result list with appropriate query limits.
    """

    @staticmethod
    def search_unified(
        user_id: str,
        query: Optional[str] = None,
        ref_type: Optional[str] = None,
        year: Optional[str] = None,
        collection_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        q_clean = (query or "").strip().lower()

        # -------------------------------------------------------------
        # 1. Fetch Central Catalog References (isShared = 1 or ownerId = user_id)
        # -------------------------------------------------------------
        central_refs: List[Dict[str, Any]] = []
        with get_db() as conn:
            cursor = conn.cursor()
            sql = """
                SELECT r.*,
                       GROUP_CONCAT(c.collectionId) AS collectionIds,
                       GROUP_CONCAT(c.name) AS collectionNames
                FROM references_tab r
                LEFT JOIN collection_memberships cm ON r.referenceId = cm.referenceId
                LEFT JOIN collections c ON cm.collectionId = c.collectionId
                WHERE (r.isShared = 1 OR r.ownerId = ?)
            """
            params: List[Any] = [user_id]

            if ref_type and ref_type != "All":
                sql += " AND r.type = ?"
                params.append(ref_type)

            if year and year != "All":
                sql += " AND r.year = ?"
                params.append(year)

            sql += " GROUP BY r.referenceId ORDER BY r.createdDate DESC"
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            for r in rows:
                item = dict(r)
                item["referenceSource"] = ReferenceSource.CENTRAL.value
                c_ids = item["collectionIds"].split(",") if item.get("collectionIds") else []
                c_names = item["collectionNames"].split(",") if item.get("collectionNames") else []
                item["collections"] = [
                    {"collectionId": cid, "name": cname}
                    for cid, cname in zip(c_ids, c_names) if cid
                ]
                central_refs.append(item)

        # -------------------------------------------------------------
        # 2. Fetch Personal References from User's Isolated SQLite Database
        # -------------------------------------------------------------
        personal_refs: List[Dict[str, Any]] = []
        try:
            raw_personal = PersonalReferenceService.get_references(
                user_id=user_id,
                query=query,
                ref_type=ref_type,
                year=year
            )
            # Attach collection memberships for personal refs from central collection_memberships table
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cm.referenceId, c.collectionId, c.name
                    FROM collection_memberships cm
                    JOIN collections c ON cm.collectionId = c.collectionId
                    WHERE c.ownerId = ?;
                """, (user_id,))
                col_map: Dict[str, List[Dict[str, str]]] = {}
                for row in cursor.fetchall():
                    rid = row["referenceId"]
                    if rid not in col_map:
                        col_map[rid] = []
                    col_map[rid].append({"collectionId": row["collectionId"], "name": row["name"]})

            for p in raw_personal:
                p["collections"] = col_map.get(p["referenceId"], [])
                personal_refs.append(p)
        except Exception as e:
            print(f"Notice fetching personal references for {user_id}: {e}")

        # -------------------------------------------------------------
        # 3. Combine and Apply Text Search & Collection Filtering
        # -------------------------------------------------------------
        combined: List[Dict[str, Any]] = []

        for ref in central_refs + personal_refs:
            # Collection filter
            if collection_id and collection_id != "All":
                has_col = any(c.get("collectionId") == collection_id for c in ref.get("collections", []))
                if not has_col:
                    continue

            # In-memory query match if query provided
            if q_clean:
                title_m = q_clean in (ref.get("title") or "").lower()
                author_m = q_clean in (ref.get("authors") or "").lower()
                year_m = q_clean in str(ref.get("year") or "").lower()
                kw_m = q_clean in (ref.get("keywords") or "").lower()
                journal_m = q_clean in (ref.get("journalName") or "").lower()
                site_m = q_clean in (ref.get("siteName") or "").lower()
                pub_m = q_clean in (ref.get("publisher") or "").lower()
                src_m = q_clean in (ref.get("referenceSource") or "").lower()

                if not (title_m or author_m or year_m or kw_m or journal_m or site_m or pub_m or src_m):
                    continue

            combined.append(ref)

        # Sort: newest first
        combined.sort(key=lambda x: x.get("createdDate") or "", reverse=True)

        # Pagination slice
        return combined[offset:offset + limit]


class ReferenceService:
    """Implements IReference interface with cascading deletion safeguards across Central & Personal DBs."""

    @staticmethod
    def get_references(
        owner_id: str,
        query: Optional[str] = None,
        ref_type: Optional[str] = None,
        year: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Unified reference listing combining central catalog & authenticated user's personal DB."""
        return ReferenceSearchService.search_unified(
            user_id=owner_id,
            query=query,
            ref_type=ref_type,
            year=year,
            collection_id=collection_id
        )

    @staticmethod
    def get_reference_by_id(owner_id: str, reference_id: str) -> Optional[Dict[str, Any]]:
        """
        Resolves reference by ID across both Personal DB and Central Catalog.
        Ensures strict access control:
          - A user can only access their own personal references.
          - Central shared references are accessible to all authenticated users.
        """
        # 1. Check personal database first if prefixed with PR- or try personal DB
        personal_ref = PersonalReferenceService.get_reference_by_id(owner_id, reference_id)
        if personal_ref:
            # Attach collection memberships
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT c.collectionId, c.name
                    FROM collection_memberships cm
                    JOIN collections c ON cm.collectionId = c.collectionId
                    WHERE cm.referenceId = ? AND c.ownerId = ?;
                """, (reference_id, owner_id))
                personal_ref["collections"] = [dict(r) for r in cursor.fetchall()]
            return personal_ref

        # 2. Check Central DB
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*,
                       GROUP_CONCAT(c.collectionId) AS collectionIds,
                       GROUP_CONCAT(c.name) AS collectionNames
                FROM references_tab r
                LEFT JOIN collection_memberships cm ON r.referenceId = cm.referenceId
                LEFT JOIN collections c ON cm.collectionId = c.collectionId
                WHERE r.referenceId = ? AND (r.isShared = 1 OR r.ownerId = ?)
                GROUP BY r.referenceId;
            """, (reference_id, owner_id))
            row = cursor.fetchone()
            if row:
                item = dict(row)
                item["referenceSource"] = ReferenceSource.CENTRAL.value
                c_ids = item["collectionIds"].split(",") if item.get("collectionIds") else []
                c_names = item["collectionNames"].split(",") if item.get("collectionNames") else []
                item["collections"] = [
                    {"collectionId": cid, "name": cnames}
                    for cid, cnames in zip(c_ids, c_names) if cid
                ]
                return item

        return None

    @staticmethod
    def add_reference(owner_id: str, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """
        Adds a new reference.
        By default, user-created references are placed into the authenticated user's
        ISOLATED PERSONAL DATABASE (Requirement 3.B: "Do not automatically add personal
        references to the central catalog").
        If explicitly requested as shared/central by an administrator, it is added to central references_tab.
        """
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        is_central = bool(data.get("isShared")) or (data.get("referenceSource") == ReferenceSource.CENTRAL.value)

        if not is_central:
            # Store in User's Personal Database
            success, msg, errs, created = PersonalReferenceService.add_reference(owner_id, data)
            if success and created and data.get("collectionId"):
                # Link to collection if requested
                from services.collection_service import CollectionService
                CollectionService.add_reference_to_collection(owner_id, data["collectionId"], created["referenceId"])
            return success, msg, errs, created

        # Store in Central Database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT referenceId FROM references_tab WHERE referenceId LIKE 'R%' ORDER BY LENGTH(referenceId) DESC, referenceId DESC LIMIT 1;")
            last_r = cursor.fetchone()
            if last_r:
                try:
                    num = int(last_r[0].replace("R", "")) + 1
                    ref_id = f"R{num}"
                except Exception:
                    ref_id = f"R{uuid.uuid4().hex[:4].upper()}"
            else:
                ref_id = "R55"

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            target_collection_id = data.get("collectionId")
            lifecycle_state = ReferenceLifecycleState.IN_COLLECTION.value if target_collection_id else ReferenceLifecycleState.STORED.value

            cursor.execute("""
                INSERT INTO references_tab (
                    referenceId, ownerId, type, title, authors, year,
                    journalName, volumeIssue, pages, publisher, editionPlace,
                    siteName, url, accessDate, keywords, lifecycleState, isShared, createdDate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                ref_id,
                owner_id,
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() if data.get("journalName") else None,
                (data.get("volumeIssue") or "").strip() if data.get("volumeIssue") else None,
                (data.get("pages") or "").strip() if data.get("pages") else None,
                (data.get("publisher") or "").strip() if data.get("publisher") else None,
                (data.get("editionPlace") or "").strip() if data.get("editionPlace") else None,
                (data.get("siteName") or "").strip() if data.get("siteName") else None,
                (data.get("url") or "").strip() if data.get("url") else None,
                (data.get("accessDate") or "").strip() if data.get("accessDate") else None,
                (data.get("keywords") or "").strip(),
                lifecycle_state,
                1,
                now
            ))

            if target_collection_id:
                mem_id = f"M{uuid.uuid4().hex[:5].upper()}"
                cursor.execute("""
                    INSERT INTO collection_memberships (membershipId, collectionId, referenceId, referenceSource)
                    VALUES (?, ?, ?, 'CENTRAL');
                """, (mem_id, target_collection_id, ref_id))

            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Added central reference {ref_id}: '{(data.get('title') or '')[:40]}'", now))

            conn.commit()

        created = ReferenceService.get_reference_by_id(owner_id, ref_id)
        return True, "Central reference saved successfully.", {}, created

    @staticmethod
    def edit_reference(owner_id: str, reference_id: str, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """Re-validates and updates reference in either Personal or Central database."""
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        # Check if it is a personal reference
        is_personal = reference_id.startswith("PR-") or PersonalReferenceService.get_reference_by_id(owner_id, reference_id) is not None

        if is_personal:
            success, msg, errs, updated = PersonalReferenceService.edit_reference(owner_id, reference_id, data)
            if success:
                ReferenceService._refresh_citing_documents(owner_id, reference_id)
            return success, msg, errs, updated

        # Central reference update
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM references_tab WHERE referenceId = ? AND (ownerId = ? OR isShared = 1);", (reference_id, owner_id))
            existing = cursor.fetchone()
            if not existing:
                return False, "Reference not found or access denied.", {}, None

            cursor.execute("""
                UPDATE references_tab SET
                    type = ?,
                    title = ?,
                    authors = ?,
                    year = ?,
                    journalName = ?,
                    volumeIssue = ?,
                    pages = ?,
                    publisher = ?,
                    editionPlace = ?,
                    siteName = ?,
                    url = ?,
                    accessDate = ?,
                    keywords = ?
                WHERE referenceId = ?;
            """, (
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() if data.get("journalName") else None,
                (data.get("volumeIssue") or "").strip() if data.get("volumeIssue") else None,
                (data.get("pages") or "").strip() if data.get("pages") else None,
                (data.get("publisher") or "").strip() if data.get("publisher") else None,
                (data.get("editionPlace") or "").strip() if data.get("editionPlace") else None,
                (data.get("siteName") or "").strip() if data.get("siteName") else None,
                (data.get("url") or "").strip() if data.get("url") else None,
                (data.get("accessDate") or "").strip() if data.get("accessDate") else None,
                (data.get("keywords") or "").strip(),
                reference_id
            ))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Edited reference {reference_id}: '{(data.get('title') or '')[:40]}'", now))

            conn.commit()

        ReferenceService._refresh_citing_documents(owner_id, reference_id)
        updated = ReferenceService.get_reference_by_id(owner_id, reference_id)
        return True, "Reference updated and citing documents refreshed.", {}, updated

    @staticmethod
    def check_cascade_citations(owner_id: str, reference_id: str) -> Dict[str, Any]:
        """Checks whether the reference is cited in any of the user's documents."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT d.documentId, d.title
                FROM citations c
                JOIN documents d ON c.documentId = d.documentId
                WHERE c.referenceId = ? AND d.ownerId = ?;
            """, (reference_id, owner_id))
            citing_docs = [dict(r) for r in cursor.fetchall()]

            return {
                "isCited": len(citing_docs) > 0,
                "citingDocuments": citing_docs,
                "referenceId": reference_id
            }

    @staticmethod
    def delete_reference(owner_id: str, reference_id: str) -> Tuple[bool, str]:
        """
        Performs cascading citation cleanup across citing documents,
        removes collection memberships, and deletes from Personal or Central DB.
        """
        # Determine source
        is_personal = reference_id.startswith("PR-") or PersonalReferenceService.get_reference_by_id(owner_id, reference_id) is not None

        ref_title = ""
        if is_personal:
            pref = PersonalReferenceService.get_reference_by_id(owner_id, reference_id)
            if not pref:
                return False, "Personal reference not found or access denied."
            ref_title = pref["title"]
        else:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT title FROM references_tab WHERE referenceId = ? AND (ownerId = ? OR isShared = 1);", (reference_id, owner_id))
                r = cursor.fetchone()
                if not r:
                    return False, "Reference not found or access denied."
                ref_title = r["title"]

        with get_db() as conn:
            cursor = conn.cursor()
            # Find all citing documents
            cursor.execute("""
                SELECT DISTINCT documentId FROM citations WHERE referenceId = ?;
            """, (reference_id,))
            affected_doc_ids = [r[0] for r in cursor.fetchall()]

            # 1. Remove citations
            cursor.execute("DELETE FROM citations WHERE referenceId = ?;", (reference_id,))

            # 2. Remove collection memberships
            cursor.execute("DELETE FROM collection_memberships WHERE referenceId = ?;", (reference_id,))

            # 3. If central, delete from references_tab
            if not is_personal:
                cursor.execute("DELETE FROM references_tab WHERE referenceId = ?;", (reference_id,))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Deleted reference {reference_id}: '{ref_title[:40]}' (cleaned {len(affected_doc_ids)} docs)", now))

            conn.commit()

        # If personal, delete from user's personal DB
        if is_personal:
            PersonalReferenceService.delete_reference(owner_id, reference_id)

        # Clean document bodies and regenerate bibliographies
        from services.document_service import DocumentService
        for doc_id in affected_doc_ids:
            DocumentService.clean_and_refresh_document_after_reference_delete(owner_id, doc_id, reference_id)

        return True, f"Reference '{ref_title}' deleted and citing documents cleaned up."

    @staticmethod
    def _refresh_citing_documents(owner_id: str, reference_id: str):
        """Regenerates inline citations and bibliographies in citing documents after an edit."""
        from services.document_service import DocumentService
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT d.documentId
                FROM citations c
                JOIN documents d ON c.documentId = d.documentId
                WHERE c.referenceId = ? AND d.ownerId = ?;
            """, (reference_id, owner_id))
            docs = cursor.fetchall()

        for d in docs:
            DocumentService.recompile_document_citations(owner_id, d["documentId"])
