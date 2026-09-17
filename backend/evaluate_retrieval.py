"""Evaluate WorkRight's vector retrieval without an answering LLM.

This script asks BGE-M3 to embed each question, uses pgvector to retrieve the
top-k policy chunks, and checks whether the manually expected chunks appear.

Run from the repository root:
    uv run python -m backend.evaluate_retrieval
    uv run python -m backend.evaluate_retrieval --top-k 5

Exit codes:
    0  every scored case found all required chunks
    1  at least one scored case missed required evidence
    2  Ollama or PostgreSQL could not be reached
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from .search_demo import search


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    question: str
    required_chunks: tuple[str, ...]
    purpose: str

    @property
    def scored(self) -> bool:
        """Cases without expected chunks are qualitative observations."""

        return bool(self.required_chunks)


CASES = (
    RetrievalCase(
        case_id="RAG-001",
        question="How many statutory annual leave days apply after 7 years of service?",
        required_chunks=("LAW-003",),
        purpose="Direct English statutory-entitlement lookup",
    ),
    RetrievalCase(
        case_id="RAG-002",
        question="How many annual leave days does WorkRight Labs provide?",
        required_chunks=("HB-004",),
        purpose="Separate company policy from statutory law",
    ),
    RetrievalCase(
        case_id="RAG-003",
        question="Can I carry unused annual leave into next year?",
        required_chunks=("HB-004",),
        purpose="Retrieve a condition expressed with different wording",
    ),
    RetrievalCase(
        case_id="RAG-004",
        question="Berapa hari cuti sakit selepas 3 tahun bekerja?",
        required_chunks=("LAW-005",),
        purpose="Malay-language sick-leave retrieval",
    ),
    RetrievalCase(
        case_id="RAG-005",
        question="How quickly must I notify my employer when I take sick leave?",
        required_chunks=("LAW-006",),
        purpose="Retrieve a statutory notification condition",
    ),
    RetrievalCase(
        case_id="RAG-006",
        question="I want to work from home two days each week. How do I apply?",
        required_chunks=("LAW-007", "LAW-008", "HB-007"),
        purpose="Retrieve all law and company evidence needed for an FWA answer",
    ),
    RetrievalCase(
        case_id="RAG-007",
        question="Can WorkRight automatically process my leave if I work in Sabah?",
        required_chunks=("LAW-001", "HB-002"),
        purpose="Retrieve both legal and company scope restrictions",
    ),
    RetrievalCase(
        case_id="RAG-008",
        question="How does WorkRight annual leave compare with the statutory minimum?",
        required_chunks=("LAW-003", "HB-004"),
        purpose="Retrieve both sources for a comparison",
    ),
    RetrievalCase(
        case_id="RAG-OBS-001",
        question="What is WorkRight's childcare allowance policy?",
        required_chunks=(),
        purpose="Observe what vector search returns when the corpus lacks an answer",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="Number of chunks to retrieve for each question (default: 4)",
    )
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")
    return args


def main() -> int:
    args = parse_args()
    passed_cases = 0
    scored_cases = 0
    expected_chunks = 0
    found_chunks = 0
    reciprocal_rank_total = 0.0

    print(f"WorkRight retrieval evaluation (top_k={args.top_k})")
    print("The similarity value ranks results; it is not a confidence percentage.\n")

    for case in CASES:
        try:
            rows = search(case.question, k=args.top_k)
        except Exception as exc:
            print(
                f"ERROR: retrieval could not run ({type(exc).__name__}). "
                "Check that Ollama, BGE-M3, PostgreSQL, and pgvector are available."
            )
            return 2

        ranked_ids = [row[0] for row in rows]
        ranks = {chunk_id: rank for rank, chunk_id in enumerate(ranked_ids, start=1)}

        if case.scored:
            scored_cases += 1
            expected_chunks += len(case.required_chunks)
            missing = [chunk for chunk in case.required_chunks if chunk not in ranks]
            found = [chunk for chunk in case.required_chunks if chunk in ranks]
            found_chunks += len(found)
            reciprocal_rank_total += sum(1 / ranks[chunk] for chunk in found)
            passed = not missing
            if passed:
                passed_cases += 1
            status = "PASS" if passed else "FAIL"
        else:
            missing = []
            status = "OBSERVE"

        print(f"[{status}] {case.case_id}: {case.question}")
        print(f"  Purpose: {case.purpose}")
        if case.scored:
            print(f"  Required: {', '.join(case.required_chunks)}")
            if missing:
                print(f"  Missing:  {', '.join(missing)}")

        for rank, row in enumerate(rows, start=1):
            # search() rows: (chunk_id, topic, subtopic, section,
            #                 source_type, authority, similarity, preview)
            chunk_no, topic, similarity = row[0], row[1], row[6]
            marker = "*" if chunk_no in case.required_chunks else " "
            print(
                f"  {marker} {rank}. {chunk_no:8} "
                f"similarity={similarity:.3f} topic={topic}"
            )
        print()

    case_recall = passed_cases / scored_cases if scored_cases else 0.0
    evidence_recall = found_chunks / expected_chunks if expected_chunks else 0.0
    mean_reciprocal_rank = (
        reciprocal_rank_total / expected_chunks if expected_chunks else 0.0
    )

    print("Summary")
    print(f"  Cases passing all requirements: {passed_cases}/{scored_cases} ({case_recall:.1%})")
    print(f"  Required chunks retrieved:      {found_chunks}/{expected_chunks} ({evidence_recall:.1%})")
    print(f"  Mean reciprocal rank:           {mean_reciprocal_rank:.3f}")
    print("  Observation cases are shown but are not included in the score.")

    return 0 if passed_cases == scored_cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
