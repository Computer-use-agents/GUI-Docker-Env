"""
并发竞态条件测试脚本
测试场景：配额 limit=2，先启动 1 个，然后并发启动 2 个
预期结果：只有 1 个并发请求成功，另一个被拒绝（429）
"""
import os
import time
import threading
from desktop_env.desktop_env import DesktopEnv
import requests

# 配置测试参数
os.environ["OSWORLD_BASE_URL"] = "http://10.1.110.48:50003"
os.environ["OSWORLD_TOKEN"] = "dart"

TOKEN = os.environ["OSWORLD_TOKEN"]
BASE_URL = os.environ["OSWORLD_BASE_URL"]
SERVER_URL = BASE_URL.split(',')[0].strip()

print("=" * 80)
print("并发竞态条件测试")
print("=" * 80)
print(f"Token: {TOKEN}")
print(f"Server: {SERVER_URL}")
print(f"配额限制: 2")
print(f"测试场景:")
print(f"  1. 先启动 1 个环境 (current=1)")
print(f"  2. 并发启动 2 个环境 (应该只有 1 个成功)")
print(f"  3. 验证最终 current=2，没有超配")
print("=" * 80)
print()

# 存储测试结果
environments = []
results = {
    "env1": {"success": False, "error": None},
    "concurrent_env2": {"success": False, "error": None},
    "concurrent_env3": {"success": False, "error": None}
}

def check_quota():
    """查询当前配额使用情况"""
    try:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        resp = requests.get(f"{SERVER_URL}/tokens", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if TOKEN in data:
                return data[TOKEN]
    except Exception as e:
        print(f"  ⚠ 查询配额失败: {e}")
    return None

def start_env(name, result_key, delay=0):
    """启动环境的线程函数"""
    if delay > 0:
        time.sleep(delay)
    
    print(f"\n[{name}] 开始启动...")
    try:
        env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type="Ubuntu",
        )
        
        emulator_id = getattr(env.provider, "emulator_id", None)
        print(f"[{name}] ✓ 启动成功")
        print(f"  - Emulator ID: {emulator_id}")
        print(f"  - Server Port: {env.provider.server_port}")
        
        environments.append(env)
        results[result_key]["success"] = True
        
    except RuntimeError as e:
        error_msg = str(e)
        print(f"[{name}] ✗ 启动失败")
        print(f"  - 错误: {error_msg}")
        results[result_key]["error"] = error_msg
        
        # 检查是否是配额超额错误
        if "quota exceeded" in error_msg.lower() or "429" in error_msg:
            print(f"  - 原因: 配额限制生效 ✓")
        
    except Exception as e:
        print(f"[{name}] ✗ 启动失败（意外错误）")
        print(f"  - 错误类型: {type(e).__name__}")
        print(f"  - 错误: {e}")
        results[result_key]["error"] = str(e)

# 步骤 1：启动第一个环境
print("\n" + "=" * 60)
print("步骤 1: 启动第一个环境")
print("=" * 60)

quota_before = check_quota()
if quota_before:
    print(f"启动前配额: {quota_before['current']}/{quota_before['limit']}")

start_env("环境1", "env1")

quota_after_1 = check_quota()
if quota_after_1:
    print(f"\n启动后配额: {quota_after_1['current']}/{quota_after_1['limit']}")

time.sleep(2)  # 等待环境完全启动

# 步骤 2：并发启动两个环境
print("\n" + "=" * 60)
print("步骤 2: 并发启动两个环境（测试竞态条件）")
print("=" * 60)

quota_before_concurrent = check_quota()
if quota_before_concurrent:
    print(f"并发启动前配额: {quota_before_concurrent['current']}/{quota_before_concurrent['limit']}")

print("\n开始并发启动...")

# 创建两个线程，几乎同时启动
thread2 = threading.Thread(target=start_env, args=("并发环境2", "concurrent_env2"))
thread3 = threading.Thread(target=start_env, args=("并发环境3", "concurrent_env3"))

# 同时启动两个线程
thread2.start()
thread3.start()

# 等待两个线程完成
thread2.join()
thread3.join()

time.sleep(2)  # 等待服务器状态稳定

quota_after_concurrent = check_quota()
if quota_after_concurrent:
    print(f"\n并发启动后配额: {quota_after_concurrent['current']}/{quota_after_concurrent['limit']}")

# 步骤 3：验证结果
print("\n" + "=" * 80)
print("测试结果验证")
print("=" * 80)

success_count = sum(1 for r in results.values() if r["success"])
failure_count = sum(1 for r in results.values() if not r["success"])

print(f"\n启动结果:")
print(f"  - 环境1: {'✓ 成功' if results['env1']['success'] else '✗ 失败'}")
print(f"  - 并发环境2: {'✓ 成功' if results['concurrent_env2']['success'] else '✗ 失败'}")
print(f"  - 并发环境3: {'✓ 成功' if results['concurrent_env3']['success'] else '✗ 失败'}")
print(f"\n总计: 成功 {success_count} 个，失败 {failure_count} 个")

# 验证是否符合预期
print(f"\n配额验证:")
expected_success = 2  # 环境1 + 并发环境2或3之一
expected_failure = 1  # 并发环境2或3之一

if success_count == expected_success and failure_count == expected_failure:
    print(f"✓ 测试通过！配额限制正常工作")
    print(f"  - 成功启动 {expected_success} 个环境（符合 limit=2）")
    print(f"  - 正确拒绝了 {expected_failure} 个超额请求")
    
    # 检查是否有超配
    if quota_after_concurrent and quota_after_concurrent['current'] == 2:
        print(f"✓ 没有超配！最终配额 current=2")
    elif quota_after_concurrent and quota_after_concurrent['current'] > 2:
        print(f"✗ 检测到超配！最终配额 current={quota_after_concurrent['current']} > limit=2")
    
else:
    print(f"✗ 测试失败！配额限制可能存在问题")
    print(f"  - 预期: 成功 {expected_success} 个，失败 {expected_failure} 个")
    print(f"  - 实际: 成功 {success_count} 个，失败 {failure_count} 个")
    
    if success_count > expected_success:
        print(f"  ⚠ 可能存在超配问题！")

# 清理环境
print("\n" + "=" * 60)
print("清理环境")
print("=" * 60)

for idx, env in enumerate(environments, 1):
    try:
        emulator_id = getattr(env.provider, "emulator_id", None)
        print(f"[{idx}/{len(environments)}] 停止环境 {emulator_id}...")
        env.close()
        print(f"  ✓ 已停止")
        time.sleep(0.5)
    except Exception as e:
        print(f"  ✗ 停止失败: {e}")

# 最终配额检查
time.sleep(2)
final_quota = check_quota()
if final_quota:
    print(f"\n清理后配额: {final_quota['current']}/{final_quota['limit']}")
    if final_quota['current'] == 0:
        print(f"✓ 配额已正确释放")
    else:
        print(f"⚠ 配额未完全释放，可能有环境未正确停止")

print(f"\n测试完成！")
