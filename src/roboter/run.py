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
SUPPLIER_TYPE_1_REQUEST_TOPIC = 'roboter/1/request'
SUPPLIER_TYPE_2_REQUEST_TOPIC = 'roboter/2/request'

PROCESSED_TYPE_1_TOPIC = 'roboter/1/processed'
PROCESSED_TYPE_2_TOPIC = 'roboter/2/processed'

# Variables
roboter_status = os.environ.get('ROBOTER_STATUS')

def set_status(client, status):
    """
    Ändert den Status des Roboters und veröffentlicht ihn.
    """
    global roboter_status
    roboter_status = status
    client.publish(DATA_TOPIC, json.dumps({"name": NAME, "status": status}))
    logger.info(f"Status geändert auf: {status}")


def process_package(client, package_type):
    """
    Simuliert die Verarbeitung eines Pakets und sendet eine Bestätigung.
    """
    try:
        if package_type == 1 and NAME == "roboter_1" or NAME == "roboter_2":
            logger.info(f"Beginne Verarbeitung von Paket Typ {package_type}.")
            set_status(client, "running")
            time.sleep(5)  # Simuliere Verarbeitung
            logger.info(f"geschlafen fuer 3 Sekunden")
            logger.info(f"Paket Typ {package_type} verarbeitet.")
            # Sende Bestätigung
            client.publish(PROCESSED_TYPE_1_TOPIC, json.dumps({"package_type": package_type}))
            logger.info(f"Bestätigung für Paket Typ {package_type} gesendet.")

        if package_type == 2 and NAME == "roboter_1" or NAME == "roboter_2":
            logger.info(f"Beginne Verarbeitung von Paket Typ {package_type}.")
            set_status(client, "running")
            time.sleep(4)  # Simuliere Verarbeitung
            logger.info(f"geschlafen fuer 4 Sekunden")
            logger.info(f"Paket Typ {package_type} verarbeitet.")
            # Sende Bestätigung
            client.publish(PROCESSED_TYPE_2_TOPIC, json.dumps({"package_type": package_type}))
            logger.info(f"Bestätigung für Paket Typ {package_type} gesendet.")

    except Exception as e:
        logger.error(f"Fehler bei der Verarbeitung: {e}")
    finally:
        set_status(client, "ready")

def on_supplier_message(client, userdata, msg):
    """
    Callback für Nachrichten vom Supplier.
    Verarbeitet die Anfragen basierend auf dem Pakettyp und Roboter-Name.
    """
    global roboter_status

    if roboter_status != "ready":
        logger.warning(f"{client} ist beschäftigt und kann keine weiteren Anfragen bearbeiten.")
        return

    try:
        message = json.loads(msg.payload.decode("utf-8"))
        requested_package_type = message.get("package_type", "unknown")
        logger.info(f"Nachricht vom Supplier empfangen: {message}")

        # Roboter 1 bearbeitet nur Paket Typ 1
        if NAME == "roboter_1" and requested_package_type == 1:
            process_package(client, requested_package_type)
        # Roboter 2 bearbeitet nur Paket Typ 2
        elif NAME == "roboter_2" and requested_package_type == 2:
            process_package(client, requested_package_type)
        else:
            logger.warning(f"{client} ignoriert Paket Typ {requested_package_type}")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Fehler beim Verarbeiten der Nachricht: {e}")


def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")
    logger.info(f"Publishing Roboter data to topic: {DATA_TOPIC}")

    # MQTT-Client mit userdata initialisieren
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    # Subscriptions für die entsprechenden Roboter
    if mqtt.name == "roboter_1":
        mqtt.subscribe(SUPPLIER_TYPE_1_REQUEST_TOPIC)
        mqtt.subscribe_with_callback(SUPPLIER_TYPE_1_REQUEST_TOPIC, on_supplier_message)
        logger.info(f"{mqtt.name} subscribed to {SUPPLIER_TYPE_1_REQUEST_TOPIC}")
    elif mqtt.name == "roboter_2":
        mqtt.subscribe(SUPPLIER_TYPE_2_REQUEST_TOPIC)
        mqtt.subscribe_with_callback(SUPPLIER_TYPE_2_REQUEST_TOPIC, on_supplier_message)
        logger.info(f"{mqtt.name} subscribed to {SUPPLIER_TYPE_2_REQUEST_TOPIC}")
    else:
        logger.error(f"Unbekannter Robotername: {mqtt.name}")
        sys.exit(1)

    # Starte die MQTT-Schleife
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
    # Entry point for the script
    main()