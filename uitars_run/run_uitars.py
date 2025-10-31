"""Script to run end-to-end evaluation on the benchmark.
Utils and basic architecture credit to https://github.com/web-arena-x/webarena/blob/main/run.py.

Refactored to:
- Initialize DesktopEnv using docker_server provider consistent with tests/run_all_examples.py
- Support concurrent execution across multiple environments with configurable max parallelism
"""

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from tqdm import tqdm

from mm_agents.uitars15_v1 import UITARSAgent
import lib_run_single
from desktop_env.desktop_env import DesktopEnv

#  Logger Configs {{{ #
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

file_handler = logging.FileHandler(
    os.path.join("logs", "normal-{:}.log".format(datetime_str)), encoding="utf-8"
)
debug_handler = logging.FileHandler(
    os.path.join("logs", "debug-{:}.log".format(datetime_str)), encoding="utf-8"
)
stdout_handler = logging.StreamHandler(sys.stdout)
sdebug_handler = logging.FileHandler(
    os.path.join("logs", "sdebug-{:}.log".format(datetime_str)), encoding="utf-8"
)

file_handler.setLevel(logging.INFO)
debug_handler.setLevel(logging.DEBUG)
stdout_handler.setLevel(logging.INFO)
sdebug_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s"
)
file_handler.setFormatter(formatter)
debug_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
sdebug_handler.setFormatter(formatter)

stdout_handler.addFilter(logging.Filter("desktopenv"))
sdebug_handler.addFilter(logging.Filter("desktopenv"))

logger.addHandler(file_handler)
logger.addHandler(debug_handler)
logger.addHandler(stdout_handler)
logger.addHandler(sdebug_handler)
#  }}} Logger Configs #

logger = logging.getLogger("desktopenv.experiment")


def ping(base_url: str) -> bool:
    """Check docker_server availability."""
    url = f"{base_url.rstrip('/')}/ping"
    try:
        r = requests.get(url, timeout=10)
        print(f"[info] ping: {r.status_code} {getattr(r, 'text', '')[:200]}")
        return r.ok
    except Exception as e:
        print(f"[error] ping failed: {e}")
        return False




def load_data_json_list(
    index_path: Path = Path("evaluation_examples/test_all.json"),
    examples_root: Path = Path("evaluation_examples/examples"),
    keys: Optional[List[str]] = None,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """
    按 test_all.json 的索引，将 examples/{app}/{id}.json 逐个读入并放入列表返回。
    仅保留每个文件的 JSON 主体（dict）。
    - keys: 可选，若提供则仅读取这些 app
    - strict: True 则遇到缺失或解析错误直接抛异常；False 则跳过并告警
    """
    index_path = Path(index_path)
    examples_root = Path(examples_root)

    if not index_path.exists():
        msg = f"Index file not found: {index_path}"
        if strict:
            raise FileNotFoundError(msg)
        logger.warning(msg)
        return []

    try:
        with index_path.open("r", encoding="utf-8") as f:
            index_data = json.load(f)
    except Exception as e:
        if strict:
            raise
        logger.warning(f"Failed to parse index JSON {index_path}: {e}")
        return []

    if not isinstance(index_data, dict):
        msg = f"Index JSON is not an object: {index_path}"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return []

    target_keys = set(keys) if keys else set(index_data.keys())
    data_json_list: List[Dict[str, Any]] = []

    for app in sorted(target_keys):
        ids = index_data.get(app)
        if not isinstance(ids, list):
            logger.warning(f"Index entry for key '{app}' is not a list; skipping.")
            continue
        for sample_id in ids:
            file_path = examples_root / app / f"{sample_id}.json"
            if not file_path.exists():
                msg = f"Missing example file: {file_path}"
                if strict:
                    raise FileNotFoundError(msg)
                logger.warning(msg)
                continue
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                data_json_list.append(data)
            except Exception as e:
                if strict:
                    raise
                logger.warning(f"Failed to load {file_path}: {e}")
                continue

    return data_json_list


def config() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end evaluation on the benchmark"
    )

    # docker_server / env server config
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:50003", help="Base URL for docker_server API")
    parser.add_argument("--token", type=str, required=True, help="Token to use for docker_server (required)")
    parser.add_argument("--max-workers", type=int, default=8, help="Maximum concurrent tasks (VMs)")
    parser.add_argument("--os-type", type=str, default="Ubuntu", help="OS type to pass to DesktopEnv")

    # environment config
    parser.add_argument("--path_to_vm", type=str, default=None)
    parser.add_argument("--headless", action="store_true", help="Run in headless machine")
    parser.add_argument("--action_space", type=str, default="pyautogui", help="Action type")
    parser.add_argument(
        "--observation_type",
        choices=["screenshot", "a11y_tree", "screenshot_a11y_tree", "som"],
        default="screenshot",
        help="Observation type",
    )
    parser.add_argument("--screen_width", type=int, default=1920)
    parser.add_argument("--screen_height", type=int, default=1080)
    parser.add_argument("--sleep_after_execution", type=float, default=2.0)
    parser.add_argument("--max_steps", type=int, default=15)

    # agent config
    parser.add_argument("--max_trajectory_length", type=int, default=50)
    parser.add_argument("--test_config_base_dir", type=str, default="evaluation_examples")

    # lm config
    parser.add_argument("--model", type=str, default="ui_tars_1.5")
    parser.add_argument("--model_type", type=str, default="qwen25vl")
    parser.add_argument("--infer_mode", type=str, default="qwen25vl_normal")
    parser.add_argument("--prompt_style", type=str, default="qwen25vl_normal")
    parser.add_argument("--input_swap", action="store_true", help="Use copy and paste to type content")
    parser.add_argument("--language", type=str, default="English")
    parser.add_argument("--max_pixels", type=float, default=16384*28*28)
    parser.add_argument("--min_pixels", type=float, default=100*28*28)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--top_k", type=int, default=-1)
    parser.add_argument("--history_n", type=int, default=5)
    parser.add_argument("--callusr_tolerance", type=int, default=3)
    parser.add_argument("--max_tokens", type=int, default=50000)
    parser.add_argument("--stop_token", type=str, default=None)

    # example config
    parser.add_argument("--domain", type=str, default="all")
    parser.add_argument("--test_all_meta_path", type=str, default="evaluation_examples/test_nogdrive.json")

    # warmup / two-phase controls
    parser.add_argument("--warmup-count", type=int, default=8, help="Number of tasks to run in warmup phase before batch")
    parser.add_argument("--auto-continue-after-warmup", dest="auto_continue_after_warmup", action="store_true", help="Continue to batch run after warmup")
    parser.add_argument("--no-auto-continue-after-warmup", dest="auto_continue_after_warmup", action="store_false", help="Disable batch run after warmup")
    parser.set_defaults(auto_continue_after_warmup=True)
    
    # logging related
    parser.add_argument("--result_dir", type=str, default="./results_chenrui")
    args = parser.parse_args()

    return args


