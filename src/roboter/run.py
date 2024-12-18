import sys
import json
import logging
import os
import time
from mqtt.mqtt_wrapper import MQTTWrapper



#name of the Senosr
NAME = os.environ['EC_NAME']

# MQTT topic for publishing sensor data
DATA_TOPIC = os.environ['EC_MQTT_TOPIC']

# MQTT Subscribed TOPICS
CFP_TOPIC = os.environ.get('CFP_TOPIC')  # Neues CfP-Thema aus den Umgebungsvariablen
PROCESSED_TOPIC = os.environ.get('PROCESSED_TOPIC')  # Verarbeitetes Thema für Bestätigungen
TICK_TOPIC = "tickgen/tick"

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,  # Log-Level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Log-Ausgabe auf die Konsole
    ]
)
logger = logging.getLogger(NAME)


def on_cfp_message(client, userdata, msg):
    """
    Callback für CfP-Nachrichten vom Supplier.
    Loggt die empfangenen Nachrichten.
    """
    try:
        cfp_data = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"Empfangene CfP-Daten: {cfp_data}")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der CfP-Nachricht: {e}")


def main():
    global first_connection, roboter_map
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")
    logger.info(f"Publishing Roboter data to topic: {DATA_TOPIC}")


    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    # CfP-Topic abonnieren
    mqtt.subscribe(CFP_TOPIC)
    mqtt.subscribe_with_callback(CFP_TOPIC, on_cfp_message)
    logger.info(f"{mqtt.name} subscribed to CfP-Topic: {CFP_TOPIC}")
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