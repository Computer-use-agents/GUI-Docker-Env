import os
import requests
from typing import Optional, Dict, Any, List

from desktop_env.desktop_env import DesktopEnv

# 为本地测试提供默认值（若外部已设置环境变量则不会覆盖）
os.environ.setdefault("OSWORLD_TOKEN", "enqi")
os.environ.setdefault("OSWORLD_BASE_URL", "http://10.1.110.48:50003")


def _get_base_url(base_url: Optional[str] = None) -> str:
    """
    获取后端 Docker 服务的 base_url，优先使用函数参数，其次使用环境变量 OSWORLD_BASE_URL。
    """
    url = base_url or os.getenv("OSWORLD_BASE_URL") or "http://localhost:50003"
    return url.rstrip("/")


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    """
    生成带 Bearer Token 的请求头（若 token 为 None 则返回空字典）。
    """
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def list_emulators_by_token(token: str, base_url: Optional[str] = None, detail: bool = False) -> Any:
    """
    查询某个 token 名下的所有虚拟机（emulator_id）。
    - detail=False: 返回 emulator_id 列表
    - detail=True:  返回带详细信息的字典列表（包含端口、container_id、资源信息等）

    说明：
    - 使用 /emulators 端点获取所有实例后，在客户端按 token 过滤（轻量，不含资源）
    - 使用 /emulator_resources 端点可以一次性得到所有实例资源信息（包含 container_id），再按 token 过滤
    """
    url = _get_base_url(base_url)
    try:
        if detail:
            # 包含 container_id、资源等信息
            resp = requests.get(f"{url}/emulator_resources", headers=_auth_headers(token), timeout=15)
            resp.raise_for_status()
            items = resp.json()
            return [item for item in items if item.get("token") == token]
        else:
            # 仅获取 id 列表（轻量）
            resp = requests.get(f"{url}/emulators", headers=_auth_headers(token), timeout=10)
            resp.raise_for_status()
            items = resp.json()
            return [i.get("emulator_id") for i in items if i.get("token") == token]
    except Exception as e:
        return {"error": str(e)}


def get_emulator_status(emulator_id: str, base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    查询某个虚拟机的状态。
    由于服务端当前未显式返回状态字段，这里约定：
    - 若 /emulator_resources/<id> 能返回 200，则认为 status='running'
    - 若返回 404，则认为 status='not_found'

    返回示例：
    {
        "emulator_id": "...",
        "status": "running" | "not_found" | "error",
        "token": "...",
        "container_id": "...",
        "ports": {...},
        "duration_minutes": 3,
        "resources": {...} | {"error": "..."} | None,
        "error": "..."(仅在出错时)
    }
    """
    url = _get_base_url(base_url)
    try:
        r = requests.get(f"{url}/emulator_resources/{emulator_id}", timeout=15)
        if r.status_code == 404:
            return {"emulator_id": emulator_id, "status": "not_found"}
        r.raise_for_status()
        data = r.json()
        return {
            "emulator_id": emulator_id,
            "status": "running",
            "token": data.get("token"),
            "container_id": data.get("container_id"),
            "ports": {
                "server_port": data.get("server_port"),
                "vnc_port": data.get("vnc_port"),
                "chromium_port": data.get("chromium_port"),
                "vlc_port": data.get("vlc_port"),
            },
            "duration_minutes": data.get("duration_minutes"),
            "resources": data.get("resources"),
        }
    except Exception as e:
        return {"emulator_id": emulator_id, "status": "error", "error": str(e)}


def stop_emulator(emulator_id: str, token: Optional[str] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
    """
    停止某个虚拟机（给定 emulator_id）。
    - 使用 /stop_emulator 端点，按约定传入 JSON: {"emulator_id": "..."}。
    - 若服务端开启 REQUIRE_TOKEN，可同时附带 Authorization: Bearer <token> 头。

    返回示例：
    {
        "emulator_id": "...",
        "stopped": True | False,
        "response": {...} | None,
        "message": "...",        # 仅某些错误/404 情况
        "error": "..."           # 仅请求异常时
    }
    """
    url = _get_base_url(base_url)
    try:
        r = requests.post(
            f"{url}/stop_emulator",
            json={"emulator_id": emulator_id},
            headers=_auth_headers(token),
            timeout=20,
        )
        if r.status_code == 404:
            return {"emulator_id": emulator_id, "stopped": False, "message": "not found"}
        # 期望后端返回 {"code": 0} 表示成功
        data = r.json()
        return {
            "emulator_id": emulator_id,
            "stopped": data.get("code") == 0,
            "response": data,
        }
    except Exception as e:
        return {"emulator_id": emulator_id, "stopped": False, "error": str(e)}


if __name__ == "__main__":
    # 读取环境变量
    token = os.environ.get("OSWORLD_TOKEN", "enqi")
    base_url = os.environ.get("OSWORLD_BASE_URL", "http://localhost:50003")
    print(f"[env_test] base_url={base_url}, token={token}")

    # 启动一个远程 Docker 虚拟机（会通过 RemoteDockerProvider 调用 /start_emulator）
    env = DesktopEnv(
        action_space="pyautogui",
        provider_name="docker_server",
        os_type="Ubuntu",
    )

    emu_id = None
    try:
        # 从 RemoteDockerProvider 读取刚启动的 emulator_id 和端口
        emu_id = getattr(env.provider, "emulator_id", None)
        print(f"[env_test] started emulator_id: {emu_id}")
        print(
            "[env_test] ports: "
            f"server={env.provider.server_port}, "
            f"vnc={env.provider.vnc_port}, "
            f"chromium={env.provider.chromium_port}, "
            f"vlc={env.provider.vlc_port}"
        )

        # 1) 列出该 token 下所有虚拟机（仅 id）
        print("\n[env_test] List emulators by token (detail=False):")
        print(list_emulators_by_token(token, base_url, detail=False))

        # 2) 列出该 token 下所有虚拟机（带详细信息，包含 container_id / 资源情况）
        print("\n[env_test] List emulators by token (detail=True):")
        detail_items: Any = list_emulators_by_token(token, base_url, detail=True)
        print(detail_items)

        # 3) 查询刚启动的虚拟机状态
        if emu_id:
            print("\n[env_test] Emulator status:")
            status = get_emulator_status(emu_id, base_url)
            print(status)

        # 4) 停止该虚拟机
        if emu_id:
            print("\n[env_test] Stop emulator:")
            stop_res = stop_emulator(emu_id, token, base_url)
            print(stop_res)

        # 5) 再次查询该 token 下虚拟机
        print("\n[env_test] List emulators after stop (detail=False):")
        print(list_emulators_by_token(token, base_url, detail=False))

    finally:
        # 确保资源清理（若已经通过远程 stop 了，这里可能无需再次 stop）
        try:
            env.close()
        except Exception:
            pass
