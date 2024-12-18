import sys
import json
import logging
import os
import time
import random
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

# Name des Sensors
NAME = os.environ['EC_NAME']

# MQTT Topics aus Umgebungsvariablen
DATA_TOPIC = os.environ['EC_MQTT_TOPIC']
TICK_TOPIC = "tickgen/tick"
CFP_TOPIC = os.environ.get('CFP_TOPIC')  # Call-for-Proposals-Thema
PROPOSALS_TOPIC = os.environ.get('PROPOSALS_TOPIC')  # Proposals-Thema

# Variablen
supplier_package_type_1 = int(os.environ.get('PACKAGE_TYPE_1_UNIT', 100))
supplier_package_type_2 = int(os.environ.get('PACKAGE_TYPE_2_UNIT', 100))
tick_counter_A = 0
tick_counter_B = 0
valid_priorities = ["leicht", "mittel", "schwer"]

def call_for_proposals(client, cfp_topic, package_type, priority, quantity=1):
    """
    Veröffentlicht eine Call-for-Proposals (CfP)-Anfrage mit benutzerdefinierter Priorität.
    """
    # Validierung der Priorität
    if priority not in valid_priorities:
        logger.warning(f"Ungültige Priorität '{priority}' gesetzt. Standard: 'mittel'")
        priority = "mittel"

    # Erstelle die CfP-Daten
    cfp_data = {
        "package_type": package_type,
        "quantity": quantity,
        "priority": priority
    }

    # Veröffentliche die CfP auf dem spezifizierten Thema
    client.publish(cfp_topic, json.dumps(cfp_data))
    logger.info(f"CfP veröffentlicht auf {cfp_topic}: {cfp_data}")

def on_message_tick(client, userdata, msg):
    """
    Callback für Tick-Nachrichten. Sendet Anfragen an Roboter, wenn Pakete verfügbar sind.
    """
    global supplier_package_type_1, supplier_package_type_2, tick_counter_A, tick_counter_B, valid_priorities

    ts_iso = msg.payload.decode("utf-8")
    logger.info(f"Tick empfangen mit Timestamp: {ts_iso}")

    # Zufällige Gewichtsklasse und Pakettyp wählen
    random_index = random.randint(0, 2)  # Generiert eine Zahl zwischen 0 und 2 (inklusive)
    random_package = 1 if random.random() < 0.6 else 2  # 60% für 1, 40% für 2
    weight_class = valid_priorities[random_index]

    # Paket-Typ 1: Anfrage oder Nachfüllen
    if supplier_package_type_1 > 0 and random_package == 1:
        call_for_proposals(client, CFP_TOPIC, 1, weight_class)
    elif supplier_package_type_1 <= 0 and random_package == 1:
        if tick_counter_A >= 10:
            tick_counter_A = 0
            supplier_package_type_1 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 1 geliefert!")
        else:
            tick_counter_A += 1

    # Paket-Typ 2: Anfrage oder Nachfüllen
    if supplier_package_type_2 > 0 and random_package == 2:
        call_for_proposals(client, CFP_TOPIC, 2, weight_class)
    elif supplier_package_type_2 <= 0 and random_package == 2:
        if tick_counter_B >= 10:
            tick_counter_B = 0
            supplier_package_type_2 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 2 geliefert!")
        else:
            tick_counter_B += 1

    # Nur aktuelle Bestände veröffentlichen, ohne sie zu ändern
    data = {
        "package_type_1": supplier_package_type_1,
        "package_type_2": supplier_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht (vor Verarbeitung): {data}")

def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    global TICK_TOPIC, CFP_TOPIC, PROPOSALS_TOPIC

    logger.info(f"Initializing MQTT client with name: {NAME}")

    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    # Subscriptions
    mqtt.subscribe(TICK_TOPIC)
    logger.info(f"Subscribing to tick topic: {TICK_TOPIC}")

    # Callback für Ticks hinzufügen
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

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
