"""Import a local matcher dataset into Langfuse, including a fresh instance."""

import argparse
import json
from pathlib import Path

from langfuse import Langfuse

from config.settings import settings
from domain.models import JobPosting


def seed_dataset(client, data: dict) -> int:
    items = data["items"]
    for item in items:
        JobPosting.model_validate(item["input"]["job"])
        if type(item["expected_output"]["worth_considering"]) is not bool:
            raise ValueError("Each example needs an expected yes/no decision")
    client.create_dataset(name=data["name"])
    for item in items:
        # Stable IDs update existing items when this import is repeated.
        client.create_dataset_item(dataset_name=data["name"], **item)
    return len(items)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("evals/job-matcher-baseline.json"))
    args = parser.parse_args()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        parser.error("Both Langfuse project keys are required")
    data = json.loads(args.file.read_text())
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )
    try:
        count = seed_dataset(client, data)
        print(f"Imported {count} examples into {data['name']}")
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
