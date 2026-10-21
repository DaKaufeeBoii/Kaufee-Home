"""Write a concise pytest report to GitHub Actions' job summary."""

from __future__ import annotations

import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def main(report_path: Path) -> int:
    summary_path_value = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path_value:
        print("GITHUB_STEP_SUMMARY is not set; skipping workflow test summary.")
        return 0
    summary_path = Path(summary_path_value)

    lines = ["## Pytest results", ""]
    if not report_path.is_file():
        lines.append("No JUnit report was created; see the test step output for the failure.")
    else:
        root = ET.parse(report_path).getroot()
        cases = root.findall(".//testcase")
        failures = [
            (case, child)
            for case in cases
            for child in list(case)
            if child.tag in {"failure", "error"}
        ]
        errors = sum(1 for case in cases for child in list(case) if child.tag == "error")
        skipped = sum(1 for case in cases for child in list(case) if child.tag == "skipped")
        lines.append(
            f"Collected {len(cases)} tests: {len(failures)} failure(s), "
            f"{errors} error(s), {skipped} skipped."
        )
        for case, failure in failures:
            name = f"{case.get('classname', '')}::{case.get('name', 'unknown')}"
            details = (failure.get("message") or failure.text or "No failure details provided.").strip()
            details = details[:2000].replace("```", "'''")
            lines.extend(["", f"### `{name}`", "", "```text", details, "```"])

    with summary_path.open("a", encoding="utf-8") as summary_file:
        summary_file.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pytest__/junit.xml")))
