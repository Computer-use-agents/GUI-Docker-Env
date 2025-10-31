# start os-world server
sudo groupadd docker 
sudo gpasswd -a shichenrui docker
source activate tonggui
python desktop_env/docker_server/server.py 
