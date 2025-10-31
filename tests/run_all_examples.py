#!/usr/bin/env python3
"""
Run all evaluation examples concurrently against DesktopEnv with docker_server provider.

- Enumerates JSON examples under evaluation_examples/examples/**.
- Sets token limit to max_workers via /set_token_limit on the docker_server.
- For each example:
  * Start VM (DesktopEnv with provider_name="docker_server", os_type="Ubuntu").
  * Reset with the example config to obtain initial observation via _get_obs.
  * Save screenshot and observation metadata under testtotal/{task_id}/.
  * Evaluate via DesktopEnv.evaluate() and save result.json.
  * On initialization failure, write error.json and ensure env.close() to delete the VM.
- Runs up to max_workers=10 tasks concurrently.
- Writes a summary.json in testtotal/ with successes/failures.

Usage:
  PYTHONPATH=. python tests/run_all_examples.py \
    --base-url http://127.0.0.1:50003 \
    --token loadtest \
    --max-workers 10 \
    --os-type Ubuntu
"""
import argparse
import base64
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List

import requests

# Project paths
EXAMPLES_DIR = Path("evaluation_examples/examples")
OUT_BASE = Path("testtotal")


def set_token_limit(base_url: str, token: str, limit: int) -> None:
    url = f"{base_url.rstrip('/')}/set_token_limit"
    try:
        r = requests.post(url, json={"token": token, "limit": int(limit)}, timeout=20)
        print(f"[info] set_token_limit({token} -> {limit}): {r.status_code} {getattr(r, 'text', '')[:200]}")
    except Exception as e:
        print(f"[warn] set_token_limit failed: {e}")


def ping(base_url: str) -> bool:
    url = f"{base_url.rstrip('/')}/ping"
    try:
        r = requests.get(url, timeout=10)
        print(f"[info] ping: {r.status_code} {getattr(r, 'text', '')[:200]}")
        return r.ok
    except Exception as e:
        print(f"[error] ping failed: {e}")
        return False


def decode_and_write_screenshot(screenshot: Any, out_png: Path) -> None:
    try:
        if isinstance(screenshot, (bytes, bytearray)):
            out_png.write_bytes(screenshot)
            return
        if isinstance(screenshot, str):
            try:
                out_png.write_bytes(base64.b64decode(screenshot))
                return
            except Exception:
                pass
        # Fallback: write raw representation for debugging
        out_png.write_text(str(screenshot), encoding="utf-8")
    except Exception as e:
        print(f"[warn] failed to write screenshot: {e}")


def iter_examples() -> List[Path]:
    return list(EXAMPLES_DIR.rglob("*.json"))


def run_single_example(example_path: Path, token: str, os_type: str) -> Dict[str, Any]:
    started_at = time.time()
    example_data = json.loads(example_path.read_text(encoding="utf-8"))
    task_id = example_data.get("id") or example_path.stem
    out_dir = OUT_BASE / task_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save a copy of the example for reference
    (out_dir / "example.json").write_text(json.dumps(example_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ensure token is available to docker_server provider
    os.environ["OSWORLD_TOKEN"] = token

    from desktop_env.desktop_env import DesktopEnv  # import here so script can run without full PYTHONPATH if needed

    env = None
    try:
        # Instantiate environment
        env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type=os_type,
        )

        # Reset with task config to initialize environment and get initial obs
        obs = env.reset(task_config=example_data)

        # Optionally (to satisfy requirement), invoke _get_obs explicitly and compare
        initial_obs = env._get_obs()
        # Prefer saving the obs from reset as the "initial" screenshot
        decode_and_write_screenshot(obs.get("screenshot"), out_dir / "screenshot.png")

        # Save small metadata (avoid writing huge blobs twice)
        meta = {
            "keys": list(obs.keys()),
            "instruction": obs.get("instruction"),
            "accessibility_tree_present": obs.get("accessibility_tree") is not None,
            "terminal_present": obs.get("terminal") is not None,
        }
        (out_dir / "obs_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Evaluate the task
        score = env.evaluate()
        result = {
            "task_id": task_id,
            "example_path": str(example_path),
            "status": "init_ok",
            "score": float(score) if score is not None else None,
            "started_at": started_at,
            "finished_at": time.time(),
        }
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"task_id": task_id, "status": "success", "score": result["score"]}
    except Exception as e:
        fail = {
            "task_id": task_id,
            "example_path": str(example_path),
            "error": str(e),
            "traceback": traceback.format_exc(),
            "status": "init_failed",
            "started_at": started_at,
            "finished_at": time.time(),
        }
        (out_dir / "error.json").write_text(json.dumps(fail, ensure_ascii=False, indent=2), encoding="utf-8")
        # Ensure VM cleanup on failure
        try:
            if env:
                env.close()
        except Exception as ce:
            print(f"[warn] env.close() error after failure: {ce}")
        return {"task_id": task_id, "status": "failed"}
    finally:
        # Always attempt to close the environment
        try:
            if env:
                env.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", type=str, default="http://127.0.0.1:50003", help="Base URL for docker_server API")
    ap.add_argument("--token", type=str, default="loadtest", help="Token to use for docker_server")
    ap.add_argument("--max-workers", type=int, default=10, help="Maximum concurrent tasks (VMs)")
    ap.add_argument("--os-type", type=str, default="Ubuntu", help="OS type to pass to DesktopEnv")
    args = ap.parse_args()

    base_url = args.base_url.strip().rstrip("/")
    token = args.token.strip()
    max_workers = max(1, args.max_workers)
    os_type = args.os_type.strip()

    OUT_BASE.mkdir(parents=True, exist_ok=True)

    # Ping server
    if not ping(base_url):
        print("[error] docker_server not reachable. Start it via:")
        print("  PYTHONPATH=. python -m desktop_env.docker_server.server")
        sys.exit(1)

    # Raise token limit to at least max_workers
    set_token_limit(base_url, token, max_workers)

    files = iter_examples()
    print(f"[info] Found {len(files)} example JSON files under {EXAMPLES_DIR}")

    successes: List[str] = []
    failures: List[str] = []

    start_global = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(run_single_example, p, token, os_type): p for p in files}
        for f in as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                # Defensive: capture any runner-level exception
                print(f"[warn] runner exception: {e}")
                continue
            task_id = res.get("task_id")
            if res.get("status") == "success":
                successes.append(task_id)
                print(f"[info] {task_id}: success")
            else:
                failures.append(task_id)
                print(f"[info] {task_id}: failed")

    summary = {
        "token": token,
        "max_workers": max_workers,
        "examples_total": len(files),
        "successes": successes,
        "failures": failures,
        "success_count": len(successes),
        "failure_count": len(failures),
        "started_at": start_global,
        "finished_at": time.time(),
        "duration_secs": time.time() - start_global,
    }
    (OUT_BASE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[info] Summary written to", OUT_BASE / "summary.json")


if __name__ == "__main__":
    main()
