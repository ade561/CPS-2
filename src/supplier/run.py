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
ADAPTIVE_MODE_TOPIC = os.environ.get('ADAPTIVE_MODE_TOPIC', 'mgmt/adaptive_mode')
RECONFIGURE_TOPIC = NAME + "/reconfigure"

# Variablen
supplier_package_type_1 = int(os.environ.get('PACKAGE_TYPE_1_UNIT', 100))
supplier_package_type_2 = int(os.environ.get('PACKAGE_TYPE_2_UNIT', 100))
tick_counter_A = 0
tick_counter_B = 0
valid_priorities = ["express", "standard", "post"]
proposals = set()  # Liste der empfangenen Angebote
registrated_robots = []
robot_statuses = {}  # Dictionary, z.B. {"robot_1": "ready", "robot_2": "charging"}
cfp_flag = False
adaptive_mode = False



def on_robot_status(client, userdata, msg):
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
            logger.info(f"Aktuelle Zustände der Roboter {robot_statuses}")
        else:
            logger.warning(f"Ungültige Ladezustandsdaten empfangen: {charging_data}")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Ladezustandsnachricht: {e}")



def call_for_proposals(client, cfp_topic, package_type, quantity,timestamp):
    """
    Veröffentlicht eine Call-for-Proposals (CfP)-Anfrage mit benutzerdefinierter Priorität.
    """
    cfp_data = {
        "package_type": package_type,
        "quantity": quantity,
        "timestamp": timestamp
    }

    client.publish(cfp_topic, json.dumps(cfp_data))
   # logger.info(f"CfP veröffentlicht auf {cfp_topic}: {cfp_data}")

def on_message_proposals(client, userdata, msg):
    global proposals

    try:
        # Proposal empfangen
        proposal = json.loads(msg.payload.decode("utf-8"))

        if proposal.get("place") != NAME:
            logger.info(f"Proposal von {proposal['name']} wird ignoriert (falscher Lieferant).")
            return
        logger.info(f"Proposal empfangen: {proposal}")

        # Erstelle ein Tupel aus den Proposal-Daten
        proposal_tuple = (
            proposal.get("name"),
            proposal.get("transport_type"),
            proposal.get("battery"),
            proposal.get("battery_cost") ,
            proposal.get("estimated_time"),
            proposal.get("package_type")
            )

        # Proposal zum Set hinzufügen
        if proposal_tuple not in proposals:
            proposals.add(proposal_tuple)
            logger.info(f"Proposal hinzugefügt: {proposal_tuple}. Anzahl: {len(proposals)}")
            logger.info(f"aktuelle Proposals : {proposals}")
        else:
            logger.info(f"Proposal von {proposal['name']} wird ignoriert (bereits vorhanden).")

        # Weiterverarbeitung, wenn genügend Proposals empfangen wurden
        ready_robots_count = sum(1 for status in robot_statuses.values() if status == "ready")
        if (not adaptive_mode and len(proposals) >= ready_robots_count) or (adaptive_mode and len(proposals) >= 1):
            package_type = proposal.get("package_type")
            select_winner_and_award(client, package_type)

    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren des Proposals: {e}")
    except Exception as e:
        logger.error(f"Ein unerwarteter Fehler in on_message_proposals: {e}")


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
        if package_type == 1 and supplier_package_type_1 > 0:
            supplier_package_type_1 -= 1
        elif package_type == 2 and supplier_package_type_1 > 0:
            supplier_package_type_2 -= 1

        logger.info(f"Lagerbestand aktualisiert: Typ 1: {supplier_package_type_1}, Typ 2: {supplier_package_type_2}")
    except Exception as e:
        logger.error(f"Fehler beim Verarbeiten der Bestätigungsnachricht: {e}")


def calculate_score(proposal):
    """
    Berechnet den Score für ein Proposal basierend auf gewichteten Kriterien.
    Ein höherer Score bedeutet ein besseres Proposal.
    """
    # Gewichtungen
    transport_weight = 0.25      
    battery_weight = 0.25        
    battery_cost_weight = 0.25    
    estimated_time_weight = 0.25  

    # Berechnung des Scores (alle positiv gewichtet)
    transport_score = transport_weight * int(proposal[1])  # Höherer Transporttyp = besser
    battery_score = battery_weight * proposal[2]           # Höherer Batteriestand = besser
    battery_cost_score = -battery_cost_weight * proposal[3] # Niedrigere Kosten = besser
    estimated_time_score = -estimated_time_weight * proposal[4]  # Kürzere Zeit = besser

    # Gesamtscore
    score = (
        transport_score +
        battery_score +
        battery_cost_score +
        estimated_time_score
    )
    
    return abs(score)



