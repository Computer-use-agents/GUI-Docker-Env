# OSWorld 远程 Docker 模拟器服务器（简版快速上手）

本指南基于 `desktop_env/docker_server/server.py` 与项目配置，面向“远程 Docker 服务器”场景，提供最小化的使用说明：
- 如何下载并配置 QCOW2 虚拟机镜像
- 如何修改配置（IP、端口、QCOW 路径、token 与并发配额）
- 如何启动服务并用示例脚本验证
- 如何通过 Dashboard 查看当前运行状态

已按要求删除冗长内容（系统环境准备、systemd 服务部署、网络端口与远程控制、API 示例等）。本指南仅保留“需要修改哪里”和“如何启动/查看”的核心信息。

---

## 1. 准备工作

- 服务器主机需安装：
  - Docker（确保 `dockerd` 正常运行）
  - Python 3（建议 3.8+）
- 磁盘空间充足，用于存放 QCOW2 镜像（几个 GB 到几十 GB 不等）

### 下载 QCOW2 镜像（示例）
以 Ubuntu 为例：
```
mkdir -p ~/VMs && cd ~/VMs
wget https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
unzip Ubuntu.qcow2.zip  # 得到 Ubuntu.qcow2
```
如需 Windows 镜像：
- https://huggingface.co/datasets/xlangai/windows_osworld/resolve/main/Windows-10-x64.qcow2.zip

> 说明：镜像体积较大，确保下载与解压空间充足。

---

## 2. 修改配置（“要修改哪里”）

配置文件位置：`configs/config.yaml`。示例内容如下（请按实际环境修改）：
```yaml
remote_docker_server:
  ip: "10.1.110.48"   # 修改为你的服务器（或本机）IP
  port: 50003         # 建议保持 50003，或按需自定义
  path_to_vm: "/absolute/path/to/Ubuntu.qcow2"  # 修改为实际解压出的 qcow2 绝对路径

# Token 并发配额配置：键为 token 名称，值为允许并发的机器数量
tokens:
  alpha: 24
  enqi: 4

# 认证设置：是否需要 token、认证头名称与 Bearer 前缀
auth:
  require_token: true
  header_name: "Authorization"
  bearer_prefix: "Bearer "
```

- `remote_docker_server.ip` 与 `port`：用于对外提供服务，客户端将以 `http://<ip>:<port>` 访问
- `remote_docker_server.path_to_vm`：必须指向你刚解压得到的 QCOW2 文件的绝对路径
- `tokens`：配置“可使用的 token 名”和“每个 token 的并发机器个数”，服务启动后会按此进行配额控制
- `auth`：
  - `require_token: true` 时，所有调用需提供合法 token
  - token 的传递方式：
    - Header：`Authorization: Bearer <token>`
    - 或 JSON body：`{"token": "<token>"}`（部分接口）
    - 或查询字符串：`?token=<token>`

---

## 3. 启动服务

在仓库根目录执行（Linux）：
```
python3 desktop_env/docker_server/server.py
```

- 服务默认监听：`0.0.0.0:50003`（见 `server.py` 末尾）
- 首次启动且镜像未存在时，会自动拉取 Docker 镜像：`happysixd/osworld-docker`
  - QCOW2 将以只读方式挂载到容器 `/System.qcow2`
  - Docker 容器会暴露诸如 `VNC/Chromium/Flask/VLC` 等端口（由内部实现决定），供桌面模拟器与可视化使用

> 注意：服务的行为依赖 Docker 与宿主机能力（如是否有 `/dev/kvm` 以启用 KVM 加速）。只要 `configs/config.yaml` 正确设置 `path_to_vm`，即可拉起相应的模拟器。

---

## 4. 用示例脚本验证（env_test.py）

示例脚本位置：`env_test.py`，内容如下：
```python
from desktop_env.desktop_env import DesktopEnv
import os 

os.environ["OSWORLD_TOKEN"] = 'enqi'
os.environ["OSWORLD_BASE_URL"] = 'http://10.1.110.48:50003'
env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type='Ubuntu',
        )
```

使用方法：
1) 将 `OSWORLD_TOKEN` 修改为你在 `configs/config.yaml` 中配置的合法 token（例如 `enqi`）
2) 将 `OSWORLD_BASE_URL` 修改为你的服务器地址（例如 `http://<ip>:50003`）
3) 运行：
   ```
   python3 env_test.py
   ```
   - 若配额充足且服务正常，该脚本会通过 `docker_server` provider 请求启动一个模拟器（emulator）
   - 失败时，检查 `configs/config.yaml` 中 `path_to_vm` 是否为有效绝对路径、`tokens` 是否包含该 token 且有可用并发额度

---

## 5. Dashboard 与状态查看

服务提供 Dashboard 与若干状态接口，便于可视化与排查：
- Dashboard: `http://<ip>:50003/dashboard`
  - 展示服务器与正在运行的模拟器状态（容器、端口、资源简要等）
- 其他接口（只列名称，避免冗长示例）：
  - `/status`（总体 CPU/内存、镜像容器数量、当前 emulator 数量、tokens 概览）
  - `/tokens`（各 token 当前使用量与限制）
  - `/emulators`（正在运行的 emulator 列表）
  - `/emulator_resources`（各容器资源使用简要）
  - `/request_logs`（最近请求日志）
  - `/set_token_limit`（动态调整已存在 token 的并发上限）

> 动态调整配额：可以在服务运行时调用 `/set_token_limit` 修改现有 token 的并发上限；也可直接编辑 `configs/config.yaml` 后重启服务来生效。

---

## 6. Docker 镜像与 QCOW2 的关系（简述）

- Docker 镜像：`happysixd/osworld-docker`
  - 提供 QEMU 及运行时（以及所需的依赖与工具）
- QCOW2 镜像：你的来宾操作系统系统盘（例如 Ubuntu/Windows）
  - 在启动容器时以只读方式挂载为 `/System.qcow2`
  - 由容器中的 QEMU 挂载并作为来宾 OS 的虚拟磁盘

---

## 7. 常见注意事项

- `path_to_vm` 必须为绝对路径且存在；否则启动模拟器会失败
- 确保 Docker 服务可用，且服务器主机资源足够（CPU/内存/磁盘）
- 若启用了 `require_token`，客户端必须提供合法 token，否则请求会被拒绝
- `configs/config.yaml` 中的 `ip` 与 `port` 用于外部访问，请与实际网络环境保持一致
- 容器端口映射与资源统计由内部实现控制；Dashboard 可帮助观察当前运行状态

---

## 8. 许可证

参见仓库 `LICENSE` 文件。