def run_one_example(args: argparse.Namespace, domain: str, example_id: str) -> Dict[str, Any]:
    """Run a single example with its own agent and environment, ensuring cleanup."""
    example_result_dir = os.path.join(
        args.result_dir,
        args.action_space,
        args.observation_type,
        args.model,
        domain,
        example_id,
    )
    os.makedirs(example_result_dir, exist_ok=True)

    # Load example config
    config_file = os.path.join(
        args.test_config_base_dir, f"examples/{domain}/{example_id}.json"
    )
    with open(config_file, "r", encoding="utf-8") as f:
        example = json.load(f)

    instruction = example.get("instruction", "")
    logger.info(f"[Domain]: {domain}")
    logger.info(f"[Example ID]: {example_id}")
    logger.info(f"[Instruction]: {instruction}")

    # Fresh agent per example
    agent = UITARSAgent(
        model=args.model,
        action_space=args.action_space,
        observation_type=args.observation_type,
        max_trajectory_length=args.max_trajectory_length,
        model_type=args.model_type,
        runtime_conf={
            "infer_mode": args.infer_mode,
            "prompt_style": args.prompt_style,
            "input_swap": args.input_swap,
            "language": args.language,
            "history_n": args.history_n,
            "max_pixels": args.max_pixels,
            "min_pixels": args.min_pixels,
            "callusr_tolerance": args.callusr_tolerance,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "top_k": args.top_k,
            "max_tokens": args.max_tokens,
        },
    )

    # Initialize environment aligned to tests/run_all_examples.py
    require_a11y = args.observation_type in ["a11y_tree", "screenshot_a11y_tree"]
    env = None
    try:
        env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type=args.os_type,
        )

        # Execute example
        scores_local: List[float] = []  # local buffer if needed
        try:
            lib_run_single.run_single_example(
                agent,
                env,
                example,
                args.max_steps,
                instruction,
                args,
                example_result_dir,
                scores_local,
            )
            status = "success"
        except Exception as e:
            logger.error(f"Exception in {domain}/{example_id}: {e}")
            # Record error into traj.jsonl for consistency
            with open(os.path.join(example_result_dir, "traj.jsonl"), "a", encoding="utf-8") as f:
                f.write(
                    json.dumps({"Error": f"Exception in {domain}/{example_id}: {str(e)}"})
                )
                f.write("\n")
            status = "failed"
        return {"task_id": example.get("id", example_id), "status": status}
    finally:
        try:
            if env:
                env.close()
        except Exception as ce:
            logger.warning(f"env.close() error: {ce}")


