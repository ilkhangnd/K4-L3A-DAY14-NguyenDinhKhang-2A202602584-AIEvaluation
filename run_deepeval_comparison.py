"""Evaluate the saved benchmark answers with DeepEval for Exercise 3.4.

This script never calls the domain assistant.  It compares the same stored
questions, actual answers, expected answers, and retrieval traces used by
``evaluate_answers.py``.  DeepEval invokes the configured judge model, so a
valid ``OPENAI_API_KEY`` in ``.env`` is required.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

# Avoid sending anonymous DeepEval telemetry; model evaluation remains enabled.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
# A retrieved trace can contain several long policy chunks.  Allow the judge
# enough time to read one before DeepEval abandons the request.
os.environ.setdefault("DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE", "180")

from deepeval import __version__ as deepeval_version
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase


ROOT = Path(__file__).resolve().parent
DEFAULT_GOLDEN = ROOT / "golden_dataset.json"
DEFAULT_ANSWERS = ROOT / "artifacts" / "actual_answers.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "deepeval_comparison.json"
METRIC_NAMES = (
    "answer_relevancy",
    "faithfulness",
    "context_recall",
    "context_precision",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_inputs(
    golden_path: Path, answers_path: Path, limit: int | None = None
) -> list[dict[str, Any]]:
    """Join saved actual-answer traces to their golden QA records by ID."""
    golden = load_json(golden_path)
    answers = load_json(answers_path)
    answer_by_id = {item["id"]: item for item in answers["answers"]}

    rows: list[dict[str, Any]] = []
    for qa in golden["qa_pairs"]:
        answer = answer_by_id.get(qa["id"])
        if answer is None:
            raise ValueError(f"Missing stored actual answer for {qa['id']}")
        if answer.get("error") is not None:
            raise ValueError(f"Stored answer {qa['id']} has error: {answer['error']}")

        retrieved_contexts = [
            chunk["text"]
            for chunk in answer.get("retrieved_contexts", [])
            if chunk.get("text")
        ]
        rows.append(
            {
                "id": qa["id"],
                "question": qa["question"],
                "expected_answer": qa["expected_answer"],
                "actual_answer": answer["actual_answer"],
                "retrieval_contexts": retrieved_contexts,
            }
        )

    return rows[:limit] if limit is not None else rows


def metric_factories(model: str) -> dict[str, Any]:
    """Return comparable DeepEval RAG metrics on the native 0–1 scale."""
    common = {"threshold": None, "model": model, "include_reason": True, "async_mode": False}
    return {
        "answer_relevancy": AnswerRelevancyMetric(**common),
        "faithfulness": FaithfulnessMetric(**common),
        "context_recall": ContextualRecallMetric(**common),
        "context_precision": ContextualPrecisionMetric(**common),
    }


def evaluate_row(row: dict[str, Any], model: str) -> dict[str, Any]:
    test_case = LLMTestCase(
        input=row["question"],
        actual_output=row["actual_answer"],
        expected_output=row["expected_answer"],
        retrieval_context=row["retrieval_contexts"],
    )

    scores: dict[str, float | None] = {}
    reasons: dict[str, str | None] = {}
    for name, metric in metric_factories(model).items():
        metric.measure(test_case)
        scores[name] = metric.score
        reasons[name] = metric.reason

    return {
        "id": row["id"],
        "retrieved_chunk_count": len(row["retrieval_contexts"]),
        "scores": scores,
        "reasons": reasons,
    }


def build_output(
    results: list[dict[str, Any]], model: str, status: str
) -> dict[str, Any]:
    averages = {
        name: mean(
            result["scores"][name]
            for result in results
            if result["scores"].get(name) is not None
        )
        for name in METRIC_NAMES
        if any(result["scores"].get(name) is not None for result in results)
    }
    return {
        "framework": "DeepEval",
        "deepeval_version": deepeval_version,
        "judge_model": model,
        "status": status,
        "case_count": len(results),
        "input_contract": {
            "generation": "No generation run; actual answers are loaded from artifacts/actual_answers.json.",
            "evaluation": "Question, stored actual answer, expected answer, and stored retrieved chunks are sent to the configured judge model.",
        },
        "averages": averages,
        "results": results,
    }


def save_output(path: Path, results: list[dict[str, Any]], model: str, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(build_output(results, model, status), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeepEval on saved OrbitTech benchmark answers."
    )
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--answers", type=Path, default=DEFAULT_ANSWERS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N dataset cases (useful for a local smoke test).",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required in .env to run DeepEval.")

    rows = build_inputs(args.golden, args.answers, args.limit)
    if not rows:
        raise ValueError("No evaluation cases were found.")

    existing_results: dict[str, dict[str, Any]] = {}
    if args.output.exists():
        previous = load_json(args.output)
        if previous.get("framework") == "DeepEval" and previous.get("judge_model") == model:
            existing_results = {item["id"]: item for item in previous.get("results", [])}

    results: list[dict[str, Any]] = [
        existing_results[row["id"]] for row in rows if row["id"] in existing_results
    ]
    for index, row in enumerate(rows, start=1):
        if row["id"] in existing_results:
            print(f"[{index}/{len(rows)}] Reusing DeepEval {row['id']}…", flush=True)
            continue
        print(f"[{index}/{len(rows)}] DeepEval {row['id']}…", flush=True)
        results.append(evaluate_row(row, model))
        save_output(args.output, results, model, "running")

    output = build_output(results, model, "complete")
    save_output(args.output, results, model, "complete")

    print("\nDeepEval averages")
    for name, score in output["averages"].items():
        print(f"  {name}: {score:.3f}")
    print(f"Saved: {args.output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
