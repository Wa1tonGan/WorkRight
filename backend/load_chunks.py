"""Load knowledge/ chunks into Postgres + pgvector WITH the 12-field metadata.

    chunking.py ─▶ our code ─▶ Ollama(bge-m3) ─▶ 1024 floats
                      └──────────────────────▶ SQLAlchemy upsert

Metadata policy (agreed 2026-09-14):
- per-chunk fields (topic/subtopic/section/jurisdiction/authority/source_type)
  come from the explicit maps below — derived from the documents themselves,
  never guessed at load time;
- copied fields (version/effective dates/source_url) ALWAYS come from the
  policy_documents master row, then a drift audit proves the copies agree.

Idempotent: rerun upserts by chunk_id and re-embeds text→vector in one batch.

Run:  uv run python -m backend.load_chunks
"""

from datetime import date

from ollama import embed
from sqlalchemy import func, select, text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .chunking import chunk_handbook, chunk_legal, HANDBOOK_PATH, LEGAL_PATH
from .database import engine
from .models import PolicyChunk, PolicyDocument

EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024
V1_JURISDICTION = ["peninsular_malaysia", "labuan"]  # EA 1955 applies to both

JTKSM_URL = (
    "https://jtksm.mohr.gov.my/sites/default/files/2023-11/"
    "Akta%20Kerja%201955%20%28Akta%20265%29.pdf"
)

# ── document masters (place of record for the copied fields) ────────────────
LEGAL = {
    "local_path": "knowledge/law/workright_legal_policy_v1.md",
    "title": "WorkRight Legal Policy Corpus V1",
    "source_type": "law",
    "version": "v1 (normalized, EA 1955 as at 2023-01-01)",
    "authority": "JTKSM (Malaysia)",
    "effective_from": date(2023, 1, 1),
    "effective_to": None,
    "source_url": JTKSM_URL,
}
HANDBOOK = {
    "local_path": "knowledge/company/workright_employee_handbook_v1.md",
    "title": "WorkRight Labs Employee Leave & Flexible Work Policy Handbook",
    "source_type": "company_policy",
    "version": "1.0",
    "authority": "WorkRight Labs Sdn. Bhd.",
    "effective_from": date(2026, 1, 1),
    "effective_to": None,
    "source_url": None,
}

# ── per-chunk metadata: (topic, subtopic, section, chunk source_type, chunk authority)
# Law: source_type splits per user vocabulary — chunks citing JTKSM
# interpretation are 'official_guidance', pure statutory summaries are 'law'.
LEGAL_META = {
    "LAW-001": ("scope", "v1_applicability", None, "official_guidance",
                "JTKSM / Employment Act 1955"),
    "LAW-002": ("policy_precedence", "statutory_minimum", "7A", "law",
                "Employment Act 1955, sections 7 and 7A"),
    "LAW-003": ("annual_leave", "entitlement", "60E", "law",
                "Employment Act 1955, s.60E"),
    "LAW-004": ("annual_leave", "conditions", "60E", "law",
                "Employment Act 1955, s.60E"),
    "LAW-005": ("sick_leave", "entitlement", "60F", "official_guidance",
                "Employment Act 1955, s.60F; JTKSM guidance"),
    "LAW-006": ("sick_leave", "certification_and_notification", "60F", "law",
                "Employment Act 1955, s.60F"),
    "LAW-007": ("fwa", "types", "60P", "law", "Employment Act 1955, s.60P"),
    "LAW-008": ("fwa", "application_process", "60Q", "law",
                "Employment Act 1955, s.60Q"),
}
HANDBOOK_META = {
    "HB-001": ("policy_scope", "purpose", "1",),
    "HB-002": ("policy_scope", "v1_applicability", "2",),
    "HB-003": ("policy_precedence", "law_vs_company", "3",),
    "HB-004": ("annual_leave", "policy_full_section", "4",),
    "HB-005": ("sick_leave", "entitlement_and_certification", "5",),
    "HB-006": ("hospitalisation_leave", "entitlement", "6",),
    "HB-007": ("fwa", "application_process", "7",),
    "HB-008": ("approval_escalation", "escalation_rules", "8",),
    "HB-009": ("agent_rules", "authorization", "9",),
    "HB-010": ("agent_rules", "resolution_order", "10",),
}

