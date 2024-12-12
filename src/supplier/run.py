import sys
import json
import logging
import os
import time
from mqtt.mqtt_wrapper import MQTTWrapper

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,  # Log-Level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Log-Ausgabe auf die Konsole
    ]
)
logger = logging.getLogger(__name__)

#name of the Senosr
NAME = os.environ['EC_NAME']

# MQTT topic for publishing sensor data
DATA_TOPIC = os.environ['EC_MQTT_TOPIC']

# MQTT Subscribed TOPICS
TICK_TOPIC = "tickgen/tick"
ROBOTER_1_STATUS_TOPIC = 'roboter/1/status'
ROBOTER_2_STATUS_TOPIC = 'roboter/2/status'

ROBOTER_1_PROCESS_TOPIC = 'roboter/1/processed'
ROBOTER_2_PROCESS_TOPIC = 'roboter/2/processed'

ROBOTER_1_REQUEST_TOPIC = 'roboter/1/request'
ROBOTER_2_REQUEST_TOPIC = 'roboter/2/request'


# Variables
supplier_package_type_1 = int(os.environ.get('PACKET_TYPE_1_UNIT', 100))
supplier_package_type_2 = int(os.environ.get('PACKET_TYPE_2_UNIT', 100))


def request_package(client, robot_topic, package_type):
    """
    Sendet eine Anfrage an einen Roboter, um ein Paket abzuholen.
    """
    request_data = {"package_type": package_type, "quantity": 1}
    client.publish(robot_topic, json.dumps(request_data))
    logger.info(f"Anfrage an {robot_topic} gesendet: {request_data}")



def on_message_tick(client, userdata, msg):
    """
    Callback für Tick-Nachrichten. Sendet Anfragen an Roboter, wenn Pakete verfügbar sind.
    """
    global supplier_package_type_1, supplier_package_type_2

    ts_iso = msg.payload.decode("utf-8")
    logger.info(f"Tick empfangen mit Timestamp: {ts_iso}")

    # Anfrage senden, Bestand wird NICHT reduziert
    if supplier_package_type_1 > 0:
        request_package(client, ROBOTER_1_REQUEST_TOPIC, 1)
    else:
        supplier_package_type_1 = 100
        logger.info(f"Supplier hat neue Pakete vom Typ 1 geliefert!")
    if supplier_package_type_2 > 0:
        request_package(client, ROBOTER_2_REQUEST_TOPIC, 2)
    else:
        supplier_package_type_2 = 100
        logger.info(f"Supplier hat neue Pakete vom Typ 2 geliefert!")
    
    # Nur aktuelle Bestände veröffentlichen, ohne sie zu ändern
    data = {
        "package_type_1": supplier_package_type_1,
        "package_type_2": supplier_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht (vor Verarbeitung): {data}")



def on_package_processed(client, userdata, msg):
    """
    Callback für Verarbeitungsbestätigungen von Robotern. Reduziert den Paketbestand.
    """
    global supplier_package_type_1, supplier_package_type_2

    try:
        # Nachricht des Roboters dekodieren
        processed_info = json.loads(msg.payload.decode("utf-8"))
        package_type = processed_info.get("package_type", "unknown")
        logger.info(f"Bestätigung empfangen: {processed_info}")

        # Bestand basierend auf Pakettyp reduzieren
        if package_type == 1 and supplier_package_type_1 > 0:
            supplier_package_type_1 -= 1
            logger.info(f"Bestand Typ 1 reduziert. Verbleibend: {supplier_package_type_1}")
        elif package_type == 2 and supplier_package_type_2 > 0:
            supplier_package_type_2 -= 1
            logger.info(f"Bestand Typ 2 reduziert. Verbleibend: {supplier_package_type_2}")
        else:
            logger.warning(f"Unbekannter oder inkonsistenter Pakettyp: {package_type}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigung: {e}")



def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")

    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    # Subscriptions
    mqtt.subscribe(ROBOTER_1_PROCESS_TOPIC)
    logger.info(f"Subscribing to tick topic: {ROBOTER_1_PROCESS_TOPIC}")

    mqtt.subscribe(ROBOTER_2_PROCESS_TOPIC)
    logger.info(f"Subscribing to tick topic: {ROBOTER_2_PROCESS_TOPIC}")

    mqtt.subscribe(TICK_TOPIC)
    logger.info(f"Subscribing to tick topic: {TICK_TOPIC}")

    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)


    mqtt.subscribe_with_callback(ROBOTER_1_PROCESS_TOPIC, on_package_processed)

    mqtt.subscribe_with_callback(ROBOTER_2_PROCESS_TOPIC, on_package_processed)


    try:
        logger.info("Starting MQTT loop...")
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("KeyboardInterrupt detected, shutting down gracefully.")
        mqtt.stop()
        sys.exit("Shutdown complete.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        mqtt.stop()
        sys.exit(1)

if __name__ == '__main__':
    # Entry point for the script
    main()
