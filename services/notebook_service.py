"""
Notebook parsing and submission utilities without external dependencies.
"""

from __future__ import annotations

import json
from typing import Any, List, Dict

from services import db_service
from services.assessment_service import submit_assessment


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


def parse_jupyter_notebook(file_bytes: bytes) -> Dict[str, Any]:
    """Parse a Jupyter notebook (JSON) from raw bytes.
    Returns a dict with combined code, extracted outputs, and metadata.
    """
    notebook = json.loads(file_bytes.decode("utf-8"))
    code_parts: List[str] = []
    all_outputs: List[str] = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") == "code":
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            code_parts.append(str(source))
            all_outputs.extend(_extract_outputs(cell))
    combined_code = "\n\n".join(code_parts)
    return {
        "code": combined_code,
        "outputs": all_outputs,
        "metadata": notebook.get("metadata", {}),
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

    db_service.save_submission_row(
        assessment_id=assessment_id,
        user_id=user_id,
        question_id="notebook",
        user_answer=parsed["code"],
        score="0",
        feedback="Notebook received.",
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
        "score": 0,
        "feedback": "Notebook submitted successfully.",
    }

