#!/usr/bin/env bash

echo "Stopping containers..."
docker stop dashboard
docker stop roboter_1
docker stop roboter_2
docker stop roboter_3
docker stop storage_1
docker stop supplier_1
docker stop tick_gen
docker stop mqttbroker

echo -e "\nRemoving containers and network...\n"
docker rm dashboard
docker rm roboter_1
docker rm roboter_2
docker rm roboter_3
docker rm storage_1
docker rm supplier_1
docker rm tick_gen
docker rm mqttbroker
docker network rm cps-net
