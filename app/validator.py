# app/validator.py
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

VALIDATOR_JAR = os.environ.get("VALIDATOR_JAR", str(Path(__file__).resolve().parent.parent / "validator_cli.jar"))
TIMEOUT_SECONDS = int(os.environ.get("VALIDATOR_TIMEOUT", "180"))


def validator_available() -> bool:
    return Path(VALIDATOR_JAR).is_file()


def validate_resources(resources: list) -> tuple:
    """
    Run the HL7 FHIR validator (R4) once over all resources.
    Returns (all_valid, results) where results = {"errors": int, "output": text}.
    Fails closed: if the validator cannot run, the resources are NOT valid.
    One Java start for all files keeps the answer fast; a start per resource takes many seconds each.
    """
    if not validator_available():
        return False, {"errors": None, "output": f"validator jar not found at {VALIDATOR_JAR}"}
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, res in enumerate(resources):
            path = Path(tmp) / f"{i:02d}-{res['resourceType']}.json"
            path.write_text(json.dumps(res))
            paths.append(str(path))
        try:
            result = subprocess.run(["java", "-jar", VALIDATOR_JAR, *paths, "-version", "4.0"],
                                    capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, {"errors": None, "output": f"validator could not run: {exc}"}
    output = result.stdout + result.stderr
    # The validator prints e.g. "Success: 0 errors, 1 warnings, 0 notes" or "*FAILURE*: 2 errors, ...".
    counts = re.findall(r"(\d+)\s+errors?", output)
    errors = sum(int(c) for c in counts) if counts else None
    return (result.returncode == 0 and errors == 0), {"errors": errors, "output": output}
