# OSWorld 桌面环境服务器（VM/本机）部署与运行指南

本指南基于 `desktop_env/server` 目录的实现，说明如何在 Ubuntu 桌面环境中部署并启动 OSWorld 桌面环境服务器（Flask 服务），以及如何从网络下载并配置 QCOW 虚拟机镜像以配合远程 Docker/云端环境使用。内容包含：
- 环境配置（系统与依赖、AT-SPI 可访问性支持）
- 如何启动（systemd 服务与直接启动）
- 需要修改的配置项（服务单元文件、配置文件、Chrome Debug 端口等）
- 下载与配置 QCOW 镜像（HuggingFace 链接）

如需详细的 Ubuntu 桌面与 VNC/noVNC 图形访问配置，可参考：`desktop_env/server/README.md`。

## 目录定位

- 核心服务代码：`desktop_env/server/main.py`（Flask，默认监听 `0.0.0.0:5000`）
- 服务单元文件：`desktop_env/server/osworld_server.service`
- Python 依赖：`desktop_env/server/requirements.txt`
- 远程 Docker 服务配置：`configs/config.yaml`
- QCOW 镜像 URL（参考）：
  - Ubuntu: https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
  - Windows: https://huggingface.co/datasets/xlangai/windows_osworld/resolve/main/Windows-10-x64.qcow2.zip

---

## 一、系统环境准备（Ubuntu 桌面）

1) 安装 GNOME 桌面（若为最小系统）
```
sudo apt update
sudo apt install -y ubuntu-desktop
sudo systemctl set-default graphical.target
```

2) 账号与自动登录
- 示例用户名：`user`，密码：`password`（可自定义，但需与后续服务文件保持一致）。
- GUI 开启自动登录：Settings -> Users -> Automatic Login（user）
- 或编辑 `/etc/gdm3/custom.conf`，在 `[daemon]` 添加：
```
AutomaticLoginEnable=true
AutomaticLogin=user
```
重启：
```
sudo systemctl restart gdm3
```

3) 使用 Xorg 而非 Wayland
- 退出到登录界面，选择“Ubuntu on Xorg”
- 检查：
```
echo $XDG_SESSION_TYPE  # 输出 x11 即为 Xorg
```

4) 可选：VNC/noVNC 远程可视化
- 安装：
```
sudo apt update && sudo apt install -y x11vnc
sudo snap install novnc
```
- 创建用户级 systemd 服务并开放 5910 端口（详见 `desktop_env/server/README.md`）。

5) 必需/推荐依赖软件
```
sudo apt install -y python3 python3-pip python3-tk python3-dev \
  gnome-screenshot wmctrl ffmpeg socat xclip python3-xlib
```
若系统找不到 python：
```
sudo ln -s /usr/bin/python3 /usr/bin/python
```

6) AT-SPI 可访问性支持（Linux）
- 服务器使用 `pyatspi`（AT-SPI）。推荐通过 apt 安装：
```
sudo apt-get update
sudo apt-get install -y python3-pyatspi
```
- 启用 GNOME 可访问性：
```
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

> 注意：不要将 `pyatspi` 与第三方命名相近的包混淆，优先通过 apt 安装 `python3-pyatspi`。

---

## 二、Python 依赖安装

在仓库根目录执行：
```
pip3 install -r desktop_env/server/requirements.txt
```

`requirements.txt` 主要包含：`flask`、`requests`、`lxml`、`Pillow`、`PyAutoGUI`、`python3-xlib`、`pygame`、`pywinauto` 等。
- 特殊：`pynput` 使用的是一个 PR 分支（Apple Silicon 兼容）
  ```
  git+https://github.com/moses-palmer/pynput.git@refs/pull/541/head
  ```
- 若 `pip` 安装 `python3-xlib==0.15` 报错，可先通过 apt 安装 `python3-xlib`（上文已安装）。如依赖冲突，可临时从本机 `pip` 安装中跳过该行或改用 `python-xlib` 包（注意版本兼容性）。

---

## 三、systemd 服务部署与修改点

目标：开机自动启动 OSWorld 服务器。

1) 放置文件
- 将 `desktop_env/server/main.py` 与 `desktop_env/server/pyxcursor.py` 拷贝到目标目录，例如：`/home/user/server/`
- 如路径或用户名不同，需同步修改服务单元文件中的 `ExecStart`、`WorkingDirectory` 与 `User`

2) 检查与修改服务单元文件  
参考：`desktop_env/server/osworld_server.service`

建议示例（注意 Python3 路径与用户/目录）：
```
[Unit]
Description=osworld service
StartLimitIntervalSec=60
StartLimitBurst=4
After=network.target auditd.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/user/server/main.py
User=user
WorkingDirectory=/home/user
Environment="DISPLAY=:0"
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
Environment="XDG_RUNTIME_DIR=/run/user/1000"
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

修改点说明：
- `ExecStart`：确保 Python 路径与 `main.py` 路径正确（建议使用 `/usr/bin/python3`）
- `User`/`WorkingDirectory`：与实际用户名与目录一致
- `DISPLAY`：若默认 X server 为 `:0`，请保持为 `:0`
- `DBUS_SESSION_BUS_ADDRESS`：用于壁纸等 DBUS 操作
- `XDG_RUNTIME_DIR`：与用户会话一致（通常 `/run/user/1000`）

3) 安装与启用服务
```
sudo cp desktop_env/server/osworld_server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable osworld_server.service
sudo systemctl start osworld_server.service
```

查看状态/排错：
```
sudo systemctl status osworld_server.service
journalctl -xe
```

---

## 四、直接运行（不使用 systemd）

- 在仓库根目录直接运行：
```
python3 desktop_env/server/main.py
```
- 或在包含 `main.py` 的目录中运行（路径按实际调整）。

