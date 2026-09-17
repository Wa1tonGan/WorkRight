"""Structure-aware chunking of knowledge/ documents (Phase 2, exercise 2).

Why heading-based instead of fixed-size windows:
both source documents already define their own semantic boundaries (the legal
corpus prescribes chunk ids LAW-001..008; the handbook is numbered sections),
and a complete rule is a citable answer while half a table is not.

This module ONLY reads and prints. It does not embed and does not touch the
database — that is the next agreed step after we inspect these boundaries.

Run:  uv run python -m backend.chunking
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    document: str
    title: str
    topic: str
    text: str

    @property
    def n_chars(self) -> int:
        return len(self.text)

    @property
    def approx_tokens(self) -> int:
        # rough heuristic for English prose (~4 chars/token); metadata and
        # markdown inflate this a little — good enough for boundary review.
        return self.n_chars // 4


REPO = Path(__file__).resolve().parents[1]
LEGAL_PATH = REPO / "knowledge" / "law" / "workright_legal_policy_v1.md"
HANDBOOK_PATH = REPO / "knowledge" / "company" / "workright_employee_handbook_v1.md"

# ---- legal corpus: split on its own declared chunk boundaries -----------------

LEGAL_HEADER = re.compile(r"^## (LAW-\d{3}) — (.+?)\s*$")
LEGAL_TOPIC = re.compile(r"^\*\*Topic:\*\* `(.+?)`")
LEGAL_SOURCE = re.compile(r"^\*\*Source type:\*\* (.+?)\s*$")
LEGAL_AUTHORITY = re.compile(r"^\*\*Authority:\*\* (.+?)\s*$")


def chunk_legal(path: Path) -> list[Chunk]:
    lines = path.read_text(encoding="utf-8").splitlines()
    chunks: list[Chunk] = []
    current: list[str] | None = None
    meta = {"id": "", "title": "", "topic": "", "source": "", "authority": ""}

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(current).strip()
        chunks.append(
            Chunk(
                chunk_id=meta["id"],
                document="workright_legal_policy_v1.md",
                title=f'{meta["title"]} [{meta["authority"]} ]' if meta["authority"] else meta["title"],
                topic=meta["topic"],
                text=f'## {meta["id"]} — {meta["title"]}\n'
                f'Topic: {meta["topic"]} | Source: {meta["source"]} | '
                f'Authority: {meta["authority"]}\n{body}',
            )
        )

    for line in lines:
        m = LEGAL_HEADER.match(line)
        if m:
            flush()
            meta = {"id": m.group(1), "title": m.group(2), "topic": "",
                    "source": "", "authority": ""}
            current = []
            continue
        if current is None:
            continue
        # preambles before Part B / source lists end the corpus section
        if line.startswith("# Official Sources") or line.startswith("# Intended RAG"):
            flush()
            current = None
            continue
        tm = LEGAL_TOPIC.match(line)
        sm = LEGAL_SOURCE.match(line)
        am = LEGAL_AUTHORITY.match(line)
        if tm:
            meta["topic"] = tm.group(1)
            continue  # metadata belongs in the rebuilt header line, not the body
        if sm:
            meta["source"] = sm.group(1).strip("`")   # markdown backticks aren't meaning
            continue
        if am:
            meta["authority"] = am.group(1)
            continue  # metadata lines stay in the header we rebuild
        current.append(line)
    flush()
    return chunks


# ---- company handbook: split on numbered top-level sections -------------------

HB_HEADER = re.compile(r"^# (\d+)\. (.+?)\s*$")

# the handbook's own §11 groups sections for RAG; we keep section-level chunks
# (smallest citable unit) and record the group via chunk_id prefix later.
HB_SKIP = {"11"}  # chunking plan itself — meta-instruction, not company policy


def chunk_handbook(path: Path) -> list[Chunk]:
    lines = path.read_text(encoding="utf-8").splitlines()
    chunks: list[Chunk] = []
    num, title = "", ""
    current: list[str] | None = None

    def flush() -> None:
        if current is None or num in HB_SKIP:
            return
        body = "\n".join(current).strip()
        if body:
            chunks.append(
                Chunk(
                    chunk_id=f"HB-{int(num):03d}",
                    document="workright_employee_handbook_v1.md",
                    title=f"WorkRight Handbook §{num}: {title}",
                    topic=title.lower().replace(" ", "_").rstrip("."),
                    text=f"# {num}. {title}\n{body}",
                )
            )

    for line in lines:
        m = HB_HEADER.match(line)
        if m:
            flush()
            num, title = m.group(1), m.group(2)
            current = []
            continue
        if current is not None:
            current.append(line)
    flush()
    return chunks


def main() -> None:
    legal = chunk_legal(LEGAL_PATH)
    handbook = chunk_handbook(HANDBOOK_PATH)
    all_chunks = legal + handbook

    print(f"{'chunk_id':10} {'chars':>6} {'~tok':>5}  title")
    print("-" * 100)
    for c in all_chunks:
        print(f"{c.chunk_id:10} {c.n_chars:6} {c.approx_tokens:5}  {c.title[:70]}")

    total_chars = sum(c.n_chars for c in all_chunks)
    print(
        f"\n{len(legal)} legal chunks + {len(handbook)} handbook chunks "
        f"= {len(all_chunks)} total, {total_chars} chars, ~{total_chars // 4} tokens"
    )

    # boundary spot-checks a reviewer should want: the two most error-prone
    # boundaries — end of one entitlement table vs start of the next section
    print("\n=== boundary check: first / last line of every legal chunk ===")
    for c in legal:
        body = [ln for ln in c.text.splitlines() if ln.strip()]
        print(f"{c.chunk_id}: first={body[1][:60]!r}  last={body[-1][:60]!r}")


if __name__ == "__main__":
    main()