# drift audit: copied chunk fields must agree with the document master
DRIFT_SQL = sa_text("""
    SELECT pc.chunk_id
    FROM policy_chunks pc
    JOIN policy_documents pd ON pd.id = pc.document_id
    WHERE pc.version       IS DISTINCT FROM pd.version
       OR pc.effective_from IS DISTINCT FROM pd.effective_from
       OR pc.effective_to    IS DISTINCT FROM pd.effective_to
       OR pc.source_url      IS DISTINCT FROM pd.source_url
""")


def _meta_or_die(meta: dict, chunk_id: str, allow_none_authority: bool):
    if chunk_id not in meta:
        raise KeyError(f"no metadata mapping for chunk {chunk_id!r} — "
                       f"add it to the loader map (or fix the chunker)")
    return meta[chunk_id]


def main() -> None:
    legal_chunks = chunk_legal(LEGAL_PATH)
    handbook_chunks = chunk_handbook(HANDBOOK_PATH)

    # completeness both ways: every chunk has meta, every meta has a chunk
    ids = {c.chunk_id for c in legal_chunks} | {c.chunk_id for c in handbook_chunks}
    extra = (set(LEGAL_META) | {k for k in HANDBOOK_META}) - ids
    if extra:
        raise KeyError(f"metadata maps mention chunks that don't exist: {extra}")

    with Session(engine) as session:
        doc_ids = {}
        for doc in (LEGAL, HANDBOOK):
            stmt = (
                pg_insert(PolicyDocument)
                .values(**doc)
                .on_conflict_do_update(index_elements=["local_path"],
                                       set_={k: doc[k] for k in doc if k != "local_path"})
                .returning(PolicyDocument.id)
            )
            doc_ids[doc["local_path"]] = session.execute(stmt).scalar_one()
        session.commit()

        def build(doc_chunks, doc, meta):
            rows = []
            for c in doc_chunks:
                if c.chunk_id in meta and len(meta[c.chunk_id]) == 5:  # legal
                    topic, subtopic, section, source_type, authority = meta[c.chunk_id]
                elif c.chunk_id in meta:                                # handbook
                    topic, subtopic, section = meta[c.chunk_id]
                    source_type, authority = doc["source_type"], doc["authority"]
                else:
                    topic, subtopic, section, source_type, authority = _meta_or_die(
                        meta, c.chunk_id, False
                    )
                rows.append({
                    "chunk_id": c.chunk_id,
                    "document_id": doc_ids[doc["local_path"]],
                    # copied from master:
                    "source_type": source_type,   # per-chunk (law vs guidance can differ)
                    "version": doc["version"],
                    "effective_from": doc["effective_from"],
                    "effective_to": doc["effective_to"],
                    "source_url": doc["source_url"],
                    # chunk-specific:
                    "topic": topic,
                    "subtopic": subtopic,
                    "section": section,
                    "jurisdiction": V1_JURISDICTION,
                    "authority": authority,
                    "text": c.text,
                })
            return rows

        rows = build(legal_chunks, LEGAL, LEGAL_META) + build(handbook_chunks, HANDBOOK, HANDBOOK_META)

        vectors = embed(model=EMBEDDING_MODEL, input=[r["text"] for r in rows])["embeddings"]
        assert all(len(v) == EMBEDDING_DIM for v in vectors), "dimension mismatch"
        for r, vec in zip(rows, vectors):
            r["embedding"] = vec

        stmt = pg_insert(PolicyChunk).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["chunk_id"],
            set_={k: stmt.excluded[k] for k in rows[0] if k != "chunk_id"},
        )
        session.execute(stmt)
        session.commit()

        drift = session.execute(DRIFT_SQL).fetchall()
        embedded = session.scalar(
            select(func.count()).select_from(PolicyChunk)
            .where(PolicyChunk.embedding.is_not(None), PolicyChunk.jurisdiction.is_not(None))
        )
        print(f"upserted {len(rows)} chunks; {embedded} carry embedding + metadata")
        print(f"drift audit (copies must match masters): {len(drift)} violations "
              f"{[d[0] for d in drift] if drift else '— clean'}")


if __name__ == "__main__":
    main()
