"""
Document Editor Module (IDocument / DocumentEditor) & Bibliography Engine (IBibliography).
Provides full CRUD, inline citation insertion, dynamic bibliography compilation,
live style switching (APA, MLA, IEEE), and deduplication (AC-07).
"""

import uuid
import datetime
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from database import get_db
from models import DocumentLifecycleState, CitationStyle, ReferenceLifecycleState
from formatters import CitationEngine


class DocumentService:
    """Implements IDocument and IBibliography interfaces."""

    @staticmethod
    def get_user_documents(owner_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.*,
                       COUNT(c.citationId) AS citationCount
                FROM documents d
                LEFT JOIN citations c ON d.documentId = c.documentId
                WHERE d.ownerId = ?
                GROUP BY d.documentId
                ORDER BY d.lastModifiedDate DESC;
            """, (owner_id,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def get_document_by_id(owner_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM documents WHERE documentId = ? AND ownerId = ?;
            """, (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return None

            doc_dict = dict(doc)

            # Fetch citations
            cursor.execute("""
                SELECT c.*, r.title AS refTitle, r.authors AS refAuthors, r.year AS refYear, r.type AS refType
                FROM citations c
                JOIN references_tab r ON c.referenceId = r.referenceId
                WHERE c.documentId = ?;
            """, (document_id,))
            doc_dict["citations"] = [dict(r) for r in cursor.fetchall()]

            # Fetch bibliography
            cursor.execute("SELECT entries, isStale FROM bibliographies WHERE documentId = ?;", (document_id,))
            bib = cursor.fetchone()
            if bib:
                doc_dict["bibliography"] = {
                    "entries": json.loads(bib["entries"]),
                    "isStale": bool(bib["isStale"])
                }
            else:
                doc_dict["bibliography"] = {"entries": [], "isStale": False}

            return doc_dict

    @staticmethod
    def create_document(owner_id: str, title: str, citation_style: str = "APA") -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        title = title.strip()
        if not title:
            return False, "Document title cannot be empty.", None

        if citation_style not in ["APA", "MLA", "IEEE"]:
            citation_style = "APA"

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT documentId FROM documents WHERE documentId LIKE 'D%' ORDER BY LENGTH(documentId) DESC, documentId DESC LIMIT 1;")
            last_d = cursor.fetchone()
            if last_d:
                try:
                    num = int(last_d[0].replace("D", "")) + 1
                    doc_id = f"D{num}"
                except Exception:
                    doc_id = f"D{uuid.uuid4().hex[:4].upper()}"
            else:
                doc_id = "D30"

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            initial_content = f"<h1>{title}</h1><p>Start writing your academic paper here...</p>"

            cursor.execute("""
                INSERT INTO documents (
                    documentId, title, ownerId, citationStyle, content, state, createdDate, lastModifiedDate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (doc_id, title, owner_id, citation_style, initial_content, DocumentLifecycleState.DRAFT.value, now, now))

            cursor.execute("""
                INSERT INTO bibliographies (documentId, entries, isStale)
                VALUES (?, ?, ?);
            """, (doc_id, "[]", 0))

            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Created document '{title}' ({doc_id})", now))

            conn.commit()

            doc = DocumentService.get_document_by_id(owner_id, doc_id)
            return True, "Document created successfully.", doc

    @staticmethod
    def save_document(owner_id: str, document_id: str, title: str, content: str, citation_style: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        title = title.strip()
        if not title:
            return False, "Document title cannot be empty.", None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return False, "Document not found or access denied.", None

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Determine state
            cursor.execute("SELECT COUNT(*) FROM citations WHERE documentId = ?;", (document_id,))
            cit_count = cursor.fetchone()[0]

            if cit_count > 0:
                new_state = DocumentLifecycleState.BIBLIOGRAPHY_GENERATED.value
            elif content and len(content.strip()) > 30:
                new_state = DocumentLifecycleState.IN_PROGRESS.value
            else:
                new_state = DocumentLifecycleState.DRAFT.value

            cursor.execute("""
                UPDATE documents SET
                    title = ?,
                    content = ?,
                    citationStyle = ?,
                    state = ?,
                    lastModifiedDate = ?
                WHERE documentId = ? AND ownerId = ?;
            """, (title, content, citation_style, new_state, now, document_id, owner_id))

            conn.commit()

        # Recompile to ensure sync
        DocumentService.recompile_document_citations(owner_id, document_id)
        updated = DocumentService.get_document_by_id(owner_id, document_id)
        return True, "Document saved successfully.", updated

    @staticmethod
    def delete_document(owner_id: str, document_id: str) -> Tuple[bool, str]:
        """
        Deletes document and cascades deletion of its Citation and Bibliography instances.
        Re-evaluates lifecycleState of referenced records.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return False, "Document not found or access denied."

            doc_title = doc["title"]

            # Fetch references cited in this doc
            cursor.execute("SELECT DISTINCT referenceId FROM citations WHERE documentId = ?;", (document_id,))
            cited_refs = [r[0] for r in cursor.fetchall()]

            # Citations and Bibliographies have ON DELETE CASCADE or explicit delete
            cursor.execute("DELETE FROM citations WHERE documentId = ?;", (document_id,))
            cursor.execute("DELETE FROM bibliographies WHERE documentId = ?;", (document_id,))
            cursor.execute("DELETE FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))

            # Re-evaluate lifecycleState of cited references
            for r_id in cited_refs:
                cursor.execute("SELECT COUNT(*) FROM citations WHERE referenceId = ?;", (r_id,))
                still_cited = cursor.fetchone()[0] > 0
                if not still_cited:
                    cursor.execute("SELECT COUNT(*) FROM collection_memberships WHERE referenceId = ?;", (r_id,))
                    in_col = cursor.fetchone()[0] > 0
                    st = ReferenceLifecycleState.IN_COLLECTION.value if in_col else ReferenceLifecycleState.STORED.value
                    cursor.execute("UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;", (st, r_id))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Deleted document '{doc_title}' ({document_id})", now))

            conn.commit()
            return True, f"Document '{doc_title}' deleted."

    @staticmethod
    def insert_citation(
        owner_id: str,
        document_id: str,
        reference_id: str,
        content_with_token: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Inserts citation into document:
        - Creates Citation entity with unique citationId (CT40...)
        - Inserts inline token into document content
        - Updates reference lifecycleState to 'Cited'
        - Recompiles document in-text citations and bibliography
        - Applies deduplication (AC-07)
        - Updates document state to 'Bibliography Generated'
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return False, "Document not found or access denied.", None

            cursor.execute("SELECT * FROM references_tab WHERE referenceId = ? AND ownerId = ?;", (reference_id, owner_id))
            ref = cursor.fetchone()
            if not ref:
                return False, "Reference not found in your library.", None

            # Generate citationId (e.g. CT41)
            cursor.execute("SELECT citationId FROM citations WHERE citationId LIKE 'CT%' ORDER BY LENGTH(citationId) DESC, citationId DESC LIMIT 1;")
            last_ct = cursor.fetchone()
            if last_ct:
                try:
                    num = int(last_ct[0].replace("CT", "")) + 1
                    citation_id = f"CT{num}"
                except Exception:
                    citation_id = f"CT{uuid.uuid4().hex[:4].upper()}"
            else:
                citation_id = "CT40"

            # Compute preliminary in-text text
            style = doc["citationStyle"]
            formatter = CitationEngine.get_formatter(style)
            in_text_text = formatter.format_in_text(dict(ref), {"ieee_index": 1})

            # Insert into citations table
            cursor.execute("""
                INSERT INTO citations (citationId, documentId, referenceId, inTextText)
                VALUES (?, ?, ?, ?);
            """, (citation_id, document_id, reference_id, in_text_text))

            # Mark reference as Cited
            cursor.execute("""
                UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;
            """, (ReferenceLifecycleState.CITED.value, reference_id))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Handle content update if client provided content where token should be injected
            current_content = doc["content"] or ""
            token_html = (
                f'<span class="citenest-citation" data-citation-id="{citation_id}" '
                f'data-ref-id="{reference_id}" contenteditable="false">'
                f'<span class="cite-text">{in_text_text}</span>'
                f'<button type="button" class="cite-del-btn" title="Remove citation">&times;</button></span>'
            )

            if content_with_token:
                # If client replaced placeholder with token_html
                final_content = content_with_token.replace("__NEW_CITATION_TOKEN__", token_html)
            else:
                # Append to end of content or last paragraph
                if "</p>" in current_content:
                    final_content = current_content[::-1].replace(">p/<", f">{token_html}p/<"[::-1], 1)[::-1]
                else:
                    final_content = current_content + f" {token_html}"

            cursor.execute("""
                UPDATE documents SET
                    content = ?,
                    state = ?,
                    lastModifiedDate = ?
                WHERE documentId = ?;
            """, (final_content, DocumentLifecycleState.BIBLIOGRAPHY_GENERATED.value, now, document_id))

            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Inserted citation {citation_id} (Ref: {reference_id}) into doc {document_id}", now))

            conn.commit()

        # Recompile in-text citations (order of appearance) and bibliography
        DocumentService.recompile_document_citations(owner_id, document_id)
        updated_doc = DocumentService.get_document_by_id(owner_id, document_id)
        return True, "Citation inserted and bibliography updated.", updated_doc

    @staticmethod
    def remove_citation(owner_id: str, document_id: str, citation_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Removes an inline citation:
        - Removes citation record
        - Strips token from document content
        - If no other citations of this reference remain in any doc, re-evaluates reference lifecycleState
        - If document now has 0 citations, transitions back to 'In Progress'
        - Recompiles bibliography
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return False, "Document not found or access denied.", None

            cursor.execute("SELECT referenceId FROM citations WHERE citationId = ? AND documentId = ?;", (citation_id, document_id))
            cit = cursor.fetchone()
            if not cit:
                return False, "Citation not found.", None

            ref_id = cit["referenceId"]

            # Remove citation record
            cursor.execute("DELETE FROM citations WHERE citationId = ?;", (citation_id,))

            # Remove token from content via regex
            content = doc["content"] or ""
            pattern = re.compile(rf'<span[^>]*data-citation-id=["\']{re.escape(citation_id)}["\'][^>]*>.*?</span>', re.DOTALL | re.IGNORECASE)
            new_content = pattern.sub("", content)

            # Check remaining citations for this document
            cursor.execute("SELECT COUNT(*) FROM citations WHERE documentId = ?;", (document_id,))
            remaining_in_doc = cursor.fetchone()[0]

            new_state = DocumentLifecycleState.BIBLIOGRAPHY_GENERATED.value if remaining_in_doc > 0 else DocumentLifecycleState.IN_PROGRESS.value
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute("""
                UPDATE documents SET
                    content = ?,
                    state = ?,
                    lastModifiedDate = ?
                WHERE documentId = ?;
            """, (new_content, new_state, now, document_id))

            # Re-evaluate reference lifecycleState
            cursor.execute("SELECT COUNT(*) FROM citations WHERE referenceId = ?;", (ref_id,))
            still_cited = cursor.fetchone()[0] > 0
            if not still_cited:
                cursor.execute("SELECT COUNT(*) FROM collection_memberships WHERE referenceId = ?;", (ref_id,))
                in_col = cursor.fetchone()[0] > 0
                st = ReferenceLifecycleState.IN_COLLECTION.value if in_col else ReferenceLifecycleState.STORED.value
                cursor.execute("UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;", (st, ref_id))

            conn.commit()

        DocumentService.recompile_document_citations(owner_id, document_id)
        updated = DocumentService.get_document_by_id(owner_id, document_id)
        return True, "Citation removed.", updated

    @staticmethod
    def change_citation_style(owner_id: str, document_id: str, new_style: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Switches document citation style (APA, MLA, IEEE).
        Immediately re-renders all in-text citation tokens and recompiles bibliography.
        """
        if new_style not in ["APA", "MLA", "IEEE"]:
            return False, "Invalid citation style specified.", None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return False, "Document not found or access denied.", None

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("UPDATE documents SET citationStyle = ?, lastModifiedDate = ? WHERE documentId = ?;", (new_style, now, document_id))
            conn.commit()

        DocumentService.recompile_document_citations(owner_id, document_id)
        updated = DocumentService.get_document_by_id(owner_id, document_id)
        return True, f"Citation style switched to {new_style}.", updated

    @staticmethod
    def recompile_document_citations(owner_id: str, document_id: str):
        """
        Core Bibliography & Citation Compiler:
        1. Reads document content and parses inline citation tokens in order of appearance.
        2. Syncs citations table if tokens were inserted or removed directly.
        3. For IEEE: dynamically assigns [1], [2], ... based on first appearance order.
        4. Updates each inline token's text inside the document HTML.
        5. Compiles deduplicated bibliography entries formatted in document.citationStyle (AC-07).
        6. Sorts bibliography according to style rules (APA/MLA alphabetical, IEEE numerical).
        7. Saves updated content and bibliography to database.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE documentId = ?;", (document_id,))
            doc = cursor.fetchone()
            if not doc:
                return

            content = doc["content"] or ""
            style = doc["citationStyle"]
            formatter = CitationEngine.get_formatter(style)

            # Find all citation tokens in document content in order of appearance
            # Pattern: <span ... data-citation-id="..." data-ref-id="..." ...>
            token_pattern = re.compile(
                r'<span\s+[^>]*class=["\'][^"\']*citenest-citation[^"\']*["\'][^>]*>',
                re.IGNORECASE
            )

            # Extract list of tokens: (full_tag, citation_id, ref_id)
            tokens = []
            for match in re.finditer(r'<span\s+([^>]*class=["\'][^"\']*citenest-citation[^"\']*["\'][^>]*)>(.*?)</span>', content, re.DOTALL | re.IGNORECASE):
                attrs = match.group(1)
                inner = match.group(2)
                cid_m = re.search(r'data-citation-id=["\']([^"\']+)["\']', attrs)
                rid_m = re.search(r'data-ref-id=["\']([^"\']+)["\']', attrs)
                if cid_m and rid_m:
                    tokens.append({
                        "full_match": match.group(0),
                        "citation_id": cid_m.group(1),
                        "reference_id": rid_m.group(1),
                        "inner": inner
                    })

            # Fetch references for all cited reference IDs
            cited_ref_ids = [t["reference_id"] for t in tokens]
            # Also check if any citations exist in citations table
            cursor.execute("SELECT referenceId FROM citations WHERE documentId = ?;", (document_id,))
            db_ref_ids = [r[0] for r in cursor.fetchall()]

            all_ref_ids = list(dict.fromkeys(cited_ref_ids + db_ref_ids))

            refs_by_id: Dict[str, Dict[str, Any]] = {}
            if all_ref_ids:
                placeholders = ",".join(["?"] * len(all_ref_ids))
                cursor.execute(f"SELECT * FROM references_tab WHERE referenceId IN ({placeholders});", all_ref_ids)
                for r in cursor.fetchall():
                    refs_by_id[r["referenceId"]] = dict(r)

            # Assign IEEE indices in order of appearance of unique references
            ieee_index_by_ref: Dict[str, int] = {}
            next_ieee_idx = 1
            for t in tokens:
                rid = t["reference_id"]
                if rid not in ieee_index_by_ref:
                    ieee_index_by_ref[rid] = next_ieee_idx
                    next_ieee_idx += 1

            # Format in-text text for each token and update HTML
            new_content = content
            for t in tokens:
                rid = t["reference_id"]
                cid = t["citation_id"]
                ref_data = refs_by_id.get(rid, {})

                context = {"ieee_index": ieee_index_by_ref.get(rid, 1)}
                in_text_text = formatter.format_in_text(ref_data, context)

                # Reconstruct token HTML
                new_token_html = (
                    f'<span class="citenest-citation" data-citation-id="{cid}" '
                    f'data-ref-id="{rid}" contenteditable="false">'
                    f'<span class="cite-text">{in_text_text}</span>'
                    f'<button type="button" class="cite-del-btn" title="Remove citation">&times;</button></span>'
                )

                # Replace in new_content
                new_content = new_content.replace(t["full_match"], new_token_html, 1)

                # Update citations table
                cursor.execute("""
                    UPDATE citations SET inTextText = ? WHERE citationId = ?;
                """, (in_text_text, cid))

            # Compile deduplicated bibliography (AC-07)
            # Unique references cited
            unique_rids_ordered = []
            for t in tokens:
                if t["reference_id"] not in unique_rids_ordered:
                    unique_rids_ordered.append(t["reference_id"])

            raw_bib_entries = []
            for rid in unique_rids_ordered:
                ref_data = refs_by_id.get(rid)
                if not ref_data:
                    continue
                context = {"ieee_index": ieee_index_by_ref.get(rid, 1)}
                entry = formatter.format_bibliography_entry(ref_data, context)
                raw_bib_entries.append(entry)

            # Sort bibliography according to style strategy
            sorted_bib_entries = formatter.sort_bibliography(raw_bib_entries, refs_by_id)

            # Save bibliography
            cursor.execute("""
                INSERT INTO bibliographies (documentId, entries, isStale)
                VALUES (?, ?, 0)
                ON CONFLICT(documentId) DO UPDATE SET
                    entries = excluded.entries,
                    isStale = 0;
            """, (document_id, json.dumps(sorted_bib_entries)))

            # Update document content and state
            state = DocumentLifecycleState.BIBLIOGRAPHY_GENERATED.value if len(sorted_bib_entries) > 0 else (
                DocumentLifecycleState.IN_PROGRESS.value if len(new_content.strip()) > 30 else DocumentLifecycleState.DRAFT.value
            )

            cursor.execute("""
                UPDATE documents SET content = ?, state = ? WHERE documentId = ?;
            """, (new_content, state, document_id))

            conn.commit()

    @staticmethod
    def clean_and_refresh_document_after_reference_delete(owner_id: str, document_id: str, deleted_ref_id: str):
        """
        Removes any residual inline tokens for deleted_ref_id from document content
        and recompiles bibliography.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM documents WHERE documentId = ? AND ownerId = ?;", (document_id, owner_id))
            doc = cursor.fetchone()
            if not doc:
                return

            content = doc["content"] or ""
            # Regex to match citation tokens referencing deleted_ref_id
            pattern = re.compile(rf'<span[^>]*data-ref-id=["\']{re.escape(deleted_ref_id)}["\'][^>]*>.*?</span>', re.DOTALL | re.IGNORECASE)
            cleaned_content = pattern.sub("", content)

            cursor.execute("UPDATE documents SET content = ? WHERE documentId = ?;", (cleaned_content, document_id))
            conn.commit()

        DocumentService.recompile_document_citations(owner_id, document_id)
