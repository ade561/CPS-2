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

# Name des Sensors
NAME = os.environ['EC_NAME']

# MQTT-Topic für veröffentlichten Bestand
DATA_TOPIC = os.environ['EC_MQTT_TOPIC']

# Abonnierte MQTT-Topics
TICK_TOPIC = "tickgen/tick"
ROBOTER_1_PROCESS_TOPIC = 'roboter/1/processed'
ROBOTER_2_PROCESS_TOPIC = 'roboter/2/processed'
ROBOTER_3_PROCESS_TOPIC = 'roboter/3/processed'

# Variablen für den Bestand
storage_package_type_1 = int(os.environ.get('PACKET_TYPE_1_UNIT', 0))
storage_package_type_2 = int(os.environ.get('PACKET_TYPE_2_UNIT', 0))


def on_message_tick(client, userdata, msg):
    """
    Callback für Tick-Nachrichten. Sendet Anfragen an Roboter, wenn Pakete verfügbar sind.
    """
    ts_iso = msg.payload.decode("utf-8")
    logger.info(f"Tick empfangen mit Timestamp: {ts_iso}")

    # Nur aktuelle Bestände veröffentlichen, ohne sie zu ändern
    data = {
        "package_type_1": storage_package_type_1,
        "package_type_2": storage_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht (vor Verarbeitung): {data}")

def remove_package_from_storage(client, userdata, msg):
    """
    Callback für Verarbeitungsbestätigungen von Robotern. Aktualisiert den Paketbestand.
    """
    global storage_package_type_1, storage_package_type_2

    try:
        processed_info = json.loads(msg.payload.decode("utf-8"))
        package_type = processed_info.get("package_type", "unknown")
        logger.info(f"Bestätigung vom Roboter empfangen: {processed_info}")

        if package_type == 1:
            storage_package_type_1 -= 1
            logger.info(f"Paket Typ 1 ausgelagert. Neuer Bestand: {storage_package_type_1}")
        elif package_type == 2:
            storage_package_type_2 -= 1
            logger.info(f"Paket Typ 2 ausgelagert. Neuer Bestand: {storage_package_type_2}")
        else:
            logger.warning(f"Unbekannter Pakettyp: {package_type}")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Dekodieren der Nachricht: {e}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigung: {e}")



def store_package(client, userdata, msg):
    """
    Callback für Verarbeitungsbestätigungen von Robotern. Aktualisiert den Paketbestand.
    """
    global storage_package_type_1, storage_package_type_2

    try:
        processed_info = json.loads(msg.payload.decode("utf-8"))
        package_type = processed_info.get("package_type", "unknown")
        logger.info(f"Bestätigung vom Roboter empfangen: {processed_info}")

        if package_type == 1:
            storage_package_type_1 += 1
            logger.info(f"Paket Typ 1 eingelagert. Neuer Bestand: {storage_package_type_1}")
        elif package_type == 2:
            storage_package_type_2 += 1
            logger.info(f"Paket Typ 2 eingelagert. Neuer Bestand: {storage_package_type_2}")
        else:
            logger.warning(f"Unbekannter Pakettyp: {package_type}")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Dekodieren der Nachricht: {e}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigung: {e}")


def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")
    logger.info(f"Publishing storage data to topic: {DATA_TOPIC}")

    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    # Abonniere nur die Verarbeitungsbestätigungen der Roboter

    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

    mqtt.subscribe(ROBOTER_1_PROCESS_TOPIC)
    logger.info(f"Subscribing to processed topic: {ROBOTER_1_PROCESS_TOPIC}")
    mqtt.subscribe_with_callback(ROBOTER_1_PROCESS_TOPIC, store_package)

    mqtt.subscribe(ROBOTER_2_PROCESS_TOPIC)
    logger.info(f"Subscribing to processed topic: {ROBOTER_2_PROCESS_TOPIC}")
    mqtt.subscribe_with_callback(ROBOTER_2_PROCESS_TOPIC, store_package)

    mqtt.subscribe(ROBOTER_3_PROCESS_TOPIC)
    logger.info(f"Subscribing to processed topic: {ROBOTER_3_PROCESS_TOPIC}")
    mqtt.subscribe_with_callback(ROBOTER_3_PROCESS_TOPIC, remove_package_from_storage)

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
