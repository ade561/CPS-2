#!/usr/bin/env bash
echo "Create network..."
docker network create cps-net

echo "Starting MQTT Broker..."
docker run -d -p 127.0.0.1:8883:1883 --net=cps-net --name mqttbroker \
  eclipse-mosquitto:1.6.13

echo "Starting Tick Generator..."
docker run -d --net=cps-net --name tick_gen tick_gen:0.1

echo "Starting dashboard..."
docker run -d -p 127.0.0.1:1880:1880 --net=cps-net --name dashboard dashboard:0.1

# echo "Starting Storage_1"
# docker run -d --net=cps-net \
#   -e EC_NAME='storage_1' \
#   -e EC_MQTT_TOPIC='storage/1/data' \
#   -e STORAGE_REQUEST_TOPIC='storage/1/request' \
#   -e PACKAGE_TYPE_1_COUNT=0 \
#   -e PACKAGE_TYPE_2_COUNT=0 \
#   --name storage_1 storage:0.1

echo "Starting Supplier_1"
docker run -d --net=cps-net \
  -e EC_NAME='supplier_1' \
  -e EC_MQTT_TOPIC='supplier/1/data' \
  -e SUPPLIER_REQUEST_TOPIC='supplier/1/request' \
  -e PACKAGE_TYPE_1_UNIT=100 \
  -e PACKAGE_TYPE_2_UNIT=100 \
  --name supplier_1 supplier:0.1

# echo "Starting Robots"
# docker run -d --net=cps-net \
#   -e EC_NAME='roboter_1' \
#   -e EC_MQTT_TOPIC='roboter/1/data' \
#   -e PROCESSED_TOPIC='roboter/1/processed' \
#   -e ROBOTER_TYPE=1 \
#   --name roboter_1 roboter:0.1

# docker run -d --net=cps-net \
#   -e EC_NAME='roboter_2' \
#   -e EC_MQTT_TOPIC='roboter/2/data' \
#   -e PROCESSED_TOPIC='roboter/2/processed' \
#   -e ROBOTER_TYPE=2 \
#   --name roboter_2 roboter:0.1

# docker run -d --net=cps-net \
#   -e EC_NAME='roboter_3' \
#   -e EC_MQTT_TOPIC='roboter/3/data' \
#   -e PROCESSED_TOPIC='roboter/3/processed' \
#   -e ROBOTER_TYPE=1 \
#   --name roboter_3 roboter:0.1

# docker run -d --net=cps-net \
#   -e EC_NAME='roboter_4' \
#   -e EC_MQTT_TOPIC='roboter/4/data' \
#   -e PROCESSED_TOPIC='roboter/4/processed' \
#   -e ROBOTER_TYPE=2 \
#   --name roboter_4 roboter:0.1
