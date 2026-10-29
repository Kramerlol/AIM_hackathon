# app/validator.py
import subprocess
import tempfile
import json
import os

VALIDATOR_JAR = "validator_cli.jar"  # adjust path if needed

def validate_resource(resource: dict) -> tuple:
    """
    Run HL7 FHIR validator on a single resource dict.
    Returns (is_valid, output_text)
    """
    # Write resource to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(resource, f)
        temp_path = f.name

    try:
        # Run validator
        result = subprocess.run(
            ["java", "-jar", VALIDATOR_JAR, temp_path, "-version", "4.0"],
            capture_output=True,
            text=True
        )
        # Check for "error" or "Error" in stdout/stderr
        output = result.stdout + result.stderr
        # The validator prints "Success: 0 errors, X warnings" on success.
        # If any errors, "error" appears in output.
        if "error" in output.lower() or "errors:" in output.lower() and "0 errors" not in output.lower():
            return False, output
        return True, output
    finally:
        os.unlink(temp_path)

def validate_resources(resources: list) -> tuple:
    """
    Validate a list of resources. Returns (all_valid, results_dict)
    """
    results = {}
    for i, res in enumerate(resources):
        is_valid, output = validate_resource(res)
        results[f"resource_{i}"] = {"valid": is_valid, "output": output}
        if not is_valid:
            return False, results
    return True, results
