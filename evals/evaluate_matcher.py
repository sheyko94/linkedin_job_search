"""Run a minimal yes/no matcher evaluation against a reviewed Langfuse dataset."""

import argparse

from langfuse import Evaluation, Langfuse
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph

from agents import matcher
from config.settings import settings
from domain.models import JobPosting


def validate_items(items: list) -> None:
    if not items:
        raise ValueError("The dataset has no active examples")
    for item in items:
        JobPosting.model_validate(item.input["job"])
        if not item.input["profile_md"].strip() or not item.input["criteria_md"].strip():
            raise ValueError(f"Dataset item {item.id} needs a profile and criteria")
        if type(item.expected_output.get("worth_considering")) is not bool:
            raise ValueError(f"Dataset item {item.id} needs an expected yes/no decision")
        if not item.metadata or item.metadata.get("reviewed") is not True:
            raise ValueError(f"Dataset item {item.id} needs human label review")


def build_evaluation_graph(prompt_version: int | None = None):
    def match_one(state: dict) -> dict:
        data = state["input"]
        result = matcher.run(
            [JobPosting.model_validate(data["job"])],
            data["profile_md"],
            data["criteria_md"],
            data.get("discard_keywords", ""),
            prompt_version=prompt_version,
            allow_prompt_fallback=False,
        )[0]
        return {"result": result}

    graph = StateGraph(dict)
    graph.add_node("match", match_one)
    graph.add_edge(START, "match")
    graph.add_edge("match", END)
    return graph.compile()


def make_task(graph, public_key: str):
    def task(*, item, **kwargs) -> dict:
        try:
            result = graph.invoke(
                {"input": item.input},
                config={"callbacks": [CallbackHandler(public_key=public_key)]},
            )["result"]
            return {
                "worth_considering": result.recommendation in ("Strong Match", "Good Match"),
                **result.model_dump(exclude={"job"}),
            }
        except Exception as exc:
            return {"error": type(exc).__name__}

    return task


def score_decision(*, output, expected_output, **kwargs) -> Evaluation:
    correct = output.get("worth_considering") is expected_output["worth_considering"]
    return Evaluation(name="decision_correct", value=int(correct), data_type="NUMERIC")


def score_run(*, item_results, **kwargs) -> list[Evaluation]:
    tp = fp = fn = tn = errors = 0
    for result in item_results:
        output = result.output
        if (
            not isinstance(output, dict)
            or "error" in output
            or type(output.get("worth_considering")) is not bool
        ):
            errors += 1
            continue
        expected = result.item.expected_output["worth_considering"]
        predicted = output["worth_considering"]
        tp += expected and predicted
        fp += not expected and predicted
        fn += expected and not predicted
        tn += not expected and not predicted

    total = len(item_results)
    # Classification metrics exclude execution errors; undefined ratios score zero.
    metrics = {
        "decision_accuracy": (tp + tn) / total if total else 0,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
        "execution_error_rate": errors / total if total else 0,
    }
    return [
        Evaluation(name=name, value=value, data_type="NUMERIC") for name, value in metrics.items()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="job-matcher-baseline")
    parser.add_argument("--run", action="store_true", help="Run the matcher and publish results")
    parser.add_argument(
        "--prompt-version", type=int, help="Evaluate an exact Langfuse prompt version"
    )
    args = parser.parse_args()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        parser.error("Both Langfuse project keys are required")
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )
    try:
        dataset = client.get_dataset(args.dataset)
        dataset.items = [item for item in dataset.items if item.status == "ACTIVE"]
        validate_items(dataset.items)
        if not args.run:
            print(f"Validated {len(dataset.items)} reviewed examples; no model calls made.")
            return

        prompt = matcher.get_prompt(
            client=client, version=args.prompt_version, allow_fallback=False
        )
        result = dataset.run_experiment(
            name="Matcher baseline",
            task=make_task(
                build_evaluation_graph(prompt.metadata["prompt_version"]),
                settings.langfuse_public_key,
            ),
            evaluators=[score_decision],
            run_evaluators=[score_run],
            max_concurrency=1,
            metadata={k: v for k, v in prompt.metadata.items() if k != "langfuse_prompt"},
        )
        print(result.format())
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
