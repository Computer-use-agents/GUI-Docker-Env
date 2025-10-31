print("Enter script")
from desktop_env.desktop_env import DesktopEnv

example = {
    "id": "94d95f96-9699-4208-98ba-3c3119edf9c2",
    "instruction": "I want to install Spotify on my current system. Could you please help me?",
    "config": [
        {
            "type": "execute",
            "parameters": {
                "command": [
                    "python",
                    "-c",
                    "import pyautogui; import time; pyautogui.click(960, 540); time.sleep(0.5);"
                ]
            }
        }
    ],
    "evaluator": {
        "func": "check_include_exclude",
        "result": {
            "type": "vm_command_line",
            "command": "which spotify"
        },
        "expected": {
            "type": "rule",
            "rules": {
                "include": ["spotify"],
                "exclude": ["not found"]
            }
        }
    }
}
print("Init env")
env = DesktopEnv(
    action_space="pyautogui",
    provider_name="docker_server",
    os_type="Ubuntu",
)
print("Reset env")
obs = env.reset(task_config=example)
print("Step env")
obs, reward, done, info = env.step("pyautogui.rightClick()")

print(obs.keys())
print(reward)
print(done)
print(info)


print("Save screenshot")
# this is a base64 encoded image, decode it to a normal image
with open("screenshot.png", "wb") as _f:
    _f.write(obs["screenshot"])
print(f"View UI in browser: http://10.1.110.48:{env.provider.vnc_port}/")
env.close()
# comment this line if you want to keep the emulator running, so that you can view it in the browser or reuse it
# env.close()