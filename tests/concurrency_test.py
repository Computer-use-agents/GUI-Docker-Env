#!/usr/bin/env python3
"""
Concurrency capacity test for OSWorld Docker Server.

What it does:
- Optionally raises the token limit via /set_token_limit
- Ramps concurrent POSTs to /start_emulator for a given token
- Holds them for a short period (to keep them simultaneously alive)
- Collects success/failure stats and server load metrics (/status)
- Stops all successfully started emulators between steps (optional)
- Optionally triggers server-side cleanup (/cleanup)
- Saves a detailed JSON report under logs/concurrency_test_*.json

Usage example:
  python tests/concurrency_test.py \
    --base-url http://127.0.0.1:50003 \
    --token loadtest \
    --max 20 \
    --step 5 \
    --hold-secs 20 \
    --request-timeout 300 \
    --no-stop-between-steps false \
    --cleanup true
"""
import argparse
import concurrent.futures as futures
import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

import requests


def _join(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


def ping(session: requests.Session, base_url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    try:
        r = session.get(_join(base_url, "ping"), timeout=10)
        return True, {"status_code": r.status_code, "text": r.text}
    except Exception as e:
        return False, {"error": str(e)}


def set_token_limit(session: requests.Session, base_url: str, token: str, limit: int) -> Tuple[bool, Dict[str, Any]]:
    url = _join(base_url, "set_token_limit")
    try:
        r = session.post(url, json={"token": token, "limit": limit}, timeout=30)
        ok = r.ok
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return ok, {"status_code": r.status_code, "data": data}
    except Exception as e:
        return False, {"error": str(e)}


def start_emulator(session: requests.Session, base_url: str, token: str, request_timeout: int) -> Tuple[bool, Dict[str, Any]]:
    """
    Returns (ok, details)
    details:
      - if ok: {"status_code", "data", "emulator_id"}
      - else: {"status_code", "data"} or {"error": "..."}
    """
    url = _join(base_url, "start_emulator")
    try:
        r = session.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"token": token},
            timeout=request_timeout,
        )
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}

        if r.ok and isinstance(data, dict) and data.get("code") == 0 and data.get("data", {}).get("emulator_id"):
            emulator_id = data["data"]["emulator_id"]
            return True, {"status_code": r.status_code, "data": data, "emulator_id": emulator_id}
        else:
            return False, {"status_code": r.status_code, "data": data}
    except Exception as e:
        return False, {"error": str(e)}


def stop_emulator(session: requests.Session, base_url: str, emulator_id: str) -> Tuple[bool, Dict[str, Any]]:
    url = _join(base_url, "stop_emulator")
    try:
        r = session.post(url, json={"emulator_id": emulator_id}, timeout=30)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.ok, {"status_code": r.status_code, "data": data}
    except Exception as e:
        return False, {"error": str(e)}


def cleanup(session: requests.Session, base_url: str) -> Tuple[bool, Dict[str, Any]]:
    url = _join(base_url, "cleanup")
    try:
        r = session.post(url, timeout=60)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.ok, {"status_code": r.status_code, "data": data}
    except Exception as e:
        return False, {"error": str(e)}


