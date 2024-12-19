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
AWARD_TOPIC = "supplier/1/award"  # Thema für Gewinner
PROCESSED_TOPIC = 'roboter/+/processed'  # Thema für Bearbeitungsbestätigungen

# Variablen
supplier_package_type_1 = int(os.environ.get('PACKAGE_TYPE_1_UNIT', 100))
supplier_package_type_2 = int(os.environ.get('PACKAGE_TYPE_2_UNIT', 100))
tick_counter_A = 0
tick_counter_B = 0
valid_priorities = ["leicht", "mittel", "schwer"]
proposals = []  # Liste der empfangenen Angebote

def call_for_proposals(client, cfp_topic, package_type, priority, quantity=1):
    """
    Veröffentlicht eine Call-for-Proposals (CfP)-Anfrage mit benutzerdefinierter Priorität.
    """
    if priority not in valid_priorities:
        logger.warning(f"Ungültige Priorität '{priority}' gesetzt. Standard: 'mittel'")
        priority = "mittel"

    cfp_data = {
        "package_type": package_type,
        "quantity": quantity,
        "priority": priority
    }

    client.publish(cfp_topic, json.dumps(cfp_data))
    logger.info(f"CfP veröffentlicht auf {cfp_topic}: {cfp_data}")

def on_message_proposals(client, userdata, msg):
    global proposals
    try:
        proposal = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"Proposal empfangen: {proposal}")
        proposals.append(proposal)
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren des Proposals: {e}")


def on_processed_message(client, userdata, msg):
    """
    Callback für Bearbeitungsbestätigungen von Robotern.
    Reduziert den Lagerbestand.
    """
    global supplier_package_type_1, supplier_package_type_2
    try:
        processed_data = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"Bearbeitungsbestätigung empfangen: {processed_data}")

        package_type = processed_data.get("package_type")
        if package_type == 1:
            supplier_package_type_1 -= 1
        elif package_type == 2:
            supplier_package_type_2 -= 1

        logger.info(f"Lagerbestand aktualisiert: Typ 1: {supplier_package_type_1}, Typ 2: {supplier_package_type_2}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigungsnachricht: {e}")


def select_winner_and_award(client):
    """
    Wählt den besten Roboter aus den empfangenen Proposals aus und sendet eine Award-Nachricht.
    """
    global proposals


    if not proposals:
        logger.info("Keine Proposals empfangen. Kein Award vergeben.")
        return

    # Wähle den Roboter mit der geringsten geschätzten Bearbeitungszeit
    winner = min(proposals, key=lambda x: x["estimated_time"])
    award_message = {
        "winner": winner["name"],
        "package_type": winner["package_type"],
        "estimated_time": winner["estimated_time"]
    }

    client.publish(AWARD_TOPIC, json.dumps(award_message))
    logger.info(f"Award vergeben an: {award_message}")

    # Leere die Liste der Proposals nach der Vergabe
    proposals = []

def on_message_tick(client, userdata, msg):
    """
    Callback für Tick-Nachrichten. Sendet Anfragen an Roboter, wenn Pakete verfügbar sind.
    """
    global supplier_package_type_1, supplier_package_type_2, tick_counter_A, tick_counter_B, valid_priorities

    ts_iso = msg.payload.decode("utf-8")
    logger.info(f"Tick empfangen mit Timestamp: {ts_iso}")

    random_index = random.randint(0, 2)
    random_package = 1 if random.random() < 0.5 else 2
    weight_class = valid_priorities[random_index]

    if supplier_package_type_1 > 0 and random_package == 1:
        call_for_proposals(client, CFP_TOPIC, 1, weight_class)
    elif supplier_package_type_1 <= 0 and random_package == 1:
        if tick_counter_A >= 10:
            tick_counter_A = 0
            supplier_package_type_1 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 1 geliefert!")
        else:
            tick_counter_A += 1

    if supplier_package_type_2 > 0 and random_package == 2:
        call_for_proposals(client, CFP_TOPIC, 2, weight_class)
    elif supplier_package_type_2 <= 0 and random_package == 2:
        if tick_counter_B >= 10:
            tick_counter_B = 0
            supplier_package_type_2 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 2 geliefert!")
        else:
            tick_counter_B += 1

    select_winner_and_award(client)

    data = {
        "package_type_1": supplier_package_type_1,
        "package_type_2": supplier_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht: {data}")

def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    global TICK_TOPIC, CFP_TOPIC, PROPOSALS_TOPIC

    logger.info(f"Initializing MQTT client with name: {NAME}")
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

    mqtt.subscribe(PROPOSALS_TOPIC)
    mqtt.subscribe_with_callback(PROPOSALS_TOPIC, on_message_proposals)

    mqtt.subscribe(PROCESSED_TOPIC)
    mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_processed_message)

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
