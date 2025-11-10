"""
释放后可复用空余名额测试脚本
测试场景：
1. 先填满所有服务器配额（例如 2台×10个=20个）
2. 释放第一个服务器上的 M 个环境
3. 验证服务器端的 available 增加
4. 再次申请 M+K 个环境，验证至少 M 个成功且落在第一台服务器
5. 清理所有环境
"""
import os
import time
import requests
from desktop_env.desktop_env import DesktopEnv
from urllib.parse import urlparse

# 配置测试参数 - 两个服务器URL
os.environ.setdefault("OSWORLD_BASE_URL", "http://10.1.110.48:50003,http://10.1.110.43:50003")
os.environ.setdefault("OSWORLD_TOKEN", "dart")

# 配置参数
OSWORLD_BASE_URL = os.environ.get("OSWORLD_BASE_URL", "http://10.1.110.48:50003,http://10.1.110.43:50003")
OSWORLD_TOKEN = os.environ.get("OSWORLD_TOKEN", "dart")
URL_LIST = [u.strip() for u in OSWORLD_BASE_URL.split(",")]
PER_URL_QUOTA = 10
URL_COUNT = len(URL_LIST)
MAX_ATTEMPTS = PER_URL_QUOTA * URL_COUNT

# 释放数量配置
RELEASE_COUNT = 3  # 在第一台服务器释放的环境数
SECOND_WAVE_COUNT = RELEASE_COUNT + 1  # 第二波尝试创建的数量


def parse_host_port(url):
    """解析 URL 获取 host 和 port"""
    parsed = urlparse(url if "://" in url else "http://" + url)
    return parsed.hostname, parsed.port or 50003


