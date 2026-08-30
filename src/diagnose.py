"""
diagnose.py
------------
Sends one troubleshooting case (symptom + topology note + show-command
output), plus optional deterministic rule-checker findings, to the
Gemini API, and gets back a structured JSON diagnosis.

SAFETY: This script NEVER connects to, configures, or changes any real
or simulated network device, and it never runs the fix it recommends.
It only prints and saves a *recommendation*. A human must review every
result (that's Stage 5 of the project) before anything is acted on.

USAGE:
    python diagnose.py <case_id>
    python diagnose.py <case_id> <path_to_network_snapshot.json>
    python diagnose.py <case_id> --dry-run
    python diagnose.py <case_id> <path_to_network_snapshot.json> --dry-run

    --dry-run builds the full prompt and prints it WITHOUT calling the
    API or spending any quota. Use this first to sanity-check everything
    is wired up correctly before you spend real API calls.
"""

import os
import sys
import csv
import json
from pathlib import Path

from dotenv import load_dotenv

# rule_checker.py lives in this same folder (src/)
from rule_checker import load_network_data, run_all_checks


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_CSV = PROJECT_ROOT / "data" / "cases.csv"
PROMPT_FILE = PROJECT_ROOT / "prompts" / "diagnose_prompt.md"
RESULTS_CSV = PROJECT_ROOT / "results" / "ai_results.csv"

MODEL_NAME = "gemini-3.6-flash"

# JSON schema the AI's response MUST follow. Gemini enforces this itself,
# so we don't have to hope the model formats its answer correctly.
DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string"},
        "osi_layer": {"type": "string"},
        "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "next_command": {"type": "string"},
        "fix_steps": {"type": "array", "items": {"type": "string"}},
        "rule_checker_agreement": {"type": "string"},
    },
    "required": [
        "root_cause", "osi_layer", "confidence",
        "evidence", "next_command", "fix_steps",
        "rule_checker_agreement",
    ],
}


# ---------------------------------------------------------------------------
# STEP 1: Load a case from cases.csv
# ---------------------------------------------------------------------------
def load_case(case_id):
    with open(CASES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["case_id"] == case_id:
                return row
    raise ValueError(f"case_id '{case_id}' not found in {CASES_CSV}")


# ---------------------------------------------------------------------------
# STEP 2: Run the Stage 3 rule checker (if a snapshot file was given)
# ---------------------------------------------------------------------------
def get_rule_checker_findings(network_json_path):
    if network_json_path and Path(network_json_path).exists():
        data = load_network_data(network_json_path)
        return run_all_checks(data)
    return []


# ---------------------------------------------------------------------------
# STEP 3: Fill the prompt template with this case's real data
# ---------------------------------------------------------------------------
def build_full_prompt(case, rule_flags):
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    if rule_flags:
        rule_summary = "\n".join(
            f"- [{flag['severity']}] {flag['rule']}: {flag['message']}"
            for flag in rule_flags
        )
    else:
        rule_summary = ("No structured network snapshot was supplied for "
                         "this case, so the deterministic rule checker did "
                         "not run.")

    filled = (
        template
        .replace("<<SYMPTOM>>", case["symptom"])
        .replace("<<TOPOLOGY_NOTE>>", case["topology_note"])
        .replace("<<SHOW_OUTPUT>>", case["show_command_output"])
        .replace("<<RULE_CHECKER_FINDINGS>>", rule_summary)
    )
    return filled


# ---------------------------------------------------------------------------
# STEP 4: Call the Gemini API
# ---------------------------------------------------------------------------
def get_client():
    """Load the API key from .env and build the Gemini client.
    Only called when we're actually making a real API call (not --dry-run)."""
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_goes_here":
        print("ERROR: GEMINI_API_KEY is missing or still set to the "
              "placeholder value. Open the .env file in the project root "
              "and paste in your real Gemini API key.")
        sys.exit(1)

    from google import genai
    return genai.Client(api_key=api_key)


def call_gemini(client, full_prompt):
    from google.genai import types
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=DIAGNOSIS_SCHEMA,
        ),
    )
    return json.loads(response.text)


# ---------------------------------------------------------------------------
# STEP 5: Save the diagnosis to results/ai_results.csv
# ---------------------------------------------------------------------------
def save_result(case_id, diagnosis):
    RESULTS_CSV.parent.mkdir(exist_ok=True)
    file_exists = RESULTS_CSV.exists()
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "case_id", "root_cause", "osi_layer", "confidence",
            "evidence", "next_command", "fix_steps", "rule_checker_agreement"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "case_id": case_id,
            "root_cause": diagnosis["root_cause"],
            "osi_layer": diagnosis["osi_layer"],
            "confidence": diagnosis["confidence"],
            "evidence": " | ".join(diagnosis["evidence"]),
            "next_command": diagnosis["next_command"],
            "fix_steps": " | ".join(diagnosis["fix_steps"]),
            "rule_checker_agreement": diagnosis["rule_checker_agreement"],
        })


# ---------------------------------------------------------------------------
# STEP 6: Command-line entry point
# ---------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv

    if len(args) < 1:
        print("Usage: python diagnose.py <case_id> [network_snapshot.json] [--dry-run]")
        sys.exit(1)

    case_id = args[0]
    network_json_path = args[1] if len(args) > 1 else None

    case = load_case(case_id)
    rule_flags = get_rule_checker_findings(network_json_path)
    full_prompt = build_full_prompt(case, rule_flags)

    if dry_run:
        print("=== DRY RUN: prompt that WOULD be sent to Gemini ===\n")
        print(full_prompt)
        print("\n(No API call was made. Remove --dry-run to actually call Gemini.)")
        return

    client = get_client()
    print(f"\nSending case {case_id} to Gemini ({MODEL_NAME})...")
    diagnosis = call_gemini(client, full_prompt)

    print(f"\n=== AI Diagnosis for {case_id} ===")
    print(json.dumps(diagnosis, indent=2))
    print("\nREMINDER: This is a recommendation only. A human reviewer must "
          "accept, edit, or reject this before any fix is applied.")

    save_result(case_id, diagnosis)
    print(f"\nSaved to {RESULTS_CSV}")


if __name__ == "__main__":
    main()