def status(session: requests.Session, base_url: str) -> Tuple[bool, Dict[str, Any]]:
    url = _join(base_url, "status")
    try:
        r = session.get(url, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = {"text": r.text}
        return r.ok, {"status_code": r.status_code, "data": data}
    except Exception as e:
        return False, {"error": str(e)}


def step_launch_and_hold(
    session_factory,
    base_url: str,
    token: str,
    conc: int,
    request_timeout: int,
    hold_secs: int,
) -> Dict[str, Any]:
    """
    Launch 'conc' emulators concurrently, hold for hold_secs, then return results.
    Does NOT stop emulators; caller decides cleanup.
    """
    results: List[Tuple[bool, Dict[str, Any]]] = []
    emulator_ids: List[str] = []

    def worker() -> Tuple[bool, Dict[str, Any]]:
        s = session_factory()
        return start_emulator(s, base_url, token, request_timeout)

    # Launch concurrently
    started_at = time.time()
    with futures.ThreadPoolExecutor(max_workers=conc) as pool:
        futs = [pool.submit(worker) for _ in range(conc)]
        for f in futures.as_completed(futs):
            ok, details = f.result()
            results.append((ok, details))
            if ok and "emulator_id" in details:
                emulator_ids.append(details["emulator_id"])

    # Hold period to keep them alive simultaneously
    time.sleep(max(0, hold_secs))

    # Snapshot server status
    s = session_factory()
    st_ok, st = status(s, base_url)

    finished_at = time.time()

    return {
        "concurrency": conc,
        "launched": len(results),
        "success": sum(1 for ok, _ in results if ok),
        "failures": [d for ok, d in results if not ok],
        "emulator_ids": emulator_ids,
        "status_snapshot": st if st_ok else {"ok": False, "data": st},
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_secs": finished_at - started_at,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", type=str, default="http://127.0.0.1:50003", help="Base URL of docker server")
    ap.add_argument("--token", type=str, default="loadtest", help="Token to use for the test")
    ap.add_argument("--max", dest="max_conc", type=int, default=20, help="Max concurrency to try")
    ap.add_argument("--step", type=int, default=5, help="Step size for ramping concurrency")
    ap.add_argument("--hold-secs", type=int, default=20, help="Seconds to hold VMs per step")
    ap.add_argument("--request-timeout", type=int, default=300, help="Per-request timeout (seconds) for /start_emulator")
    ap.add_argument("--no-stop-between-steps", dest="stop_between", action="store_false", help="Do not stop emulators between steps")
    ap.add_argument("--cleanup", type=str, default="true", help="Whether to call /cleanup at the end (true/false)")
    args = ap.parse_args()

    base_url = args.base_url.strip()
    token = args.token.strip()
    max_conc = max(1, args.max_conc)
    step = max(1, args.step)
    hold_secs = max(0, args.hold_secs)
    request_timeout = max(30, args.request_timeout)
    stop_between = bool(args.stop_between)
    do_cleanup = str(args.cleanup).lower() in ("1", "true", "yes", "y")

    def make_session() -> requests.Session:
        s = requests.Session()
        # Authorization header for token-protected endpoints
        s.headers.update({"Authorization": f"Bearer {token}"})
        return s

    print(f"[info] Pinging server at {base_url} ...")
    ok, pong = ping(make_session(), base_url)
    if not ok:
        print(f"[error] Server ping failed: {pong}")
        return
    print(f"[info] Ping OK: {pong}")

    # Raise token limit high enough for the test
    desired_limit = max_conc + 10
    print(f"[info] Setting token '{token}' limit to {desired_limit} ...")
    ok, resp = set_token_limit(make_session(), base_url, token, desired_limit)
    if not ok:
        print(f"[warn] Could not set token limit: {resp}")

    # Prepare report
    os.makedirs("logs", exist_ok=True)
    started_global = time.time()
    report: Dict[str, Any] = {
        "base_url": base_url,
        "token": token,
        "max_concurrency": max_conc,
        "step": step,
        "hold_secs": hold_secs,
        "request_timeout": request_timeout,
        "stop_between_steps": stop_between,
        "started_at": started_global,
        "steps": [],
    }

    all_started_ids: List[str] = []

    try:
        for conc in range(step, max_conc + 1, step):
            print(f"[info] Launching concurrency={conc} ...")
            step_res = step_launch_and_hold(make_session, base_url, token, conc, request_timeout, hold_secs)
            report["steps"].append(step_res)

            succ = step_res["success"]
            ids = list(step_res["emulator_ids"])
            all_started_ids.extend(ids)

            print(f"[info] Step done: success={succ}/{conc}, duration={step_res['duration_secs']:.1f}s")
            st = step_res.get("status_snapshot", {})
            if isinstance(st, dict) and st.get("status_code") == 200:
                sd = st.get("data", {})
                print(f"[info] Status snapshot: total_emulators={sd.get('total_emulators')}, "
                      f"cpu={sd.get('cpu_percent')}, mem={sd.get('memory_percent')}")

            if stop_between and ids:
                print(f"[info] Stopping {len(ids)} emulators from this step ...")
                with futures.ThreadPoolExecutor(max_workers=min(16, len(ids))) as pool:
                    futs = [pool.submit(stop_emulator, make_session(), base_url, eid) for eid in ids]
                    _ = [f.result() for f in futs]
                # brief cooldown
                time.sleep(5)

        # Persist report
        finished_global = time.time()
        report["finished_at"] = finished_global
        report["duration_secs"] = finished_global - started_global

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join("logs", f"concurrency_test_{ts}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[info] Report saved to {out_path}")

    finally:
        if not stop_between:
            # If user kept VMs between steps, try to stop all started
            if all_started_ids:
                print(f"[info] Stopping all {len(all_started_ids)} started emulators ...")
                with futures.ThreadPoolExecutor(max_workers=min(16, len(all_started_ids))) as pool:
                    futs = [pool.submit(stop_emulator, make_session(), base_url, eid) for eid in all_started_ids]
                    _ = [f.result() for f in futs]
                time.sleep(5)

        if do_cleanup:
            print("[info] Triggering server-side cleanup (/cleanup) ...")
            ok, resp = cleanup(make_session(), base_url)
            if ok:
                print(f"[info] Cleanup ok: {resp}")
            else:
                print(f"[warn] Cleanup failed: {resp}")


if __name__ == "__main__":
    main()