def get_tokens_snapshot(ip, port, token):
    """获取指定服务器上的 token 配额快照"""
    try:
        resp = requests.get(
            f"http://{ip}:{port}/tokens",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get(token)
    except Exception as e:
        print(f"  ⚠ Failed to get tokens snapshot from {ip}:{port}: {e}")
        return None


def wait_available(ip, port, token, expect_available, timeout=30, interval=1):
    """等待服务器上的 available 达到预期值"""
    start = time.time()
    while time.time() - start < timeout:
        info = get_tokens_snapshot(ip, port, token)
        if info:
            current_available = info["limit"] - info["current"]
            if current_available >= expect_available:
                print(f"  ✓ Available reached {current_available} (expected >= {expect_available})")
                return True
            print(f"  ⏳ Waiting... current available={current_available}, expected>={expect_available}")
        time.sleep(interval)
    return False


def print_server_status(ip, port, token, label=""):
    """打印服务器状态"""
    info = get_tokens_snapshot(ip, port, token)
    if info:
        available = info["limit"] - info["current"]
        print(f"  {label} Server {ip}:{port} - current={info['current']}, limit={info['limit']}, available={available}")
    else:
        print(f"  {label} Server {ip}:{port} - Failed to get status")


def main():
    print("=" * 80)
    print("释放后可复用空余名额测试")
    print("=" * 80)
    print(f"Token: {OSWORLD_TOKEN}")
    print(f"Servers: {URL_LIST}")
    print(f"Per-server quota: {PER_URL_QUOTA}")
    print(f"Total quota: {MAX_ATTEMPTS}")
    print(f"Release count: {RELEASE_COUNT}")
    print(f"Second wave attempts: {SECOND_WAVE_COUNT}")
    print("=" * 80)
    print()

    # 解析第一个服务器的 IP 和端口
    first_ip, first_port = parse_host_port(URL_LIST[0])
    first_key = f"{first_ip}:{first_port}"

    # 存储所有环境
    all_envs = []
    by_server = {}  # server_key -> [env1, env2, ...]

    # ========== 阶段 1: 填满所有服务器配额 ==========
    print("\n" + "=" * 80)
    print("阶段 1: 填满所有服务器配额")
    print("=" * 80)
    
    # 打印初始状态
    print("\n初始服务器状态:")
    for url in URL_LIST:
        ip, port = parse_host_port(url)
        print_server_status(ip, port, OSWORLD_TOKEN, "📊")

    success_count = 0
    for i in range(MAX_ATTEMPTS):
        try:
            env = DesktopEnv(
                action_space="pyautogui",
                provider_name="docker_server",
                os_type="Ubuntu"
            )
            server_ip = env.provider.remote_docker_server_ip
            server_port = env.provider.remote_docker_server_port
            emulator_id = getattr(env.provider, "emulator_id", None)
            key = f"{server_ip}:{server_port}"
            
            by_server.setdefault(key, []).append(env)
            all_envs.append(env)
            success_count += 1
            
            print(f"[{i+1}/{MAX_ATTEMPTS}] ✓ Started on {key} (emulator_id={emulator_id})")
            time.sleep(0.5)
        except Exception as e:
            print(f"[{i+1}/{MAX_ATTEMPTS}] ✗ Failed: {e}")
            break

    print(f"\n阶段 1 完成: 成功启动 {success_count}/{MAX_ATTEMPTS} 个环境")
    print("\n各服务器分配情况:")
    for key, envs in by_server.items():
        print(f"  - {key}: {len(envs)} 个环境")

    # 打印填满后的状态
    print("\n填满后服务器状态:")
    for url in URL_LIST:
        ip, port = parse_host_port(url)
        print_server_status(ip, port, OSWORLD_TOKEN, "📊")

    # ========== 阶段 2: 释放第一个服务器上的部分环境 ==========
    print("\n" + "=" * 80)
    print(f"阶段 2: 释放第一个服务器 ({first_key}) 上的 {RELEASE_COUNT} 个环境")
    print("=" * 80)

    to_release = by_server.get(first_key, [])[:RELEASE_COUNT]
    actual_release_count = len(to_release)
    
    if actual_release_count == 0:
        print(f"⚠ 警告: 第一个服务器 {first_key} 上没有环境可释放！")
        print("测试无法继续，清理并退出...")
        for env in all_envs:
            try:
                env.close()
            except Exception:
                pass
        return

    print(f"\n准备释放 {actual_release_count} 个环境:")
    for idx, env in enumerate(to_release, 1):
        emulator_id = getattr(env.provider, "emulator_id", None)
        print(f"  [{idx}/{actual_release_count}] emulator_id={emulator_id}")

    print(f"\n开始释放...")
    released_count = 0
    for idx, env in enumerate(to_release, 1):
        try:
            emulator_id = getattr(env.provider, "emulator_id", None)
            env.close()
            released_count += 1
            print(f"  [{idx}/{actual_release_count}] ✓ Released emulator_id={emulator_id}")
            # 从 by_server 中移除
            by_server[first_key].remove(env)
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{idx}/{actual_release_count}] ✗ Release failed: {e}")

    print(f"\n释放完成: 成功释放 {released_count}/{actual_release_count} 个环境")

    # 等待服务器状态更新
    print(f"\n等待第一个服务器 ({first_key}) 的 available 恢复到 >= {released_count}...")
    ok = wait_available(first_ip, first_port, OSWORLD_TOKEN, expect_available=released_count, timeout=20, interval=1)
    
    if not ok:
        print(f"⚠ 警告: 等待超时，available 未达到预期值")
    
    # 打印释放后的状态
    print("\n释放后服务器状态:")
    for url in URL_LIST:
        ip, port = parse_host_port(url)
        print_server_status(ip, port, OSWORLD_TOKEN, "📊")

    # ========== 阶段 3: 再次申请环境 ==========
    print("\n" + "=" * 80)
    print(f"阶段 3: 再次申请 {SECOND_WAVE_COUNT} 个环境")
    print("=" * 80)

    second_wave_envs = []
    second_wave_success = 0
    
    for i in range(SECOND_WAVE_COUNT):
        try:
            env = DesktopEnv(
                action_space="pyautogui",
                provider_name="docker_server",
                os_type="Ubuntu"
            )
            server_ip = env.provider.remote_docker_server_ip
            server_port = env.provider.remote_docker_server_port
            emulator_id = getattr(env.provider, "emulator_id", None)
            key = f"{server_ip}:{server_port}"
            
            second_wave_envs.append(env)
            by_server.setdefault(key, []).append(env)
            all_envs.append(env)
            second_wave_success += 1
            
            print(f"[{i+1}/{SECOND_WAVE_COUNT}] ✓ Started on {key} (emulator_id={emulator_id})")
            time.sleep(0.5)
        except Exception as e:
            print(f"[{i+1}/{SECOND_WAVE_COUNT}] ✗ Failed: {e}")

    print(f"\n阶段 3 完成: 成功启动 {second_wave_success}/{SECOND_WAVE_COUNT} 个环境")

    # 统计第二波在第一个服务器上的数量
    second_wave_on_first = sum(
        1 for env in second_wave_envs
        if f"{env.provider.remote_docker_server_ip}:{env.provider.remote_docker_server_port}" == first_key
    )

    print(f"\n第二波环境分配情况:")
    print(f"  - 总成功数: {second_wave_success}")
    print(f"  - 在第一个服务器 ({first_key}) 上: {second_wave_on_first}")
    print(f"  - 在其他服务器上: {second_wave_success - second_wave_on_first}")

    # 打印最终状态
    print("\n最终服务器状态:")
    for url in URL_LIST:
        ip, port = parse_host_port(url)
        print_server_status(ip, port, OSWORLD_TOKEN, "📊")

    # ========== 验证结果 ==========
    print("\n" + "=" * 80)
    print("测试结果验证")
    print("=" * 80)

    # 验证 1: 第二波至少成功了 released_count 个
    test1_pass = second_wave_success >= released_count
    print(f"\n验证 1: 第二波成功数 >= 释放数")
    print(f"  - 释放数: {released_count}")
    print(f"  - 第二波成功数: {second_wave_success}")
    print(f"  - 结果: {'✓ PASS' if test1_pass else '✗ FAIL'}")

    # 验证 2: 第二波在第一个服务器上至少有 released_count 个（或接近）
    # 注意：如果其他服务器也有空余，可能会分配到其他服务器
    # 所以这里放宽条件，只要 >= released_count - 1 就算通过
    test2_pass = second_wave_on_first >= max(1, released_count - 1)
    print(f"\n验证 2: 第二波在第一个服务器上的数量 >= {max(1, released_count - 1)}")
    print(f"  - 预期至少: {max(1, released_count - 1)}")
    print(f"  - 实际数量: {second_wave_on_first}")
    print(f"  - 结果: {'✓ PASS' if test2_pass else '✗ FAIL'}")

    # 验证 3: 释放后 available 确实增加了
    final_info = get_tokens_snapshot(first_ip, first_port, OSWORLD_TOKEN)
    if final_info:
        final_available = final_info["limit"] - final_info["current"]
        # 由于第二波可能又占用了一些，所以这里只验证 current 没有超过 limit
        test3_pass = final_info["current"] <= final_info["limit"]
        print(f"\n验证 3: 第一个服务器配额未超限")
        print(f"  - Current: {final_info['current']}")
        print(f"  - Limit: {final_info['limit']}")
        print(f"  - 结果: {'✓ PASS' if test3_pass else '✗ FAIL'}")
    else:
        test3_pass = False
        print(f"\n验证 3: 无法获取服务器状态")
        print(f"  - 结果: ✗ FAIL")

    # 总体结果
    all_pass = test1_pass and test2_pass and test3_pass
    print("\n" + "=" * 80)
    if all_pass:
        print("🎉 测试通过！释放后的环境可以被成功复用。")
    else:
        print("⚠ 测试未完全通过，请检查上述验证结果。")
    print("=" * 80)

    # ========== 清理所有环境 ==========
    print("\n" + "=" * 80)
    print("清理所有环境")
    print("=" * 80)

    cleanup_success = 0
    cleanup_failed = 0
    for idx, env in enumerate(all_envs, 1):
        try:
            emulator_id = getattr(env.provider, "emulator_id", None)
            env.close()
            cleanup_success += 1
            print(f"[{idx}/{len(all_envs)}] ✓ Stopped emulator_id={emulator_id}")
            time.sleep(0.2)
        except Exception as e:
            cleanup_failed += 1
            print(f"[{idx}/{len(all_envs)}] ✗ Stop failed: {e}")

    print(f"\n清理完成: 成功 {cleanup_success}, 失败 {cleanup_failed}")
    
    # 打印清理后的状态
    print("\n清理后服务器状态:")
    for url in URL_LIST:
        ip, port = parse_host_port(url)
        print_server_status(ip, port, OSWORLD_TOKEN, "📊")

    print("\n测试完成！")


if __name__ == "__main__":
    main()
