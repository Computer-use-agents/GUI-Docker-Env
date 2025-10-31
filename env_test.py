from desktop_env.desktop_env import DesktopEnv
import os 

os.environ["OSWORLD_TOKEN"] = 'enqi'
os.environ["OSWORLD_BASE_URL"] = 'http://10.1.110.48:50003'
env = DesktopEnv(
            action_space="pyautogui",
            provider_name="docker_server",
            os_type='Ubuntu',
        )



