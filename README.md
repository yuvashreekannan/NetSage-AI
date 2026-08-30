# NetSage AI

AI-assisted troubleshooting helper for Cisco Packet Tracer network labs, with mandatory human review before any fix is accepted.

## Project Structure
- `data/` — troubleshooting case dataset (cases.csv)
- `prompts/` — AI prompt templates
- `src/` — Python scripts (AI diagnosis, rule checker, pipeline)
- `results/` — AI output, rule-checker flags, human review log
- `dashboard/` — Streamlit dashboard app
- `docs/` — Responsible AI log

## Setup
1. Create virtual environment: `python -m venv venv`
2. Activate it: `venv\Scripts\Activate.ps1` (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Add your Anthropic API key to `.env`

## Status
Stage 1: Project skeleton — in progress