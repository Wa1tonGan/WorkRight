"""Inject a new policy document into the knowledge base — one command.

    uv run python -m backend.ingest_policy knowledge/company/my_policy.md \
        --title "Work From Home Equipment Policy" \
        --version 1.0 --effective-from 2026-10-01

What it does (the whole pipeline, re-runnable):
  1. reads the markdown file
  2. chunks it on its own top-level headings (generic; no per-document code)
  3. derives metadata: chunk ids <PREFIX>-001..., topic/subtopic/section from
     the headings, jurisdiction defaults to the V1 scope
  4. upserts ONE row in policy_documents (master of record)
  5. embeds each chunk with BGE-M3 and upserts policy_chunks by chunk_id
     — existing chunks of OTHER documents are untouched; re-running this
     command on an edited file updates only its own chunks

Chunk ids default to the title's initials (max 5 chars) — override with
--prefix. Nothing is hardcoded per document: this is the general door.
"""

import argparse
import re
from datetime import date
from pathlib import Path

from ollama import embed
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .database import engine
from .models import PolicyChunk, PolicyDocument

EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024
DEFAULT_JURISDICTION = ["peninsular_malaysia", "labuan"]

HEADING = re.compile(r"^# (.+?)\s*$")
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(.*)$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def chunk_markdown(text: str) -> list[dict]:
    """Split on top-level '# ' headings; fall back to paragraph groups."""
    lines = text.splitlines()
    chunks: list[dict] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        content = "\n".join(body).strip()
        if not content:
            return
        number = None
        title = heading
        if heading:
            m = NUMBERED.match(heading)
            if m:
                number, title = m.group(1), m.group(2)
        chunks.append({
            "heading": heading or "Overview",
            "number": number,
            "topic": slug(title) if title else "overview",
            "body": (f"# {heading}\n" if heading else "") + content,
        })

    for line in lines:
        m = HEADING.match(line)
        if m:
            flush()
            heading, body = m.group(1), []
            continue
        body.append(line)
    flush()

    if len(chunks) <= 1 and not any(HEADING.match(l) for l in lines):
        # no headings at all: group paragraphs into ~700-char chunks
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        grouped, buf, size = [], [], 0
        for p in paragraphs:
            if size + len(p) > 700 and buf:
                grouped.append("\n\n".join(buf)); buf, size = [], 0
            buf.append(p); size += len(p)
        if buf:
            grouped.append("\n\n".join(buf))
        chunks = [{"heading": "Overview", "number": None,
                   "topic": "overview", "body": g} for g in grouped]
    return chunks


def derive_prefix(title: str) -> str:
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z0-9]+", title))
    return (initials[:5] or "POL").upper()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="markdown file, e.g. knowledge/company/x.md")
    ap.add_argument("--title", required=True)
    ap.add_argument("--version", default="1.0")
    ap.add_argument("--effective-from", default=None,
                    help="ISO date, default: today")
    ap.add_argument("--effective-to", default=None)
    ap.add_argument("--authority", default="WorkRight Labs Sdn. Bhd.")
    ap.add_argument("--source-type", default="company_policy",
                    choices=["law", "official_guidance", "company_policy"])
    ap.add_argument("--source-url", default=None)
    ap.add_argument("--prefix", default=None,
                    help="chunk-id prefix, default: title initials")
    ap.add_argument("--topic", default=None,
                    help="document-level topic; default: derived per heading")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    text = path.read_text(encoding="utf-8")
    chunks = chunk_markdown(text)
    if not chunks:
        raise SystemExit("no content found to ingest")

    prefix = (args.prefix or derive_prefix(args.title)).upper()
    effective_from = date.fromisoformat(args.effective_from) if args.effective_from else date.today()
    effective_to = date.fromisoformat(args.effective_to) if args.effective_to else None

    with Session(engine) as session:
        doc_stmt = (
            pg_insert(PolicyDocument)
            .values(
                title=args.title,
                source_type=args.source_type,
                version=args.version,
                authority=args.authority,
                effective_from=effective_from,
                effective_to=effective_to,
                source_url=args.source_url,
                local_path=str(path),
            )
            .on_conflict_do_update(
                index_elements=["local_path"],
                set_={"title": args.title, "source_type": args.source_type,
                      "version": args.version, "authority": args.authority,
                      "effective_from": effective_from,
                      "effective_to": effective_to,
                      "source_url": args.source_url},
            )
            .returning(PolicyDocument.id)
        )
        doc_id = session.execute(doc_stmt).scalar_one()
        session.commit()

        rows = []
        for i, c in enumerate(chunks, start=1):
            rows.append({
                "chunk_id": f"{prefix}-{i:03d}",
                "document_id": doc_id,
                "source_type": args.source_type,
                "topic": args.topic or c["topic"],
                "subtopic": c["topic"],
                "section": c["number"],
                "jurisdiction": DEFAULT_JURISDICTION,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "version": args.version,
                "authority": args.authority,
                "source_url": args.source_url,
                "text": c["body"],
            })

        vectors = embed(model=EMBEDDING_MODEL,
                        input=[r["text"] for r in rows],
                        keep_alive="30m")["embeddings"]
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

        total = session.scalar(select(func.count()).select_from(PolicyChunk))
        print(f"ingested {len(rows)} chunks from {path}")
        print(f"  document: {args.title} (v{args.version}, "
              f"effective {effective_from}, authority: {args.authority})")
        for r in rows:
            print(f"  {r['chunk_id']}  topic={r['topic']:28} section={r['section']}")
        print(f"knowledge base now holds {total} chunks — search finds these immediately")


if __name__ == "__main__":
    main()