def test(args: argparse.Namespace, data_json_list, test_all_meta: dict) -> None:
    # Pre-flight: ensure docker_server reachable and token limit configured

    if not ping(args.base_url):
        print("[error] docker_server not reachable. Start it via:")
        print("  PYTHONPATH=. python -m desktop_env.docker_server.server")
        return

   #  set_token_limit(args.base_url, args.token, args.max_workers)

    # Flatten tasks
    tasks: List[Dict[str, str]] = []
    for domain in sorted(test_all_meta.keys()):
        for example_id in test_all_meta[domain]:
            tasks.append({"domain": domain, "example_id": example_id})

    successes: List[str] = []
    failures: List[str] = []

    def run_batch(batch_tasks: List[Dict[str, str]], max_workers: int) -> None:
        print(f"[info] Dispatching {len(batch_tasks)} tasks with max_workers={max_workers}")
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futs = {pool.submit(run_one_example, args, t["domain"], t["example_id"]): t for t in batch_tasks}
            for f in as_completed(futs):
                try:
                    res = f.result()
                except Exception as e:
                    logger.warning(f"runner exception: {e}")
                    continue
                task_id = res.get("task_id")
                if res.get("status") == "success":
                    successes.append(task_id)
                    print(f"[info] {task_id}: success")
                else:
                    failures.append(task_id)
                    print(f"[info] {task_id}: failed")

   
    run_batch(tasks, max_workers=args.max_workers)
    

    print(f"[info] Completed. success={len(successes)} failed={len(failures)}")


def get_unfinished(
    action_space, use_model, observation_type, result_dir, total_file_json
):
    target_dir = os.path.join(result_dir, action_space, observation_type, use_model)

    if not os.path.exists(target_dir):
        return total_file_json

    finished = {}
    for domain in os.listdir(target_dir):
        finished[domain] = []
        domain_path = os.path.join(target_dir, domain)
        if os.path.isdir(domain_path):
            for example_id in os.listdir(domain_path):
                if example_id == "onboard":
                    continue
                example_path = os.path.join(domain_path, example_id)
                if os.path.isdir(example_path):
                    if "result.txt" not in os.listdir(example_path):
                        # empty all files under example_id
                        for file in os.listdir(example_path):
                            os.remove(os.path.join(example_path, file))
                    else:
                        finished[domain].append(example_id)

    if not finished:
        return total_file_json

    for domain, examples in finished.items():
        if domain in total_file_json:
            total_file_json[domain] = [
                x for x in total_file_json[domain] if x not in examples
            ]

    return total_file_json


def get_result(action_space, use_model, observation_type, result_dir, total_file_json):
    target_dir = os.path.join(result_dir, action_space, observation_type, use_model)
    if not os.path.exists(target_dir):
        print("New experiment, no result yet.")
        return None

    all_result = []

    for domain in os.listdir(target_dir):
        domain_path = os.path.join(target_dir, domain)
        if os.path.isdir(domain_path):
            for example_id in os.listdir(domain_path):
                example_path = os.path.join(domain_path, example_id)
                if os.path.isdir(example_path):
                    if "result.txt" in os.listdir(example_path):
                        # empty all files under example_id
                        try:
                            all_result.append(
                                float(
                                    open(
                                        os.path.join(example_path, "result.txt"), "r"
                                    ).read()
                                )
                            )
                        except Exception:
                            all_result.append(0.0)

    if not all_result:
        print("New experiment, no result yet.")
        return None
    else:
        print("Current Success Rate:", sum(all_result) / len(all_result) * 100, "%")
        return all_result


if __name__ == "__main__":
    ####### The complete version of the list of examples #######
    # os.environ.setdefault("ENV_USER_TOKEN", "chenrui")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    args = config()
    os.environ["OSWORLD_TOKEN"] = args.token
    os.environ["OSWORLD_BASE_URL"] = args.base_url

    # Load meta and optionally filter by domain
    with open(args.test_all_meta_path, "r", encoding="utf-8") as f:
        test_all_meta = json.load(f)

    if args.domain != "all":
        test_all_meta = {args.domain: test_all_meta[args.domain]}

    # Determine unfinished tasks
    test_file_list = get_unfinished(
        args.action_space,
        args.model,
        args.observation_type,
        args.result_dir,
        test_all_meta,
    )
    left_info = ""
    for domain in test_file_list:
        left_info += f"{domain}: {len(test_file_list[domain])}\n"
    logger.info(f"Left tasks:\n{left_info}")

    # Print current results
    get_result(
        args.action_space,
        args.model,
        args.observation_type,
        args.result_dir,
        test_all_meta,
    )

    # Run tests concurrently using docker_server DesktopEnv initialization
    # Note: data_json_list is no longer used for env init; kept for API compatibility
    data_json_list = []
    test(args, data_json_list, test_file_list)
