"""Publish every JSON chat prompt in the prompts directory to Langfuse."""

import argparse
import json

from langfuse import Langfuse

from config.settings import settings
from prompts.prompt import PROMPT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label", help="Assign a release label, e.g. production; omitted by default"
    )
    args = parser.parse_args()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        parser.error("Both Langfuse project keys are required")
    files = sorted(PROMPT_DIR.glob("*.json"))
    if not files:
        parser.error("No JSON prompts found")
    prompts = [json.loads(path.read_text()) for path in files]
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )
    try:
        for data in prompts:
            prompt = client.create_prompt(**data, labels=[args.label] if args.label else [])
            print(f"Published {prompt.name} version {prompt.version}; labels: {prompt.labels}")
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
