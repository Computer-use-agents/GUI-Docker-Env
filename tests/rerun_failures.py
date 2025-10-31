#!/usr/bin/env python3
"""
Rerun only failure cases from an existing testtotal/summary.json and save results to a new out directory.

Usage example:
  PYTHONPATH=. python tests/rerun_failures.py \
    --base-url http://127.0.0.1:50003 \
    --token loadtest \
    --os-type Ubuntu \
    --from-summary testtotal/summary.json \
    --out-base testtotal_2 \
    --max-workers 10
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
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_FROM_SUMMARY = Path("testtotal/summary.json")
DEFAULT_OUT_BASE = Path("testtotal_2")
EVAL_EXAMPLES_DIR = Path("evaluation_examples/examples")


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


def load_failures(summary_path: Path) -> List[str]:
    if not summary_path.exists():
        raise FileNotFoundError(f"summary.json not found at {summary_path}")
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    failures = data.get("failures", [])
    if not isinstance(failures, list):
        raise ValueError("Invalid summary.json format: 'failures' is not a list")
    return failures


def load_example_from_testtotal(task_id: str) -> Optional[Tuple[Dict[str, Any], str]]:
    # Preferred source: testtotal/{task_id}/example.json
    ex_path = Path("testtotal") / task_id / "example.json"
    if ex_path.exists():
        try:
            example = json.loads(ex_path.read_text(encoding="utf-8"))
            return example, str(ex_path)
        except Exception as e:
            print(f"[warn] failed reading {ex_path}: {e}")

    # Fallback: read error.json to get example_path
    err_path = Path("testtotal") / task_id / "error.json"
    if err_path.exists():
        try:
            ej = json.loads(err_path.read_text(encoding="utf-8"))
            ep = ej.get("example_path")
            if ep:
                ep_path = Path(ep)
                if ep_path.exists():
                    try:
                        example = json.loads(ep_path.read_text(encoding="utf-8"))
                        return example, str(ep_path)
                    except Exception as e:
                        print(f"[warn] failed reading {ep_path}: {e}")
        except Exception as e:
            print(f"[warn] failed reading {err_path}: {e}")

    # Last resort: search in evaluation_examples by filename {task_id}.json
    candidates = list(EVAL_EXAMPLES_DIR.rglob(f"{task_id}.json"))
    for p in candidates:
        try:
            example = json.loads(p.read_text(encoding="utf-8"))
            return example, str(p)
        except Exception:
            continue

    return None


def run_single_example_from_payload(task_id: str, example_data: Dict[str, Any], example_path: str, token: str, os_type: str, out_base: Path) -> Dict[str, Any]:
    started_at = time.time()
    out_dir = out_base / task_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save a copy of the example for reference
    try:
        (out_dir / "example.json").write_text(json.dumps(example_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[warn] failed to write example.json for {task_id}: {e}")

    # Ensure token is available to docker_server provider
    os.environ["OSWORLD_TOKEN"] = token

    from desktop_env.desktop_env import DesktopEnv  # local import to avoid requiring PYTHONPATH at startup

    env = None
    try:
        env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type=os_type,
        )

        obs = env.reset(task_config=example_data)

        # Save screenshot decoded
        decode_and_write_screenshot(obs.get("screenshot"), out_dir / "screenshot.png")

        # Save small metadata
        meta = {
            "keys": list(obs.keys()),
            "instruction": obs.get("instruction"),
            "accessibility_tree_present": obs.get("accessibility_tree") is not None,
            "terminal_present": obs.get("terminal") is not None,
        }
        (out_dir / "obs_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        score = env.evaluate()
        result = {
            "task_id": task_id,
            "example_path": example_path,
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
            "example_path": example_path,
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
    ap.add_argument("--from-summary", type=str, default=str(DEFAULT_FROM_SUMMARY), help="Path to prior summary.json with failures")
    ap.add_argument("--out-base", type=str, default=str(DEFAULT_OUT_BASE), help="Output base directory for reruns")
    args = ap.parse_args()

    base_url = args.base_url.strip().rstrip("/")
    token = args.token.strip()
    max_workers = max(1, args.max_workers)
    os_type = args.os_type.strip()
    summary_path = Path(args.from_summary)
    out_base = Path(args.out_base)

    out_base.mkdir(parents=True, exist_ok=True)

    # Ping server
    if not ping(base_url):
        print("[error] docker_server not reachable. Start it via:")
        print("  PYTHONPATH=. python -m desktop_env.docker_server.server")
        sys.exit(1)

    # Raise token limit to at least max_workers for concurrency
    set_token_limit(base_url, token, max_workers)

    # Collect failures to rerun
    failed_ids = load_failures(summary_path)
    print(f"[info] Rerunning {len(failed_ids)} failure cases from {summary_path}")

    successes: List[str] = []
    failures: List[str] = []

    def _prepare_and_run(tid: str) -> Dict[str, Any]:
        loaded = load_example_from_testtotal(tid)
        if not loaded:
            # Could not locate example payload; record as failure
            out_dir = out_base / tid
            out_dir.mkdir(parents=True, exist_ok=True)
            fail = {
                "task_id": tid,
                "example_path": "",
                "error": f"Unable to locate example payload for {tid}",
                "traceback": "",
                "status": "init_failed",
                "started_at": time.time(),
                "finished_at": time.time(),
            }
            (out_dir / "error.json").write_text(json.dumps(fail, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"task_id": tid, "status": "failed"}
        example_data, example_path = loaded
        # Ensure task_id matches; prefer original tid for directory stability
        ex_tid = example_data.get("id") or tid
        return run_single_example_from_payload(task_id=ex_tid, example_data=example_data, example_path=example_path, token=token, os_type=os_type, out_base=out_base)

    start_global = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_prepare_and_run, tid): tid for tid in failed_ids}
        for f in as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                # Defensive capture
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
        "examples_total": len(failed_ids),
        "successes": successes,
        "failures": failures,
        "success_count": len(successes),
        "failure_count": len(failures),
        "source_summary": str(summary_path),
        "started_at": start_global,
        "finished_at": time.time(),
        "duration_secs": time.time() - start_global,
    }
    (out_base / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[info] Summary written to", out_base / "summary.json")


if __name__ == "__main__":
    main()
