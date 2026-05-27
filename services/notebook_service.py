"""
Notebook parsing and submission utilities without external dependencies.
"""

from __future__ import annotations

import json
from typing import Any, List, Dict

from services import db_service
from services.assessment_service import submit_assessment
from services.llm_service import evaluate_answers


def _extract_outputs(cell: Dict[str, Any]) -> List[str]:
    """Extract text-like outputs from a Jupyter code cell.
    Supports stream, execute_result, display_data, and error outputs.
    """
    outputs: List[str] = []
    for out in cell.get("outputs", []):
        out_type = out.get("output_type")
        if out_type == "stream":
            text = out.get("text")
            if text:
                outputs.append(str(text))
        elif out_type in {"execute_result", "display_data"}:
            data = out.get("data", {})
            txt = data.get("text/plain")
            if txt:
                outputs.append(str(txt))
        elif out_type == "error":
            traceback = out.get("traceback", [])
            if traceback:
                outputs.append("\n".join(traceback))
    return outputs


def _cell_source(cell: Dict[str, Any]) -> str:
    """Return cell source as a plain string regardless of list/str storage."""
    src = cell.get("source", "")
    if isinstance(src, list):
        src = "".join(src)
    return str(src)


def parse_jupyter_notebook(file_bytes: bytes) -> Dict[str, Any]:
    """Parse a Jupyter notebook (JSON) from raw bytes.

    Returns a dict with:
      - ``cells``: list of {question, code, outputs} — markdown question paired
        with the immediately following code cell.
      - ``code``: all student code combined.
      - ``outputs``: all cell outputs combined.
      - ``metadata``: notebook-level metadata.

    The template structure produced by the platform is:
      [markdown: question text] → [code: student answer] → repeat
    This parser pairs each code cell with the most recent preceding markdown cell.
    """
    notebook = json.loads(file_bytes.decode("utf-8"))
    raw_cells = notebook.get("cells", [])

    code_parts: List[str] = []
    all_outputs: List[str] = []
    paired_cells: List[Dict[str, Any]] = []

    last_markdown = ""
    for cell in raw_cells:
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            last_markdown = _cell_source(cell)
        elif cell_type == "code":
            source = _cell_source(cell)
            outputs = _extract_outputs(cell)
            # Skip blank code cells that have no associated question — these are
            # trailing/noise cells added by Jupyter (e.g. the default empty cell
            # at the bottom of a new notebook), not unanswered questions.
            if not source.strip() and not last_markdown.strip():
                continue
            code_parts.append(source)
            all_outputs.extend(outputs)
            paired_cells.append({
                "question": last_markdown,
                "code": source,
                "outputs": outputs,
            })
            last_markdown = ""  # consume so the next code cell doesn't inherit it

    return {
        "code": "\n\n".join(code_parts),
        "outputs": all_outputs,
        "metadata": notebook.get("metadata", {}),
        "cells": paired_cells,
    }


def submit_notebook_assessment(
    assessment_id: str,
    user_id: str,
    notebook_bytes: bytes,
    submitter_client_id: str | None = None,
) -> Dict[str, Any]:
    """Handle notebook submission.
    Parses notebook, stores code as a submission row.
    """
    parsed = parse_jupyter_notebook(notebook_bytes)
    try:
        raw_notebook_dict = json.loads(notebook_bytes.decode("utf-8"))
    except Exception:
        raw_notebook_dict = None

    # Grade each question/code pair: question = markdown prompt, answer = student code + outputs
    cell_scores = []
    feedback_parts = []
    for idx, cell in enumerate(parsed.get("cells", []), start=1):
        question_text = cell.get("question", "").strip()
        code = cell.get("code", "").strip()
        outputs = "\n".join(cell.get("outputs", []))

        if not code:
            cell_scores.append(0)
            feedback_parts.append(f"Q{idx}: No code submitted for this question.")
            continue

        # Build the student answer from their code; append outputs if they ran the cell
        student_answer = code
        if outputs.strip():
            student_answer = f"{code}\n\n--- Output ---\n{outputs}"

        # Fall back to using the code as the question context if no markdown was captured
        effective_question = question_text if question_text else f"(Code cell {idx})"

        try:
            eval_result = evaluate_answers(question=effective_question, user_answer=student_answer)
            score = eval_result.get("score", 0)
            fb = eval_result.get("feedback", "")
        except Exception as e:
            score = 0
            fb = f"Evaluation error for Q{idx}: {e}"
        cell_scores.append(score)
        feedback_parts.append(f"Q{idx}: {fb}")

    # Aggregate scores (average) and combine feedback
    overall_score = round(sum(cell_scores) / len(cell_scores), 2) if cell_scores else 0
    combined_feedback = "\n".join(feedback_parts) if feedback_parts else "No code cells found."

    db_service.save_submission_row(
        assessment_id=assessment_id,
        user_id=user_id,
        question_id="notebook",
        user_answer=parsed["code"],
        score=str(overall_score),
        feedback=combined_feedback,
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        submitter_client_id=submitter_client_id,
        routing_flag="jupyter",
        raw_notebook=raw_notebook_dict,
    )
    return {
        "assessment_id": assessment_id,
        "user_id": user_id,
        "code": parsed["code"],
        "outputs": parsed["outputs"],
        "metadata": parsed["metadata"],
        "score": overall_score,
        "feedback": combined_feedback,
    }

