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

echo "Starting Storage_1"
docker run -d --net=cps-net \
  -e EC_NAME='storage_1' \
  -e EC_MQTT_TOPIC='storage/1/data' \
  -e PACKET_TYPE_1_COUNT=0 \
  -e PACKET_TYPE_2_COUNT=0 \
  --name storage_1 storage:0.1

echo "Starting Supplier_1"
docker run -d --net=cps-net \
  -e EC_NAME='supplier_1' \
  -e EC_MQTT_TOPIC='supplier/1/data' \
  -e PACKET_TYPE_1_UNIT=100 \
  -e PACKET_TYPE_2_UNIT=100 \
  --name supplier_1 supplier:0.1

echo "Starting Roboter_1 Type A"
docker run -d --net=cps-net \
  -e EC_NAME='roboter_1' \
  -e EC_MQTT_TOPIC='roboter/1/status' \
  -e ROBOTER_1_REQUEST_TOPIC='roboter/1/request' \
  -e ROBOTER_1_PROCESSED_TOPIC='roboter/1/processed' \
  -e ROBOTER_STATUS='ready' \
  --name roboter_1 roboter:0.1

echo "Starting Roboter_2 Type B"
docker run -d --net=cps-net \
  -e EC_NAME='roboter_2' \
  -e EC_MQTT_TOPIC='roboter/2/status' \
  -e ROBOTER_2_REQUEST_TOPIC='roboter/2/request' \
  -e ROBOTER_2_PROCESSED_TOPIC='roboter/2/processed' \
  -e ROBOTER_STATUS='ready' \
  --name roboter_2 roboter:0.1


echo "Starting Roboter_3 Type Super"
docker run -d --net=cps-net \
  -e EC_NAME='roboter_3' \
  -e EC_MQTT_TOPIC='roboter/3/status' \
  -e ROBOTER_3_REQUEST_TOPIC='roboter/3/request' \
  -e ROBOTER_3_PROCESSED_TOPIC='roboter/3/processed' \
  -e ROBOTER_STATUS='ready' \
  --name roboter_3 roboter:0.1