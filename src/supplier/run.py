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
ROBOTER_PROPOSAL_TOPIC = 'roboter/+/proposal' # Proposals-Thema
AWARD_TOPIC = "supplier/1/award"  # Thema für Gewinner
PROCESSED_TOPIC = 'roboter/+/processed'  # Thema für Bearbeitungsbestätigungen
ROBOTER_REGISTER_TOPIC='roboter/+/register'
ROBOT_STATUS_TOPIC='roboter/+/status'

# Variablen
supplier_package_type_1 = int(os.environ.get('PACKAGE_TYPE_1_UNIT', 100))
supplier_package_type_2 = int(os.environ.get('PACKAGE_TYPE_2_UNIT', 100))
tick_counter_A = 0
tick_counter_B = 0
random_quantity = 0
valid_priorities = ["express", "standard", "post"]
proposals = set()  # Liste der empfangenen Angebote
registrated_robots = set()
robot_statuses = {}  # Dictionary, z.B. {"robot_1": "ready", "robot_2": "charging"}



def on_robot_charging_status(client, userdata, msg):
    """
    Callback für Ladezustandsnachrichten von Robotern.
    Aktualisiert den Zustand der Roboter.
    """
    global robot_statuses

    try:
        charging_data = json.loads(msg.payload.decode("utf-8"))
        robot_name = charging_data.get("name")
        status = charging_data.get("status")

        if robot_name and status:
            robot_statuses[robot_name] = status
            logger.info(f"Zustand von {robot_name} aktualisiert: {status}")
        else:
            logger.warning(f"Ungültige Ladezustandsdaten empfangen: {charging_data}")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Ladezustandsnachricht: {e}")



#TODO Proposal sollte sich aus prio, quantity zusammensetzen dass ist der Preis den der Supplier anschaut
def call_for_proposals(client, cfp_topic, package_type, quantity):
    """
    Veröffentlicht eine Call-for-Proposals (CfP)-Anfrage mit benutzerdefinierter Priorität.
    """
    cfp_data = {
        "package_type": package_type,
        "quantity": quantity,
    }

    client.publish(cfp_topic, json.dumps(cfp_data))
   # logger.info(f"CfP veröffentlicht auf {cfp_topic}: {cfp_data}")

def on_message_proposals(client, userdata, msg):
    global proposals

    try:
        # Proposal empfangen
        proposal = json.loads(msg.payload.decode("utf-8"))
       # logger.info(f"Proposal empfangen: {proposal}")

        # Erstelle ein Tupel aus den Proposal-Daten
        proposal_tuple = (proposal["name"], proposal["package_type"], proposal["quantity"])

        # Proposal zum Set hinzufügen
        if proposal_tuple not in proposals:
            proposals.add(proposal_tuple)
           # logger.info(f"Proposal hinzugefügt: {proposal_tuple}. Anzahl: {len(proposals)}")
        else:
            logger.info(f"Proposal von {proposal['name']} wird ignoriert (bereits vorhanden).")

        # Weiterverarbeitung, wenn genügend Proposals empfangen wurden
        if len(proposals) >= sum(1 for status in robot_statuses.values() if status == "ready"):
            select_winner_and_award(client)

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren des Proposals: {e}")
    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler in on_message_proposals: {e}")


def on_processed_message(client, userdata, msg):
    """
    Callback für Bearbeitungsbestätigungen von Robotern.
    Reduziert den Lagerbestand.
    """
    global supplier_package_type_1, supplier_package_type_2,random_quantity
    try:
        processed_data = json.loads(msg.payload.decode("utf-8"))
       # logger.info(f"Bearbeitungsbestätigung empfangen: {processed_data}")
       # logger.info(f"random_quantity: {random_quantity}")

        package_type = processed_data.get("package_type")
        if package_type == 1 and supplier_package_type_1 > 0:
            supplier_package_type_1 -= random_quantity
        elif package_type == 2 and supplier_package_type_1 > 0:
            supplier_package_type_2 -= random_quantity

        #logger.info(f"Lagerbestand aktualisiert: Typ 1: {supplier_package_type_1}, Typ 2: {supplier_package_type_2}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigungsnachricht: {e}")