def select_winner_and_award(client,package_type):
    global proposals,cfp_flag

    if not proposals:
        logger.info("Keine Proposals empfangen. Kein Award vergeben.")
        return

    # Gewinner mit dem höchsten Score auswählen
    winner = max(proposals, key=calculate_score)

    award_message = {
        "winner": winner[0],          # Name
        "transport_type": winner[1],  # Versandtyp
        "battery": winner[2],         # Batterie
        "battery_cost": winner[3],    # Batteriekosten
        "estimated_time": winner[4],   # Bearbeitungszeit
        "package_type": package_type,
        "timestamp": time.time()     # Zeitstempel
    }
    client.publish(AWARD_TOPIC, json.dumps(award_message))
    logger.info(f"Award vergeben an: {award_message}\n")
    cfp_flag = False
    # Leere das Set der Proposals nach der Vergabe
    proposals.clear()



def on_message_tick(client, userdata, msg):
    global supplier_package_type_1, supplier_package_type_2, tick_counter_A, tick_counter_B, random_quantity, robot_statuses,cfp_flag

    ts_iso = msg.payload.decode("utf-8")

    # Überprüfen, ob mindestens ein Roboter "ready" ist
    if not any(status == "ready" for status in robot_statuses.values()):
        #logger.info("Keine verfügbaren Roboter. CfPs werden nicht gesendet.")
        return
    
    if supplier_package_type_1 <= 0:
            if tick_counter_A >= 10:
                tick_counter_A = 0
                supplier_package_type_1 = 100
                logger.info(f"Supplier hat neue Pakete vom Typ 1 geliefert!")
            else:
                tick_counter_A += 1

    if supplier_package_type_2 <= 0:
            if tick_counter_B >= 10:
                tick_counter_B = 0
                supplier_package_type_2 = 100
                logger.info(f"Supplier hat neue Pakete vom Typ 2 geliefert!")
            else:
                tick_counter_B += 1

    if cfp_flag != True:
        if supplier_package_type_1 > 0 and supplier_package_type_2 <= 0:
            random_package = 1
        elif supplier_package_type_1 <= 0 and supplier_package_type_2 > 0:
            random_package = 2
        else:
            random_package = 1 if random.random() < 0.5 else 2
        cfp_flag = True
        if supplier_package_type_1 > 0 and random_package == 1:
            random_quantity = random.randint(1, min(4, supplier_package_type_1))
            call_for_proposals(client, CFP_TOPIC, random_package, random_quantity,ts_iso)
        
        elif supplier_package_type_2 > 0 and random_package == 2:
            random_quantity = random.randint(1, min(4, supplier_package_type_2))
            call_for_proposals(client, CFP_TOPIC, random_package, random_quantity,ts_iso)

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

    if robot_id and register_data.get("supplier") == NAME:
        if robot_id not in registrated_robots:
            registrated_robots.append(robot_id)  # Nur die ID hinzufügen
            logger.info(f"Roboter mit ID: {robot_id} hat sich registriert!")
        else:
            logger.info(f"Roboter mit ID: {robot_id} ist bereits registriert.")
    elif robot_id and register_data.get("supplier") != NAME:
        if robot_id in registrated_robots:
            registrated_robots.remove(robot_id)
            logger.warning(f"Roboter mit ID: {robot_id} wurde entfernt, da der Lieferant nicht übereinstimmt.")
        else:
            logger.warning(f"Ungültige Registrierungsdaten empfangen: {register_data}")

    logger.info(f"aktuelle registrierte Roboter: {registrated_robots} : Laenge= {len(registrated_robots)}")


def on_adaptive_mode_message(client, userdata, msg):
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
    mqtt.subscribe_with_callback(ROBOT_STATUS_TOPIC, on_robot_status)
    logger.info(f"{mqtt.name} subscribed to Robot Status Topic: {ROBOT_STATUS_TOPIC}")


    mqtt.subscribe(ROBOTER_PROPOSAL_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_PROPOSAL_TOPIC, on_message_proposals)
    logger.info(f"{mqtt.name} subscribed to Robot proposal Topic: {ROBOTER_PROPOSAL_TOPIC}")

    mqtt.subscribe(PROCESSED_TOPIC)
    mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_processed_message)
    logger.info(f"{mqtt.name} subscribed to Robot processed Topic: {PROCESSED_TOPIC}")

    mqtt.subscribe(ADAPTIVE_MODE_TOPIC)
    mqtt.subscribe_with_callback(ADAPTIVE_MODE_TOPIC, on_adaptive_mode_message)
    logger.info(f"{mqtt.name} subscribed to Adaptive Mode Topic: {ADAPTIVE_MODE_TOPIC}")




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