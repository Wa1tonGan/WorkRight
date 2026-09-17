"""Vector search demo — now a thin CLI over the real search tool.

Run:  uv run python -m backend.search_demo
"""

from .tools import search_chunks


def search(question: str, jurisdiction: str | None = None,
           as_of=None, k: int = 4) -> list:
    rows = search_chunks(question, jurisdiction=jurisdiction, k=k, as_of=as_of)
    return [
        (r["chunk_id"], r["topic"], r["subtopic"], r["section"],
         r["source_type"], r["authority"], r["similarity"], r["text"][:110])
        for r in rows
    ]


def show(title: str, rows: list) -> None:
    print(f"\n── {title}")
    if not rows:
        print("   (no applicable chunks → ESCALATE TO HR — the correct answer)")
        return
    for cid, topic, subtopic, section, stype, authority, sim, preview in rows:
        cite = f"{cid}" + (f" §{section}" if section else "")
        print(f"   {sim:.3f}  {cite:12} [{stype}] {authority}")


def main() -> None:
    q = "how many days of annual leave am I entitled to?"

    show("DANIAL — peninsular_malaysia asks the SAME question",
         search(q, jurisdiction="peninsular_malaysia"))
    show("JELIN — sabah asks the SAME question",
         search(q, jurisdiction="sabah"))
    show("no-filter (old behaviour, for comparison)",
         search(q, jurisdiction=None, k=2))


if __name__ == "__main__":
    main()
