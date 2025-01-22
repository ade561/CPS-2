import random
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

CFP_TOPIC = os.environ.get('CFP_TOPIC')  # Call-for-Proposals-Thema
ROBOTER_PROPOSAL_TOPIC = 'roboter/+/proposal' # Proposals-Thema
AWARD_TOPIC = os.environ.get('AWARD_TOPIC')  # Thema für Gewinner


mqtt = None
storage_package_type_1 = 0
storage_package_type_2 = 0

storage_package_type_1_entries = []
storage_package_type_2_entries = []

proposals = set()  # Liste der empfangenen Angebote
robot_statuses = {}  # Dictionary, z.B. {"robot_1": "ready", "robot_2": "charging"}
robot_status_topics = []

cfp_flag = False
current_tick = None
adaptive_mode = True
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
        "storage_filled": len(storage_package_type_1_entries) + len(storage_package_type_2_entries)  / storage_size * 100,
        "count_package_type_1": len(storage_package_type_1_entries),
        "count_package_type_2": len(storage_package_type_2_entries)
    }

    client.publish(RECONFIGURE_TOPIC, json.dumps(data))
    logger.info(f"Reconfig-Daten veröffentlicht: {data}")

def on_message_tick(client, userdata, msg):
    global cfp_flag
    ts_iso = msg.payload.decode("utf-8")

    ## PUBLISH DATA ##
    data = {
        "package_type_1_Entries": len(storage_package_type_1_entries),
        "package_type_2_Entries": len(storage_package_type_2_entries),
        "package_type_1": storage_package_type_1,
        "package_type_2": storage_package_type_2,
        "timestamp": ts_iso
    }
    client.publish(DATA_TOPIC, json.dumps(data))
    logger.info(f"Bestand veröffentlicht (vor Verarbeitung): {data}")
    logger.info(f"Aktuelle Zustände der Roboter {robot_statuses}")

    if robot_status_topics:
        for topic in robot_status_topics:
            client.message_callback_add(topic, on_robot_status)

    if adaptive_mode == True:
        storage_package_type_1_entries.sort(key=lambda x: (x[0] == 2, -x[3], x[1]))
        storage_package_type_2_entries.sort(key=lambda x: (x[0] == 2, -x[3], x[1]))

        # logger.info(f"Aktualisierter Sorted-Entries: TYP 1: {storage_package_type_1_entries}")
        # logger.info(f"Aktualisierter Sorted-Entries: TYP 2: {storage_package_type_2_entries}")

    if not registrated_robots:
        logger.info("Keine Roboter Roboter haben sich registriert. CfPs werden nicht gesendet.")
        return
    
    # Überprüfen, ob mindestens ein Roboter "ready" ist
    if not any(status == "ready" for status in robot_statuses.values()):
        logger.info("Keine verfügbaren Roboter. CfPs werden nicht gesendet.")
        return

    
    if cfp_flag != True:
        if storage_package_type_1 > 0 and storage_package_type_2 <= 0:
            random_package = 1
        elif storage_package_type_1 <= 0 and storage_package_type_2 > 0:
            random_package = 2
        else:
            random_package = 1 if random.random() < 0.5 else 2
        if storage_package_type_1 > 0 and random_package == 1:
            cfp_flag = True
            quantity_first_entry = storage_package_type_1_entries[0][3]
            call_for_proposals(client, CFP_TOPIC, random_package, quantity_first_entry,ts_iso)
        
        elif storage_package_type_2 > 0 and random_package == 2:
            cfp_flag = True
            quantity_seconde_entry = storage_package_type_2_entries[0][3]
            call_for_proposals(client, CFP_TOPIC, random_package, quantity_seconde_entry,ts_iso)

def on_message_robot(client, userdata, msg):
    global storage_package_type_1, storage_package_type_2
    try: 
        processed_data = json.loads(msg.payload.decode("utf-8"))
        transport_type = processed_data.get('transport_type')
        timestamp = processed_data.get('timestamp')
        package_type = processed_data.get('package_type')
        quantity = processed_data.get('quantity')

        # logger.info(f"Empfangene Daten: Transportart: {transport_type}, Zeitstempel: {timestamp}, Pakettyp: {package_type}, Quantity: {quantity}")

        global storage_package_type_1, storage_package_type_2
        if processed_data.get('storage') == NAME and processed_data.get('supplier') not in [None, '']:
            if package_type == 1:
                storage_package_type_1_entries.append([transport_type, timestamp, package_type,quantity])
                storage_package_type_1 = min(100, storage_package_type_1+quantity)
            elif package_type == 2:
                storage_package_type_2_entries.append([transport_type, timestamp, package_type,quantity])
                storage_package_type_2 = min(100,storage_package_type_2+quantity)

        logger.info(f"Aktualisierter Lagerbestand: Typ 1: {storage_package_type_1}, Typ 2: {storage_package_type_2}")


    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Nachricht: {e}")

