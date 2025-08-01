#!/bin/sh

echo "Waiting for MySQL Service to start..."
# Control startup and shutdown order in Compose
# ...https://docs.docker.com/compose/startup-order/
# Script from ./wait-for is from:
#...https://github.com/vishnubob/wait-for-it/blob/master/wait-for-it.sh
./wait-for mysql:3306 -s

python uni_hub/manage.py makemigrations
python uni_hub/manage.py migrate

# Explanation for why we should run on 0.0.0.0 instead of 127.0.0.1 as default
# ...https://itecnote.com/tecnote/docker-app-server-ip-address-127-0-0-1-difference-of-0-0-0-0-ip/
python uni_hub/manage.py runserver 0.0.0.0:8000