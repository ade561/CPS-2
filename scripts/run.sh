#!/usr/bin/env bash
 
# Anzahl der Elemente definieren
NUM_STORAGES=2
NUM_SUPPLIERS=2
NUM_ROBOTS=4
 
# Netzwerk erstellen
echo "Create network..."
docker network create cps-net
 
# MQTT Broker starten
echo "Starting MQTT Broker..."
docker run -d -p 127.0.0.1:8883:1883 --net=cps-net --name mqttbroker eclipse-mosquitto:1.6.13
 
# Tick Generator starten
echo "Starting Tick Generator..."
docker run -d --net=cps-net --name tick_gen tick_gen:0.1
 
# Dashboard starten
echo "Starting dashboard..."
docker run -d -p 127.0.0.1:1880:1880 --net=cps-net --name dashboard dashboard:0.1
 
# Storages starten
echo "Starting Storages..."
for i in $(seq 1 $NUM_STORAGES); do
  docker run -d --net=cps-net \
    -e EC_NAME="storage/$i" \
    -e EC_MQTT_TOPIC="storage/$i/data" \
    -e CFP_TOPIC="storage/$i/cfp"   \
    -e ROBOTER_PROPOSAL_TOPIC="storage/$i/proposal"\
    -e AWARD_TOPIC="storage/$i/award" \
    --name "storage_$i" storage:0.1
done
 
# Suppliers starten
echo "Starting Suppliers..."
for i in $(seq 1 $NUM_SUPPLIERS); do
  docker run -d --net=cps-net \
    -e EC_NAME="supplier/$i" \
    -e EC_MQTT_TOPIC="supplier/$i/data" \
    -e CFP_TOPIC="supplier/$i/cfp" \
    -e AWARD_TOPIC="supplier/$i/award" \
    --name "supplier_$i" supplier:0.1
done
 
# Roboter starten
echo "Starting Robots..."
for i in $(seq 1 $NUM_ROBOTS); do
  docker run -d --net=cps-net \
    -e EC_NAME="roboter_$i" \
    -e EC_MQTT_TOPIC="roboter/$i/data" \
    -e NUMBER_OF_STORAGES=$NUM_STORAGES \
    -e NUMBER_OF_SUPPLIERS=$NUM_SUPPLIERS \
    -e PROCESSED_TOPIC="roboter/$i/processed" \
    -e CFP_TOPIC="supplier/1/cfp" \
    -e ROBOTER_PROPOSAL_TOPIC="roboter/$i/proposal" \
    -e ROBOTER_REGISTER_TOPIC="roboter/$i/register" \
    -e ROBOTER_REGISTER_CONFIRMATION_TOPIC="roboter/roboter_$i/registerConfirmation" \
    -e ROBOT_STATUS_TOPIC="roboter/roboter_$i/status" \
    --name "roboter_$i" roboter:0.1
done