默认监听 `0.0.0.0:5000`，可通过浏览器或 `curl` 调用 API。

---

## 五、网络端口与远程控制（核心与可选）

建议开放/使用的端口：
- Flask server_port：`5000`
- Chromium remote debugging：`9222`（通常通过 `socat` 从 `1337` 转发）
- noVNC：`5910`
- VLC HTTP：`8080`
- VNC（x11vnc）：`5900`（noVNC 通过 `5910` 转发）

安装 `socat`：
```
sudo apt install -y socat
```

Chrome 远程调试端口（GUI 启动也生效）：
- 修改 `~/.local/share/applications/google-chrome.desktop` 或 `/usr/share/applications/google-chrome.desktop`，将所有 `Exec` 行改为：
```
Exec=/usr/bin/google-chrome-stable --remote-debugging-port=1337 --remote-debugging-address=0.0.0.0 %U
```
- 在 VM 内用 `socat` 将 `1337` -> `9222`（按实际场景转发）。

---

## 六、QCOW 镜像下载与配置（用于 Docker/云端 VM）

1) 下载镜像  
以 Ubuntu 为例（体积较大，确保磁盘空间充足）：
```
mkdir -p ~/VMs && cd ~/VMs
wget https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
unzip Ubuntu.qcow2.zip  # 将得到 Ubuntu.qcow2
```

2) 配置路径（`configs/config.yaml`）  
文件：`configs/config.yaml`
```yaml
remote_docker_server:
  ip: "10.1.110.48"   # 修改为你的远程（或本机）IP
  port: 50003         # 修改为你的远程 Docker server 端口
  path_to_vm: "/absolute/path/to/Ubuntu.qcow2"  # 修改为实际解压出的 qcow2 路径
```

说明：
- `desktop_env/docker_server/server.py` 会从 `configs/config.yaml` 读取 `path_to_vm`：
  ```python
  DEFAULT_VM_PATH = "/home/shichenrui/TongGUI/ubuntu_env/desktop_env/Ubuntu.qcow2"
  PATH_TO_VM = _cfg_get("remote_docker_server.path_to_vm", DEFAULT_VM_PATH)
  ```
  请务必将 `path_to_vm` 改为你的实际绝对路径，避免默认值指向开发者机器路径。

3) 云厂商导入流程（参考）
- Aliyun/火山引擎等：下载并解压后上传到对象存储（OSS/TOS），在控制台执行“导入镜像”。
- 文档参考：
  - `desktop_env/providers/aliyun/ALIYUN_GUIDELINE.md` / `ALIYUN_GUIDELINE_CN.md`
  - `desktop_env/providers/volcengine/VOLCENGINE_GUIDELINE_CN.md`
- Docker 场景：`desktop_env/providers/docker/manager.py` 中 `UBUNTU_X86_URL` 即为上述链接。

---

## 七、API 验证（示例）

服务启动后（默认端口 `5000`）：

- 获取平台：
```
curl http://<VM-IP>:5000/platform
```

- 截图（带鼠标指针）：
```
curl -o screenshot.png http://<VM-IP>:5000/screenshot
```

- 执行命令：
```
curl -X POST http://<VM-IP>:5000/execute -H "Content-Type: application/json" \
  -d '{"command":"gnome-screenshot","shell":false}'
```

- 使用服务端下载器（适合大文件，带重试与完整性校验）：
```
curl -X POST http://<VM-IP>:5000/setup/download_file -H "Content-Type: application/json" \
  -d '{"url":"https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip", "path":"~/VMs/Ubuntu.qcow2.zip"}'
```

---

## 八、常见问题与排查

- 服务无法获取壁纸或 DBUS 错误：  
  确认在服务单元文件设置了
  `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus` 与 `XDG_RUNTIME_DIR=/run/user/1000`，并且存在用户会话。

- AT-SPI 不工作：  
  确认安装了 `python3-pyatspi`；在 GNOME 中启用 `toolkit-accessibility`；使用 Xorg 而非 Wayland。

- Chrome 远程调试端口失效：  
  确保所有桌面条目的 `Exec` 都包含 `--remote-debugging-port=1337 --remote-debugging-address=0.0.0.0`，并使用 `socat` 转发到 `9222`。

- 视频录制（`/start_recording`）失败：  
  确认 `ffmpeg` 已安装，且 `DISPLAY=:0`（与系统 X11 配置一致）。

- systemd 找不到 Python：  
  统一使用 `/usr/bin/python3`，或按需建立符号链接。

- `pip` 安装 `python3-xlib` 报错：  
  使用 `apt` 安装 `python3-xlib`，并在必要时跳过该行或使用 `python-xlib` 包替代（注意版本兼容性）。

---

## 九、变更点汇总（“要修改哪里”）

- `desktop_env/server/osworld_server.service`：
  - `ExecStart`：`/usr/bin/python3 /home/<你的用户名>/server/main.py`
  - `User` / `WorkingDirectory`：替换为你的实际用户名和目录
  - `Environment`：
    - `DISPLAY=:0`
    - `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`
    - `XDG_RUNTIME_DIR=/run/user/1000`

- `configs/config.yaml`：
  - `remote_docker_server.ip`：修改为你的服务器 IP
  - `remote_docker_server.port`：修改为你的端口
  - `remote_docker_server.path_to_vm`：指向你解压后的 `Ubuntu.qcow2` 绝对路径

- Chrome 桌面条目（`/usr/share/applications/google-chrome.desktop` 或用户级路径）：
  - 所有 `Exec` 行添加：`--remote-debugging-port=1337 --remote-debugging-address=0.0.0.0`

---

## 十、许可证

见仓库 `LICENSE` 文件。
