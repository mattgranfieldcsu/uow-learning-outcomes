"""
db/tagger.py

Uses Claude to classify each learning outcome by:
  - category: knowledge | skill | application | value | other
  - bloom_level: remember | understand | apply | analyse | evaluate | create

Run after scraping:
    python -m db.tagger

Requires ANTHROPIC_API_KEY in your environment.
"""

import sqlite3
import json
import os
import time
from pathlib import Path

import anthropic

DB_PATH = Path("data/outcomes.db")

BLOOM_VERBS = {
    "remember":    ["define", "list", "recall", "identify", "name", "recognise", "state"],
    "understand":  ["explain", "describe", "summarise", "interpret", "classify", "compare"],
    "apply":       ["use", "implement", "demonstrate", "calculate", "solve", "execute"],
    "analyse":     ["analyse", "differentiate", "examine", "distinguish", "investigate", "break down"],
    "evaluate":    ["evaluate", "critique", "justify", "assess", "argue", "defend", "judge"],
    "create":      ["design", "develop", "construct", "produce", "formulate", "compose", "plan"],
}

SYSTEM_PROMPT = """You are an expert in curriculum design and Bloom's Taxonomy.
Given a list of learning outcomes, classify each one with:

1. category: one of
   - "knowledge"    (facts, concepts, theories)
   - "skill"        (practical ability, technique, process)
   - "application"  (applying knowledge in professional/real contexts)
   - "value"        (ethical, attitudinal, or dispositional outcomes)
   - "other"

2. bloom_level: one of
   remember | understand | apply | analyse | evaluate | create
   (choose the HIGHEST level implied by the outcome's verb)

Return ONLY a JSON array, one object per outcome, in the same order:
[
  {"category": "skill", "bloom_level": "apply"},
  ...
]
No explanation, no markdown fences."""


def tag_batch(outcomes: list[str], client: anthropic.Anthropic) -> list[dict]:
    """Send up to 20 outcomes to Claude and return classifications."""
    numbered = "\n".join(f"{i+1}. {o}" for i, o in enumerate(outcomes))
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": numbered}],
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)


def run(batch_size: int = 20, dry_run: bool = False):
    """Tag all unclassified learning outcomes in the database."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Set ANTHROPIC_API_KEY environment variable")

    client = anthropic.Anthropic(api_key=api_key)
    conn   = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Fetch untagged outcomes
    rows = conn.execute(
        "SELECT id, outcome FROM learning_outcomes WHERE category IS NULL ORDER BY id"
    ).fetchall()

    print(f"Tagging {len(rows)} unclassified outcomes in batches of {batch_size}…")

    total_tagged = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        texts = [row["outcome"] for row in batch]

        try:
            tags = tag_batch(texts, client)
        except Exception as e:
            print(f"  Batch {start}–{start+len(batch)} failed: {e}")
            time.sleep(5)
            continue

        if not dry_run:
            for row, tag in zip(batch, tags):
                conn.execute(
                    "UPDATE learning_outcomes SET category=?, bloom_level=? WHERE id=?",
                    (
                        tag.get("category", "other"),
                        tag.get("bloom_level"),
                        row["id"],
                    ),
                )
            conn.commit()

        total_tagged += len(batch)
        print(f"  Tagged {total_tagged}/{len(rows)}")
        time.sleep(0.5)  # avoid rate-limiting

    conn.close()
    print("Tagging complete.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(batch_size=args.batch_size, dry_run=args.dry_run)
