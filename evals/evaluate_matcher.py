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


def build_evaluation_graph():
    def match_one(state: dict) -> dict:
        data = state["input"]
        result = matcher.run(
            [JobPosting.model_validate(data["job"])],
            data["profile_md"],
            data["criteria_md"],
            data.get("discard_keywords", ""),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="job-matcher-baseline")
    parser.add_argument("--run", action="store_true", help="Run the matcher and publish results")
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

        def score_run(*, item_results, **kwargs):
            correct = sum(
                score_decision(
                    output=result.output, expected_output=result.item.expected_output
                ).value
                for result in item_results
            )
            return Evaluation(name="decision_accuracy", value=correct / len(dataset.items))

        result = dataset.run_experiment(
            name="Matcher baseline",
            task=make_task(build_evaluation_graph(), settings.langfuse_public_key),
            evaluators=[score_decision],
            run_evaluators=[score_run],
            max_concurrency=1,
        )
        print(result.format())
    finally:
        client.shutdown()


if __name__ == "__main__":
    main()