def select_winner_and_award(client):
    """
    Wählt den besten Roboter aus den empfangenen Proposals aus und sendet eine Award-Nachricht.
    """
    global proposals

    if not proposals:
        #logger.info("Keine Proposals empfangen. Kein Award vergeben.")
        return

    # Wähle den Roboter mit der geringsten geschätzten Bearbeitungszeit
    winner = min(proposals, key=lambda x: x[2])  # Nutze die Position des "estimated_time" Werts im Tupel
    award_message = {
        "winner": winner[0],          # Name
        "package_type": winner[1],    # Pakettyp
        "estimated_time": winner[2]   # Bearbeitungszeit
    }

    client.publish(AWARD_TOPIC, json.dumps(award_message))
   # logger.info(f"Award vergeben an: {award_message}")

    # Leere das Set der Proposals nach der Vergabe
    proposals.clear()


def on_message_tick(client, userdata, msg):
    global supplier_package_type_1, supplier_package_type_2, tick_counter_A, tick_counter_B, random_quantity, robot_statuses

    ts_iso = msg.payload.decode("utf-8")

    # Überprüfen, ob mindestens ein Roboter "ready" ist
    if not any(status == "ready" for status in robot_statuses.values()):
        #logger.info("Keine verfügbaren Roboter. CfPs werden nicht gesendet.")
        return

    random_package = 1 if random.random() < 0.5 else 2

    if supplier_package_type_1 > 0 and random_package == 1:
        random_quantity = random.randint(1, min(4, supplier_package_type_1))
        call_for_proposals(client, CFP_TOPIC, random_package, random_quantity)
    elif supplier_package_type_1 <= 0 and random_package == 1:
        if tick_counter_A >= 10:
            tick_counter_A = 0
            supplier_package_type_1 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 1 geliefert!")
        else:
            tick_counter_A += 1

    if supplier_package_type_2 > 0 and random_package == 2:
        random_quantity = random.randint(1, min(4, supplier_package_type_2))
        call_for_proposals(client, CFP_TOPIC, random_package, random_quantity)
    elif supplier_package_type_2 <= 0 and random_package == 2:
        if tick_counter_B >= 10:
            tick_counter_B = 0
            supplier_package_type_2 = 100
            logger.info(f"Supplier hat neue Pakete vom Typ 2 geliefert!")
        else:
            tick_counter_B += 1

    data = {
        "package_type_1": supplier_package_type_1,
        "package_type_2": supplier_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))


def on_registration(client, userdata, msg):
    global registrated_robots
    register_data = json.loads(msg.payload.decode("utf-8"))

    # Beispiel: Nehmen wir an, `register_data` enthält eine eindeutige "id" des Roboters.
    robot_id = register_data.get("name")
    if robot_id:
        registrated_robots.add(robot_id)  # Nur die ID hinzufügen
        logger.info(f"Roboter mit ID: {robot_id} hat sich registriert!")
    else:
        logger.warning(f"Ungültige Registrierungsdaten empfangen: {register_data}")

    logger.info(f"aktuelle registrierte Roboter: {registrated_robots} : Laenge= {len(registrated_robots)}")


def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    global TICK_TOPIC, CFP_TOPIC, ROBOTER_PROPOSAL_TOPIC

    logger.info(f"Initializing MQTT client with name: {NAME}")
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)

    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)
    logger.info(f"{mqtt.name} subscribed to Robot tick Topic: {TICK_TOPIC}")


    mqtt.subscribe(ROBOTER_REGISTER_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_REGISTER_TOPIC,on_registration)
    logger.info(f"{mqtt.name} subscribed to Robot register Topic: {ROBOTER_REGISTER_TOPIC}")


    mqtt.subscribe(ROBOT_STATUS_TOPIC)
    mqtt.subscribe_with_callback(ROBOT_STATUS_TOPIC, on_robot_charging_status)
    logger.info(f"{mqtt.name} subscribed to Robot Status Topic: {ROBOT_STATUS_TOPIC}")


    mqtt.subscribe(ROBOTER_PROPOSAL_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_PROPOSAL_TOPIC, on_message_proposals)
    logger.info(f"{mqtt.name} subscribed to Robot proposal Topic: {ROBOTER_PROPOSAL_TOPIC}")

    mqtt.subscribe(PROCESSED_TOPIC)
    mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_processed_message)
    logger.info(f"{mqtt.name} subscribed to Robot processed Topic: {PROCESSED_TOPIC}")


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
