# OSWorld Remote Docker Simulator Server (Installation & Startup Guide · Recommended)

1.  Create and activate the Conda environment.
2.  Install the project and dependencies (`pip install .`, and install `omegaconf` separately).
3.  Install/Update Docker, pull the image, and configure sudo-less Docker permissions.
4.  Prepare the QCOW2 Virtual Machine image.
5.  Modify `configs/config.yaml` (IP, Port, QCOW2 path, Token concurrency, and Authentication).
6.  Start the service: `python desktop_env/docker_server/server.py`
7.  Run verification in another window: `python env_test.py`
8.  Check the system and simulator status via the Dashboard.

-----

## 1\. Create and Activate Conda Environment

Python 3.10 is recommended:

```bash
conda create -n myenv python=3.10
conda activate myenv
pip install .
pip install omegaconf
pip install desktop_env
```

**Notes:**

  * `pip install .` installs the project based on the current repository.
  * `omegaconf` must be installed separately to satisfy configuration reading dependencies.

-----

## 2\. Install/Update Docker and Pull Image

**Install/Update Docker on Ubuntu:**
(Reference: [Official Docker Installation Script](https://get.docker.com))

```bash
# Download and execute the official Docker installation script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker
```

**Pull the runtime image:**

```bash
sudo docker pull happysixd/osworld-docker
```

**Grant Docker permissions to the current user (Sudo-less access):**

```bash
sudo groupadd docker
sudo gpasswd -a $USER docker
newgrp docker
docker images   # If the image list appears successfully, permissions are active
```

-----

## 3\. Prepare QCOW2 Virtual Machine Image

Using Ubuntu as an example (Note: File size is large, ensure sufficient disk space):

```bash
mkdir -p ~/VMs && cd ~/VMs
wget https://huggingface.co/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
unzip Ubuntu.qcow2.zip  # Extracts Ubuntu.qcow2
```

-----

## 4\. Modify Configuration (`configs/config.yaml`)

Edit `configs/config.yaml` to match your actual environment:

```yaml
remote_docker_server:
  ip: "10.1.110.48"      # Change to your server (or local machine) IP
  port: 50003            # Port, recommended to keep 50003 or customize as needed
  path_to_vm: "/absolute/path/to/Ubuntu.qcow2"  # Change to the actual absolute path of the QCOW2 file

# Token Concurrency Quota Configuration: 
# Key is the token name, Value is the allowed number of concurrent machines
tokens:
  alpha: 24
  enqi: 4

# Authentication Settings
auth:
  require_token: true
  header_name: "Authorization"
  bearer_prefix: "Bearer "
```

**Key Points:**

  * `path_to_vm` must be a valid, existing absolute path to the QCOW2 file; otherwise, the simulator will fail to start.
  * The `tokens` section configures "Valid Token Names" and "Concurrency Limits." The service will enforce quotas based on these settings.

-----

## 5\. Start Service (Window 1)

Execute the following in the repository root directory:

```bash
python desktop_env/docker_server/server.py
```

**Notes:**

  * By default, it listens on `0.0.0.0:50003` (see end of `server.py`).
  * If the image does not exist locally, it will automatically pull `happysixd/osworld-docker` on the first run.
  * The container will mount the QCOW2 file as read-only at `/System.qcow2`. This serves as the system disk for the Guest OS via QEMU inside the container.

-----

## 6\. Verification (Window 2)

Keep the service from the previous step running. Open a new terminal window and execute:

```bash
python env_test.py
```

**`env_test.py` Example (included in repo):**

```python
from desktop_env.desktop_env import DesktopEnv
import os 

# Change these to match the values configured in configs/config.yaml
os.environ["OSWORLD_TOKEN"] = 'enqi'
os.environ["OSWORLD_BASE_URL"] = 'http://10.1.110.48:50003'

env = DesktopEnv(
    action_space="pyautogui",
    provider_name="docker_server",
    os_type='Ubuntu',
)
```

**Important:** Please ensure `OSWORLD_TOKEN` and `OSWORLD_BASE_URL` are updated to match your actual configuration in `configs/config.yaml`.

-----

## 7\. Dashboard and Status APIs

  * **Dashboard:** `http://<ip>:50003/dashboard`
  * **Other Endpoints:**
      * `/status` (Overall CPU/Memory, image container count, current emulator count, tokens overview)
      * `/tokens` (Current usage and limits for each token)
      * `/emulators` (List of currently running emulators)
      * `/emulator_resources` (Brief resource usage for each container)
      * `/request_logs` (Recent request logs)
      * `/set_token_limit` (Dynamically adjust concurrency limits for existing tokens)

-----

## 8\. Common Notes & Troubleshooting

  * **Path Validation:** The `path_to_vm` must be correct and accessible. If the file is missing, the simulator setup will fail.
  * **Token Requirement:** If `require_token: true` is set, all requests must provide a valid token.
  * **Docker Permissions:** After configuring the docker group, if you encounter permission errors, try logging out and back in, or run `newgrp docker` again.
  * **Hardware Resources:** The server host requires sufficient CPU, Memory, and Disk resources. If `/dev/kvm` is available, KVM acceleration can be enabled for better performance.

-----

## 9\. License

Please refer to the `LICENSE` file in the repository.

-----

**Would you like me to create a shell script to automate the installation steps (1-3) for you?**
