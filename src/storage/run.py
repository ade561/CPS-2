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

NAME = os.environ.get('EC_NAME')
ADAPTIVE_MODE_TOPIC = os.environ.get('ADAPTIVE_MODE_TOPIC', 'mgmt/adaptive_mode')
DATA_TOPIC = os.environ.get('EC_MQTT_TOPIC', 'storage/1/data')
PROCESSED_TOPIC = 'roboter/+/processed'  # Thema für Bearbeitungsbestätigungen
ROBOTER_REGISTER_TOPIC='roboter/+/register'
COUNT_ROBOTS_STORAGE = os.environ.get('COUNT_ROBOTS_STORAGE', 1)
TICK_TOPIC = "tickgen/tick"
REKONFIG_TIMER_TOPIC = "rekonfig/time"
RECONFIGURE_TOPIC = NAME + "/reconfigure"

mqtt = None
storage_package_type_1 = []
storage_package_type_2 = []
adaptive_mode = False
registrated_robots = []  # Ändern von Set zu Liste
storage_size = 300


def on_adaptive_mode(client, userdata, msg):
    global adaptive_mode
    try:
        message = msg.payload.decode("utf-8").strip().lower()
        if message == 'true':
            adaptive_mode = True
        elif message == 'false':
            adaptive_mode = False
        else:
            logger.warning(f"Ungültige Nachricht für den adaptiven Modus empfangen: {message}")
        logger.info(f"Adaptiver Modus gesetzt auf: {adaptive_mode}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Nachricht für den adaptiven Modus: {e}")

def on_reconfig_message(client, userdata, msg):
    global registrated_robots, storage_package_type_1, storage_package_type_2, NAME

    data = {
        "name": NAME,
        "count_robots": len(registrated_robots),
        "registered_robots": registrated_robots,
        "storage_filled": len(storage_package_type_1) + len(storage_package_type_2)  / storage_size * 100,
        "count_package_type_1": len(storage_package_type_1),
        "count_package_type_2": len(storage_package_type_2)
    }

    client.publish(RECONFIGURE_TOPIC, json.dumps(data))
    logger.info(f"Reconfig-Daten veröffentlicht: {data}")

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
        quantity = processed_data.get('quantity')

        logger.info(f"Empfangene Daten: Transportart: {transport_type}, Zeitstempel: {timestamp}, Pakettyp: {package_type}")

        global storage_package_type_1, storage_package_type_2
        if processed_data.get('storage') == NAME and processed_data.get('supplier') not in [None, '']:
            if package_type == 1:
                storage_package_type_1.append([transport_type, timestamp, package_type,quantity])
            elif package_type == 2:
                storage_package_type_2.append([transport_type, timestamp, package_type,quantity])

        logger.info(f"Aktualisierter Lagerbestand: Typ 1: {storage_package_type_1}, Typ 2: {storage_package_type_2}")

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Nachricht: {e}")

        logger.info(f"Aktualisierter Lagerbestand: Typ 1: {storage_package_type_1}, Typ 2: {storage_package_type_2}")

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Nachricht: {e}")


def on_registration(client, userdata, msg):
    global registrated_robots
    register_data = json.loads(msg.payload.decode("utf-8"))

    # Beispiel: Nehmen wir an, `register_data` enthält eine eindeutige "id" des Roboters.
    robot_id = register_data.get("name")

    if robot_id and register_data.get("storage") == NAME:
        if robot_id not in registrated_robots:
            registrated_robots.append(robot_id)  # Nur die ID hinzufügen
            logger.info(f"Roboter mit ID: {robot_id} hat sich registriert!")
        else:
            logger.info(f"Roboter mit ID: {robot_id} ist bereits registriert.")
    elif robot_id and register_data.get("storage") != NAME:
        if robot_id in registrated_robots:
            registrated_robots.remove(robot_id)
            logger.warning(f"Roboter mit ID: {robot_id} wurde entfernt, da der Lieferant nicht übereinstimmt.")
        else:
            logger.warning(f"Ungültige Registrierungsdaten empfangen: {register_data}")

    logger.info(f"aktuelle registrierte Roboter: {registrated_robots} : Laenge= {len(registrated_robots)}")


def main():
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)
    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

    mqtt.subscribe(PROCESSED_TOPIC)
    mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_message_robot)

    mqtt.subscribe(REKONFIG_TIMER_TOPIC)
    mqtt.subscribe_with_callback(REKONFIG_TIMER_TOPIC, on_reconfig_message)
    logger.info(f"{mqtt.name} subscribed to Adaptive Mode Topic: {REKONFIG_TIMER_TOPIC}")

    mqtt.subscribe(ADAPTIVE_MODE_TOPIC)
    mqtt.subscribe_with_callback(ADAPTIVE_MODE_TOPIC, on_adaptive_mode)
    logger.info(f"{mqtt.name} subscribed to Adaptive Mode Topic: {ADAPTIVE_MODE_TOPIC}")

    mqtt.subscribe(ROBOTER_REGISTER_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_REGISTER_TOPIC,on_registration)
    logger.info(f"{mqtt.name} subscribed to Robot register Topic: {ROBOTER_REGISTER_TOPIC}")

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