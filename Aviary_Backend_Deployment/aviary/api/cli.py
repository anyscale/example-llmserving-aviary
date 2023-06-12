import ast
import json
from typing import Annotated, List

import typer
from rich import print as rp
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from aviary.api import sdk

app = typer.Typer()

model_type = typer.Option(
    default=..., help="The model to use. You can specify multiple models."
)
prompt_type = typer.Option(help="Prompt to query")
stats_type = typer.Option(help="Whether to print generated statistics")


@app.command(name="list_models")
def list_models(metadata: Annotated[bool, "Whether to print metadata"] = False):
    """Get a list of the available models"""
    result = sdk.models()
    if metadata:
        for model in result:
            rp(f"[bold]{model}:[/]")
            rp(sdk.metadata(model))
    else:
        print("\n".join(result))


def _print_result(result, model, print_stats):
    rp(f"[bold]{model}:[/]")
    rp(result["generated_text"])
    if print_stats:
        del result["generated_text"]
        rp("[bold]Stats:[/]")
        rp(result)


def progress_spinner():
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    )


@app.command()
def query(
    model: Annotated[List[str], model_type],
    prompt: Annotated[str, prompt_type],
    print_stats: Annotated[bool, stats_type] = False,
):
    """Query one or several models with a prompt."""
    with progress_spinner() as progress:
        for m in model:
            progress.add_task(
                description=f"Processing prompt against {m}...", total=None
            )
            result = sdk.query(m, prompt)
            _print_result(result, m, print_stats)


@app.command(name="batch_query")
def batch_query(
    model: Annotated[List[str], model_type],
    prompt: Annotated[List[str], prompt_type],
    print_stats: Annotated[bool, stats_type] = False,
):
    """Query a model with a batch of prompts."""
    with progress_spinner() as progress:
        for m in model:
            progress.add_task(
                description=f"Processing prompt against {m}...", total=None
            )
            results = sdk.batch_query(m, prompt)
            for result in results:
                _print_result(result, m, print_stats)


@app.command()
def run(model: Annotated[List[str], model_type]):
    """Start a model in Aviary.

    Args:
        *model: The model to run.
    """
    sdk.run(*model)


prompt_file_type = typer.Option(
    default=..., help="File containing prompts. A simple text file"
)
separator_type = typer.Option(help="Separator used in prompt files")
results_type = typer.Option(help="Where to save the results")


@app.command(name="multi_query")
def multi_query(
    model: Annotated[List[str], model_type],
    prompt_file: Annotated[str, prompt_file_type],
    separator: Annotated[str, separator_type] = "----",
    output_file: Annotated[str, results_type] = "aviary-output.json",
):
    """Query one or multiple models with a batch of prompts taken from a file."""

    with progress_spinner() as progress:
        progress.add_task(
            description=f"Loading your prompts from {prompt_file}.", total=None
        )
        with open(prompt_file, "r") as f:
            prompts = f.read().split(separator)
        results = {prompt: [] for prompt in prompts}

        for m in model:
            progress.add_task(
                description=f"Processing all prompts against model: {model}.",
                total=None,
            )
            query_results = sdk.batch_query(m, prompts)
            for i, prompt in enumerate(prompts):
                result = query_results[i]
                text = result["generated_text"]
                del result["generated_text"]
                results[prompt].append({"model": m, "result": text, "stats": result})

        progress.add_task(description="Writing output file.", total=None)
        with open(output_file, "w") as f:
            f.write(json.dumps(results, indent=2))


evaluator_type = typer.Option(help="Which LLM to use for evaluation")


@app.command()
def evaluate(
    input_file: Annotated[str, results_type] = "aviary-output.json",
    evaluation_file: Annotated[str, results_type] = "evaluation-output.json",
    evaluator: Annotated[str, evaluator_type] = "gpt-4",
):
    """Evaluate and summarize the results of a multi_query run with a strong
    'evaluator' LLM like GPT-4.
    The results of the ranking are stored to file and displayed in a table.
    """
    with progress_spinner() as progress:
        progress.add_task(description="Loading the evaluator LLM.", total=None)
        if evaluator == "gpt-4":
            from aviary.common.evaluation import GPT

            eval_model = GPT()
        else:
            raise NotImplementedError(f"No evaluator for {evaluator}")

        with open(input_file, "r") as f:
            results = json.load(f)

        for prompt, result_list in results.items():
            progress.add_task(
                description=f"Evaluating results for prompt: {prompt}.", total=None
            )
            evaluation = eval_model.evaluate_results(prompt, result_list)
            try:
                # GPT-4 returns a string with a Python dictionary, hopefully!
                evaluation = ast.literal_eval(evaluation)
            except Exception:
                print(f"Could not parse evaluation: {evaluation}")

            for i, _res in enumerate(results[prompt]):
                results[prompt][i]["rank"] = evaluation[i]["rank"]

        progress.add_task(description="Storing evaluations.", total=None)
        with open(evaluation_file, "w") as f:
            f.write(json.dumps(results, indent=2))

    for prompt in results.keys():
        table = Table(title="Evaluation results (higher ranks are better)")

        table.add_column("Model", justify="left", style="cyan", no_wrap=True)
        table.add_column("Rank", style="magenta")
        table.add_column("Response", justify="right", style="green")

        for i, _res in enumerate(results[prompt]):
            model = results[prompt][i]["model"]
            response = results[prompt][i]["result"]
            rank = results[prompt][i]["rank"]
            table.add_row(model, str(rank), response)

        console = Console()
        console.print(table)


if __name__ == "__main__":
    app()
