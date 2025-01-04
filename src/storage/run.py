import sys
import json
import logging
import os
from mqtt.mqtt_wrapper import MQTTWrapper

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

NAME = os.environ.get('EC_NAME', 'storage_1')
DATA_TOPIC = os.environ.get('EC_MQTT_TOPIC', 'storage/1/data')
ROBOTER_PROCESS_TOPICS = os.environ.get('ROBOTER_PROCESS_TOPICS', 'roboter/1/processed,roboter/2/processed,roboter/3/processed,roboter/4/processed').split(',')
COUNT_ROBOTS_STORAGE = os.environ.get('COUNT_ROBOTS_STORAGE', 1)
TICK_TOPIC = "tickgen/tick"

mqtt = None
storage_package_type_1 = []
storage_package_type_2 = []

def on_message_tick(client, userdata, msg):
    ts_iso = msg.payload.decode("utf-8")
    logger.info(f"Tick empfangen mit Timestamp: {ts_iso}")

    # Nur aktuelle Bestände veröffentlichen, ohne sie zu ändern
    data = {
        "package_type_1": len(storage_package_type_1),
        "package_type_2": len(storage_package_type_2),
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht (vor Verarbeitung): {data}")


def on_message_robot(client, userdata, msg):
    try: 
        processed_data = json.loads(msg.payload.decode("utf-8"))
        transport_type = processed_data.get('transport_type')
        timestamp = processed_data.get('timestamp')
        package_type = processed_data.get('package_type')

        logger.info(f"Empfangene Daten: Transportart: {transport_type}, Zeitstempel: {timestamp}, Pakettyp: {package_type}")

        global storage_package_type_1, storage_package_type_2
        if processed_data.get('storage') == NAME and processed_data.get('supplier') not in [None, '']:
            if package_type == 1:
                storage_package_type_1.append([transport_type, timestamp, package_type])
            elif package_type == 2:
                storage_package_type_2.append([transport_type, timestamp, package_type])

        logger.info(f"Aktualisierter Lagerbestand: Typ 1: {storage_package_type_1}, Typ 2: {storage_package_type_2}")

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Nachricht: {e}")

        logger.info(f"Aktualisierter Lagerbestand: Typ 1: {storage_package_type_1}, Typ 2: {storage_package_type_2}")

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Nachricht: {e}")


def main():
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)
    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

    for topic in ROBOTER_PROCESS_TOPICS:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_robot)

    try:
        logger.info("Starting MQTT loop...")
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("KeyboardInterrupt detected, shutting down gracefully.")
        mqtt.stop()
        sys.exit("Shutdown complete.")
    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler ist aufgetreten: {e}")
        mqtt.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()