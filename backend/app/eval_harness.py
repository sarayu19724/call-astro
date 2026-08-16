"""
Hallucination / groundedness evaluation harness (idea #6 from the RAG
review). Runs a fixed battery of test questions against a real session with
a real Kundli, and reports:

  - hallucination rate         (claim_issues_remaining > 0, after retry)
  - initial-issue rate         (claim_issues_initial > 0, before retry)
  - retry-fix rate             (how often the retry actually cleared issues)
  - retrieval groundedness     (% of astrology questions that got >=1 RAG source)
  - per-intent-category breakdown

This does NOT call an LLM twice for comparison (that's idea #7, a separate
follow-on) — it measures the pipeline you have today, deterministically,
so you have a number to show instead of "it caught a hallucination once."

Usage:
    python -m backend.app.eval_harness
"""
import sys
import json
from pathlib import Path
from collections import defaultdict


from app.memory.database import db
from app.services.chat_service import chat_service
from app.utils.logger import logger

# A fixed test profile so every run is comparable (same chart = same ground truth).
EVAL_SESSION_ID = "eval_harness_fixed_session"
EVAL_PROFILE = {
    "name": "EvalUser",
    "dob": "14-02-1996",
    "birth_time": "08:15",
    "birth_place": "Lucknow",
    "language": "English",
}

# Tagged with the intent category they should exercise, mirroring
# intent_service.INTENT_PATTERNS so results can be broken down the same way.
TEST_QUESTIONS = [
    ("simple_fact", "What is my Ascendant sign?"),
    ("simple_fact", "What is my Moon sign?"),
    ("timing", "When will I get married?"),
    ("timing", "When will my career improve in the next 2 years?"),
    ("explanation", "Why is my career slow right now?"),
    ("explanation", "Why do I feel financially stuck?"),
    ("strength_check", "Is my 7th house strong for marriage?"),
    ("strength_check", "How strong is my Jupiter?"),
    ("remedy", "Which gemstone should I wear for career growth?"),
    ("remedy", "What remedy helps my health?"),
    ("general", "Tell me about my Kundli overall."),
    ("general", "What does Rahu in my chart mean?"),
    ("general", "How is my financial future looking?"),
    ("general", "What do you see for my health this year?"),
]


def setup_eval_session():
    session = db.get_or_create_session(EVAL_SESSION_ID)
    db.update_session(EVAL_SESSION_ID, EVAL_PROFILE)
    db.clear_history(EVAL_SESSION_ID)
    logger.info(f"Eval session ready: {EVAL_SESSION_ID}")
    return db.get_or_create_session(EVAL_SESSION_ID)


def run_eval():
    setup_eval_session()

    results = []
    for category, question in TEST_QUESTIONS:
        logger.info(f"[EVAL] ({category}) {question}")
        try:
            result = chat_service.process_chat_message(EVAL_SESSION_ID, question)
        except Exception as e:
            logger.error(f"[EVAL] request failed for '{question}': {e}")
            continue

        row = {
            "category": category,
            "question": question,
            "response": result.get("message", ""),
            "topic": result.get("topic"),
            "rag_sources": result.get("rag_sources", []),
            "claim_issues_initial": result.get("claim_issues_initial", 0),
            "claim_issues_remaining": result.get("claim_issues_remaining", 0),
            "evidence_confidence": result.get("evidence_confidence"),
            "evidence_verdict": result.get("evidence_verdict"),
        }
        results.append(row)

    return results


def summarize(results):
    total = len(results)
    if total == 0:
        print("No results to summarize.")
        return

    had_initial_issue = sum(1 for r in results if r["claim_issues_initial"] > 0)
    still_hallucinating = sum(1 for r in results if r["claim_issues_remaining"] > 0)
    fixed_by_retry = sum(
        1 for r in results
        if r["claim_issues_initial"] > 0 and r["claim_issues_remaining"] == 0
    )
    had_rag_source = sum(1 for r in results if r["rag_sources"])

    by_category = defaultdict(lambda: {"n": 0, "hallucinated": 0, "grounded": 0})
    for r in results:
        c = by_category[r["category"]]
        c["n"] += 1
        if r["claim_issues_remaining"] > 0:
            c["hallucinated"] += 1
        if r["rag_sources"]:
            c["grounded"] += 1

    print("\n" + "=" * 60)
    print(" HALLUCINATION / GROUNDEDNESS EVAL REPORT")
    print("=" * 60)
    print(f"Total questions:                 {total}")
    print(f"Initial claim issues detected:   {had_initial_issue} ({had_initial_issue/total:.0%})")
    print(f"Fixed automatically on retry:    {fixed_by_retry} ({fixed_by_retry/total:.0%})")
    print(f"Still unsupported after retry:   {still_hallucinating} ({still_hallucinating/total:.0%})  <- hallucination rate")
    print(f"Responses with >=1 RAG source:   {had_rag_source} ({had_rag_source/total:.0%})  <- groundedness rate")

    print("\nBy intent category:")
    print(f"{'category':<16}{'n':<4}{'hallucinated':<14}{'grounded':<10}")
    for cat, stats in by_category.items():
        print(f"{cat:<16}{stats['n']:<4}{stats['hallucinated']:<14}{stats['grounded']:<10}")

    print("\nFlagged responses (still unsupported after retry):")
    for r in results:
        if r["claim_issues_remaining"] > 0:
            print(f"  - [{r['category']}] \"{r['question']}\" -> {r['claim_issues_remaining']} issue(s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    results = run_eval()
    summarize(results)

    out_path = Path(__file__).resolve().parent / "eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Full results written to {out_path}")