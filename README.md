# OSWorld 远程 Docker 模拟器服务器（安装与启动流程 · 推荐版）

1) 创建并激活 Conda 环境
2) 安装项目与依赖（pip install .，并单独安装 omegaconf）
3) 安装/更新 Docker（参考教程链接），拉取镜像并配置 docker 免 sudo 权限
4) 准备 QCOW2 虚拟机镜像
5) 修改 configs/config.yaml（IP、端口、QCOW2 路径、token 并发与认证）
6) 启动服务：python desktop_env/docker_server/server.py
7) 另一个窗口运行：python env_test.py 验证
8) 通过 Dashboard 查看系统与模拟器状态

— — —

## 1. 创建并激活 Conda 环境

建议 Python 3.10：
```
conda create -n myenv python=3.10
conda activate myenv
pip install .
pip install omegaconf
```

说明：
- `pip install .` 会基于当前仓库安装项目。
- 单独安装 `omegaconf` 以满足配置读取等依赖。

— — —

## 2. 安装/更新 Docker 与镜像拉取

- Ubuntu Docker 安装/更新教程（参考）：  
  https://www.runoob.com/docker/ubuntu-docker-install.html
# 下载并执行Docker官方安装脚本
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 启动Docker服务
sudo systemctl start docker
sudo systemctl enable docker

拉取运行镜像：
```
sudo docker pull happysixd/osworld-docker
```

授予当前用户使用 docker 的权限（免 sudo）：
```
sudo groupadd docker
sudo gpasswd -a $USER docker
newgrp docker
docker images   # 能够成功列出镜像表示权限生效
```

— — —

## 3. 准备 QCOW2 虚拟机镜像

以 Ubuntu 为例（体积较大，注意磁盘空间）：
```
mkdir -p ~/VMs && cd ~/VMs
wget https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
unzip Ubuntu.qcow2.zip  # 得到 Ubuntu.qcow2
```


— — —

## 4. 修改配置（configs/config.yaml）

编辑 `configs/config.yaml`，按实际环境修改：
```yaml
remote_docker_server:
  ip: "10.1.110.48"      # 修改为你的服务器（或本机）IP
  port: 50003            # 端口，建议保持 50003 或按需自定义
  path_to_vm: "/absolute/path/to/Ubuntu.qcow2"  # 修改为实际 QCOW2 绝对路径

# Token 并发配额配置：键为 token 名称，值为允许并发的机器数量
tokens:
  alpha: 24
  enqi: 4

# 认证设置
auth:
  require_token: true
  header_name: "Authorization"
  bearer_prefix: "Bearer "
```

要点：
- `path_to_vm` 必须是存在的 QCOW2 绝对路径，否则无法启动模拟器。
- `tokens` 配置“可使用的 token 名”与“并发机器个数”，服务将按此进行配额控制。

— — —

## 5. 启动服务（窗口 1）

在仓库根目录执行：
```
python desktop_env/docker_server/server.py
```

说明：
- 默认监听 `0.0.0.0:50003`（见 `server.py` 末尾）。
- 如本机未存在镜像，首次启动会自动拉取 `happysixd/osworld-docker`。
- 容器内会以只读方式挂载 QCOW2 为 `/System.qcow2`，由容器内 QEMU 作为来宾 OS 的系统盘。

— — —

## 6. 验证（窗口 2）

保持上一步服务在运行，新开一个终端窗口执行：
```
python env_test.py
```

`env_test.py` 示例（仓库自带）：
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

请将 `OSWORLD_TOKEN` 与 `OSWORLD_BASE_URL` 改为你在 `configs/config.yaml` 中配置的实际值。

— — —

## 7. Dashboard 与状态接口

- Dashboard: `http://<ip>:50003/dashboard`
- 其他接口（名称列举）：  
  - `/status`（总体 CPU/内存、镜像容器数量、当前 emulator 数量、tokens 概览）  
  - `/tokens`（各 token 当前使用量与限制）  
  - `/emulators`（正在运行的 emulator 列表）  
  - `/emulator_resources`（各容器资源使用简要）  
  - `/request_logs`（最近请求日志）  
  - `/set_token_limit`（动态调整已存在 token 的并发上限）

— — —

## 8. 常见注意事项

- `path_to_vm` 路径必须正确且存在，否则启动模拟器会失败。
- 若配置了 `require_token: true`，请求需提供合法 token。
- 完成 docker 组配置后，如遇权限未生效，可重新登录或再次执行 `newgrp docker`。
- 服务器主机需要有足够 CPU/内存/磁盘资源；有 `/dev/kvm` 时可启用 KVM 加速。

— — —

## 9. 许可证

参见仓库 `LICENSE` 文件。