def on_registration(client, userdata, msg):
    global registrated_robots
    register_data = json.loads(msg.payload.decode("utf-8"))

    # Beispiel: Nehmen wir an, `register_data` enthält eine eindeutige "id" des Roboters.
    robot_id = register_data.get("name")
    robot_status = register_data.get("status")
    target_storage = register_data.get("storage")

    if not robot_id or not robot_status:
        logger.error(f"Ungültige Registrierungsdaten empfangen: {register_data}")
        return

    if target_storage != NAME:
        logger.warning(f"Roboter {robot_id} versucht sich bei falschem Supplier zu registrieren.")
        return

    if robot_id in registrated_robots:
        logger.info(f"Roboter {robot_id} ist bereits registriert. Status wird aktualisiert.")
        return

    logger.info(f"Registrierungsbestätigung an Roboter {robot_id} gesendet.")
    registrated_robots.append(robot_id)
    robot_statuses[robot_id] = robot_status
    logger.info(f"Roboter {robot_id} erfolgreich registriert.")
    logger.info(f"Aktuelle registrierte Roboter: {registrated_robots} : Laenge= {len(registrated_robots)}")

    robot_status_topic = f"roboter/{robot_id}/status"
    client.subscribe(robot_status_topic)
    robot_status_topics.append(robot_status_topic)
    logger.info(f"Subscribed to Robot status Topic: {robot_status_topic}")

def call_for_proposals(client, cfp_topic, package_type, quantity,timestamp):
    global cfp_flag
    """
    Veröffentlicht eine Call-for-Proposals (CfP)-Anfrage mit benutzerdefinierter Priorität.
    """
    cfp_data = {
        "name": NAME,
        "package_type": package_type,
        "quantity": quantity,
        "timestamp": timestamp
    }

    client.publish(cfp_topic, json.dumps(cfp_data))
    cfp_flag = False

def on_robot_status(client, userdata, msg):
    """
    Callback für Ladezustandsnachrichten von Robotern.
    Aktualisiert den Zustand der Roboter.
    """
    global robot_statuses

    try:
        status_data = json.loads(msg.payload.decode("utf-8"))
        robot_name = status_data.get("name")
        status = status_data.get("status")

        if robot_name in registrated_robots:
            if robot_name and status:
                robot_statuses[robot_name] = status
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Ladezustandsnachricht: {e}")

def main():
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)
    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)

    mqtt.subscribe(PROCESSED_TOPIC)
    mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_message_robot)

    mqtt.subscribe(REKONFIG_TIMER_TOPIC)
    mqtt.subscribe_with_callback(REKONFIG_TIMER_TOPIC, on_reconfig_message)
    logger.info(f"{mqtt.name} subscribed to Adaptive Mode Topic: {REKONFIG_TIMER_TOPIC}")

    # mqtt.subscribe(ADAPTIVE_MODE_TOPIC)
    # mqtt.subscribe_with_callback(ADAPTIVE_MODE_TOPIC, on_adaptive_mode)
    # logger.info(f"{mqtt.name} subscribed to Adaptive Mode Topic: {ADAPTIVE_MODE_TOPIC}")

    mqtt.subscribe(ROBOTER_REGISTER_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_REGISTER_TOPIC,on_registration)
    logger.info(f"{mqtt.name} subscribed to Robot register Topic: {ROBOTER_REGISTER_TOPIC}")

    # mqtt.subscribe(ROBOTER_PROPOSAL_TOPIC)
    # mqtt.subscribe_with_callback(ROBOTER_PROPOSAL_TOPIC, on_message_proposals)
    # logger.info(f"{mqtt.name} subscribed to Robot proposal Topic: {ROBOTER_PROPOSAL_TOPIC}")

    # mqtt.subscribe(PROCESSED_TOPIC)
    # mqtt.subscribe_with_callback(PROCESSED_TOPIC, on_processed_message)
    # logger.info(f"{mqtt.name} subscribed to Robot processed Topic: {PROCESSED_TOPIC}")

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