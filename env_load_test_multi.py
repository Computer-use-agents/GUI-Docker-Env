"""
多服务器配额限制负载测试脚本
测试 DesktopEnv 在多个服务器之间的轮询和配额限制功能
"""
import os
import time
from desktop_env.desktop_env import DesktopEnv

# 配置测试参数 - 两个服务器URL
os.environ.setdefault("OSWORLD_BASE_URL", "http://10.1.110.48:50003,http://10.1.110.43:50003")
os.environ.setdefault("OSWORLD_TOKEN", "dart")

TOKEN = os.environ.get("OSWORLD_TOKEN")
BASE_URL = os.environ.get("OSWORLD_BASE_URL")
URL_LIST = [url.strip() for url in BASE_URL.split(',')]

# 每个服务器配额10个，共2个服务器
PER_URL_QUOTA = 10
URL_COUNT = len(URL_LIST)
MAX_ATTEMPTS = PER_URL_QUOTA * URL_COUNT  # 20个应该成功
TOTAL_ATTEMPTS = MAX_ATTEMPTS + 2  # 22个尝试（多2个测试失败情况）

print(f"=" * 80)
print(f"多服务器配额限制负载测试")
print(f"=" * 80)
print(f"Token: {TOKEN}")
print(f"服务器列表:")
for idx, url in enumerate(URL_LIST, 1):
    print(f"  {idx}. {url}")
print(f"每个服务器配额: {PER_URL_QUOTA}")
print(f"服务器总数: {URL_COUNT}")
print(f"预期成功启动数量: {MAX_ATTEMPTS} ({PER_URL_QUOTA} × {URL_COUNT})")
print(f"实际尝试启动数量: {TOTAL_ATTEMPTS} (多尝试 2 个)")
print(f"=" * 80)
print()

# 存储成功启动的环境
environments = []
success_count = 0
failure_count = 0
server_usage = {}  # 记录每个服务器启动的环境数量

# 尝试启动多个环境
for i in range(TOTAL_ATTEMPTS):
    print(f"\n[测试 {i+1}/{TOTAL_ATTEMPTS}] 尝试启动第 {i+1} 个环境...")
    
    try:
        env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type="Ubuntu",
        )
        
        # 获取启动的虚拟机信息
        emulator_id = getattr(env.provider, "emulator_id", None)
        server_ip = env.provider.remote_docker_server_ip
        server_port = env.provider.remote_docker_server_port
        server_key = f"{server_ip}:{server_port}"
        
        # 记录服务器使用情况
        server_usage[server_key] = server_usage.get(server_key, 0) + 1
        
        print(f"✓ 成功启动环境 {i+1}")
        print(f"  - Emulator ID: {emulator_id}")
        print(f"  - Server: {server_key}")
        print(f"  - Server Port: {env.provider.server_port}")
        print(f"  - VNC Port: {env.provider.vnc_port}")
        
        environments.append(env)
        success_count += 1
        
        # 短暂延迟，避免请求过快
        time.sleep(1)
        
    except RuntimeError as e:
        error_msg = str(e)
        print(f"✗ 环境 {i+1} 启动失败（预期行为）")
        print(f"  - 错误信息: {error_msg}")
        
        # 检查是否是配额超额错误
        if "quota exceeded" in error_msg.lower() or "超过" in error_msg:
            print(f"  - 原因: 配额限制生效 ✓")
        else:
            print(f"  - 原因: 其他错误")
        
        failure_count += 1
        
    except Exception as e:
        print(f"✗ 环境 {i+1} 启动失败（意外错误）")
        print(f"  - 错误类型: {type(e).__name__}")
        print(f"  - 错误信息: {e}")
        failure_count += 1

# 输出测试结果摘要
print(f"\n" + "=" * 80)
print(f"测试结果摘要")
print(f"=" * 80)
print(f"成功启动: {success_count} 个环境")
print(f"启动失败: {failure_count} 个环境")
print(f"总计尝试: {TOTAL_ATTEMPTS} 次")
print(f"\n服务器使用情况:")
for server, count in sorted(server_usage.items()):
    print(f"  - {server}: {count} 个环境")
print(f"=" * 80)

# 动态计算预期结果
expected_success = MAX_ATTEMPTS
expected_failure = 2

# 验证结果
print(f"\n配额限制验证:")
if success_count == expected_success and failure_count == expected_failure:
    print(f"✓ 配额限制正常工作！")
    print(f"  - 允许启动 {expected_success} 个环境（符合配额限制）")
    print(f"  - 正确拒绝了超额的 {expected_failure} 次启动请求")
else:
    print(f"✗ 配额限制可能存在问题")
    print(f"  - 预期: 成功 {expected_success} 个，失败 {expected_failure} 个")
    print(f"  - 实际: 成功 {success_count} 个，失败 {failure_count} 个")

# 验证服务器轮询
print(f"\n服务器轮询验证:")
all_servers_used = len(server_usage) == URL_COUNT
balanced_distribution = all(count == PER_URL_QUOTA for count in server_usage.values()) if success_count == expected_success else False

if all_servers_used and balanced_distribution:
    print(f"✓ 服务器轮询正常工作！")
    print(f"  - 所有 {URL_COUNT} 个服务器都被使用")
    print(f"  - 每个服务器启动了 {PER_URL_QUOTA} 个环境（均衡分配）")
elif all_servers_used:
    print(f"⚠ 服务器轮询部分正常")
    print(f"  - 所有 {URL_COUNT} 个服务器都被使用")
    print(f"  - 但分配不均衡:")
    for server, count in sorted(server_usage.items()):
        print(f"    • {server}: {count} 个（预期 {PER_URL_QUOTA} 个）")
else:
    print(f"✗ 服务器轮询可能存在问题")
    print(f"  - 只使用了 {len(server_usage)}/{URL_COUNT} 个服务器")
    if server_usage:
        print(f"  - 使用情况:")
        for server, count in sorted(server_usage.items()):
            print(f"    • {server}: {count} 个")

# 清理：停止所有启动的环境
print(f"\n" + "=" * 60)
print(f"清理环境")
print(f"=" * 60)

for idx, env in enumerate(environments, 1):
    try:
        emulator_id = getattr(env.provider, "emulator_id", None)
        print(f"[{idx}/{len(environments)}] 停止环境 {emulator_id}...")
        env.close()
        print(f"  ✓ 已停止")
        time.sleep(0.5)  # 短暂延迟，确保停止操作完成
    except Exception as e:
        print(f"  ✗ 停止失败: {e}")

print(f"\n测试完成！")
