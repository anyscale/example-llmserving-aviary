import sys
from typing import List, Union

import ray._private.usage.usage_lib
from ray import serve

from aviary.backend.server.app import LLMDeployment, RouterDeployment
from aviary.backend.server.models import LLMApp, ServeArgs
from aviary.backend.server.utils import parse_args


def llm_server(args: Union[str, LLMApp, List[Union[LLMApp, str]]]):
    """Serve LLM Models

    This function returns a Ray Serve Application.

    Accepted inputs:
    1. The path to a yaml file defining your LLMApp
    2. The path to a folder containing yaml files, which define your LLMApps
    2. A list of yaml files defining multiple LLMApps
    3. A dict or LLMApp object
    4. A list of dicts or LLMApp objects

    You can use `serve.run` to run this application on the local Ray Cluster.

    `serve.run(llm_backend(args))`.

    You can also remove
    """
    models = parse_args(args)
    if not models:
        raise RuntimeError("No enabled models were found.")

    # For each model, create a deployment
    deployments = {}
    model_configs = {}
    for model in models:
        print("Initializing LLM app", model.json(indent=2))
        user_config = model.dict()
        deployment_config = model.deployment_config.dict()
        model_configs[model.model_config.model_id] = model

        deployment_config = deployment_config.copy()
        max_concurrent_queries = deployment_config.pop(
            "max_concurrent_queries", None
        ) or user_config["model_config"]["generation"].get("max_batch_size", 1)
        deployments[model.model_config.model_id] = LLMDeployment.options(
            name=model.model_config.model_id.replace("/", "--").replace(".", "_"),
            max_concurrent_queries=max_concurrent_queries,
            user_config=user_config,
            **deployment_config,
        ).bind()

    return RouterDeployment.bind(deployments, model_configs)


def llm_application(args):
    """This is a simple wrapper for LLM Server
    That is compatible with the yaml config file format

    """
    serve_args = ServeArgs.parse_obj(args)
    return llm_server(serve_args.models)


def run(*models: Union[LLMApp, str]):
    """Run the LLM Server on the local Ray Cluster

    Args:
        *models: A list of LLMApp objects or paths to yaml files defining LLMApps

    Example:
       run("models/")           # run all models in the models directory
       run("models/model.yaml") # run one model in the model directory
       run({...LLMApp})         # run a single LLMApp
       run("models/model1.yaml", "models/model2.yaml", {...LLMApp}) # mix and match
    """
    app = llm_server(list(models))
    ray._private.usage.usage_lib.record_library_usage("aviary")
    serve.run(app, host="0.0.0.0")


if __name__ == "__main__":
    run(*sys.argv[1:])
