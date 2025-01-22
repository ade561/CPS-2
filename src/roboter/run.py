import sys
import json
import logging
import os
import time
import random
from mqtt.mqtt_wrapper import MQTTWrapper

# Name des Sensors
NAME = os.environ['EC_NAME']

# MQTT Topics
DATA_TOPIC = os.environ['EC_MQTT_TOPIC']
SUPPLIER_CFP_TOPIC = "supplier/+/cfp"  # CfP-Thema
TICK_TOPIC = "tickgen/tick"

ROBOT_PROPOSAL_TOPIC = os.environ.get('ROBOTER_PROPOSAL_TOPIC')
ROBOT_REGISTER_TOPIC = os.environ.get('ROBOTER_REGISTER_TOPIC')
ROBOTER_REGISTER_CONFIRMATION_TOPIC = os.environ.get('ROBOTER_REGISTER_CONFIRMATION_TOPIC')
ROBOT_STATUS_TOPIC = os.environ.get('ROBOT_STATUS_TOPIC')

AWARD_TOPIC = "supplier/+/award"  # Thema für Gewinner
PROCESSED_TOPIC = os.environ.get('PROCESSED_TOPIC')

REKONFIG_TIMER_TOPIC = "rekonfig/time"
RECONFIGURE_DATA = "+/+/reconfigure"

# Variablen
lastRegisteredSupplier = ""
lastRegisteredStorage = ""
currentNumberOfSuppliers = os.environ.get('NUMBER_OF_SUPPLIERS')
currentNumberOfStorages = os.environ.get('NUMBER_OF_STORAGES')
last_cfp_data = None  # Zwischenspeicherung der letzten CfP-Daten
current_cfp_data = None
roboter_status = "ready"  # Standardstatus des Roboters
roboter_battery = 100
register_flag = False
charging_flag = False
transport_type = ["express", "standard"]
current_storage = ""
current_supplier = ""
reconfig_data = []  # Reconfig-Daten als Feld
charging_tick_counter = 0;
process_tick_counter = 0;
supplier_cfp_topics = []
storage_cfp_topics = []
# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,  # Log-Level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Log-Ausgabe auf die Konsole
    ]
)
logger = logging.getLogger(NAME)

def register_robot(client):
    """
    Führt die Registrierung des Roboters durch und veröffentlicht den initialen Status.
    """
    global roboter_status,current_supplier,current_storage,lastRegisteredStorage,lastRegisteredSupplier,supplier_cfp_topic,storage_cfp_topic
    registerNumber = random.randint(1, int(currentNumberOfSuppliers))

    current_supplier = f"supplier/{registerNumber}"
    current_storage = f"storage/{registerNumber}"

    logger.info(f"CURRENT SUPPLIER: {current_supplier}, CURRENT STORAGE: {current_storage}")
    if current_supplier == lastRegisteredSupplier and current_storage == lastRegisteredStorage:
        logger.info(f"Robot {NAME} has already been registered with the same supplier and storage. Supplier: {current_supplier}, Storage: {current_storage}")
        return
    
    # Registrierungsdaten
    register_data = {
        "name": NAME,
        "status": roboter_status,
        "storage": current_storage,
        "supplier": current_supplier
    }
    client.publish(ROBOT_REGISTER_TOPIC, json.dumps(register_data))

    supplier_cfp_topic = f"{current_supplier}/cfp"
    storage_cfp_topic = f"{current_storage}/cfp"

    client.subscribe(supplier_cfp_topic)
    supplier_cfp_topics.append(supplier_cfp_topic)
    client.subscribe(storage_cfp_topic)
    storage_cfp_topics.append(storage_cfp_topic)
    lastRegisteredStorage = current_storage
    lastRegisteredSupplier = current_supplier

def on_registerConfirmationTopic(client, userdata, msg):
    """
    Führt die Registrierung des Roboters durch und veröffentlicht den initialen Status.
    """
    global register_flag

    register_data = json.loads(msg.payload.decode("utf-8"))
    confirmation_supplier_name = register_data.get("supplier")
    confirmation_name = register_data.get("name")
    confirmation_status = register_data.get("status")

    if confirmation_name == NAME and confirmation_supplier_name == current_supplier:
        if confirmation_status == "registered":
            register_flag = True
            logger.info(f"{NAME} wurde erfolgreich registriert.")
            logger.info(f"CONFIRM=Supplier: {confirmation_supplier_name}, Name: {confirmation_name}, Status: {confirmation_status}, Register_Flag: {register_flag}")

def on_cfp_message(client, userdata, msg):
    """
    Callback für CfP-Nachrichten vom Supplier.
    Speichert die empfangenen CfP-Daten.
    """
    global current_cfp_data, last_cfp_data
    try:
        cfp_data = json.loads(msg.payload.decode("utf-8"))
        if cfp_data != last_cfp_data:
            #logger.info(f"\nEmpfangene CfP-Daten: {cfp_data}")
            last_cfp_data = current_cfp_data
            current_cfp_data = cfp_data  # CfP-Daten zwischenspeichern
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der CfP-Nachricht: {e}")

def on_award_message(client, userdata, msg):
    """
    Callback für AWARD-Nachrichten vom Supplier.
    Überprüft, ob der Roboter ausgewählt wurde.
    """
    try:
        award_data = json.loads(msg.payload.decode("utf-8"))

        # Überprüfen, ob die notwendigen Felder vorhanden sind
        if not all(key in award_data for key in ["winner", "package_type", "transport_type", "battery", "battery_cost", "estimated_time","quantity"]):
            logger.error("Ungültige Award-Daten. Auftrag wird ignoriert.")
            return

        if award_data["winner"] == NAME:
            logger.info(f"Empfangene Award-Daten: {award_data}")
            process_package(client, award_data["package_type"], award_data["battery_cost"], award_data["estimated_time"], award_data["timestamp"], award_data["transport_type"],award_data["quantity"])
        else:
            logger.info(f"{NAME} hat den Auftrag nicht erhalten. Ignoriere Auftrag.")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Award-Nachricht: {e}")

def on_tick_message(client, userdata, msg):
    """
    Callback für Tick-Nachrichten.
    Prüft, ob ein Proposal basierend auf den letzten CfP-Daten gesendet werden soll.
    """
    global last_cfp_data, roboter_battery,charging_tick_counter,roboter_status,process_tick_counter

    if register_flag == False:
        register_robot(client)
    # Akku prüfen
    data = {"battery": roboter_battery,}
    client.publish(DATA_TOPIC, json.dumps(data))
    
    if supplier_cfp_topics:
        for topic in supplier_cfp_topics:
            client.message_callback_add(topic, on_cfp_message)

    if storage_cfp_topics:
        for topic in storage_cfp_topics:
            client.message_callback_add(topic, on_cfp_message)

    if roboter_battery < 20:
        if charging_tick_counter  >= 0:
            logger.info(f"{NAME} Akku ist zu niedrig ({roboter_battery}%). Lade Akku auf.")
            charging_tick_counter = -1
            return
        roboter_battery = 100
        logger.info(f"{NAME} Akku vollständig aufgeladen.")
    
    if roboter_status == "busy":
        if process_tick_counter > 0:
            process_tick_counter -= 1
            return
        else:
            roboter_status = "ready"
            current_status = {
                "name": NAME,
                "status": roboter_status
            }
            client.publish(ROBOT_STATUS_TOPIC, json.dumps(current_status))
            logger.info(f"{NAME} ist bereit.")
            return

    if current_cfp_data and current_cfp_data != last_cfp_data and roboter_status == "ready":  # Nur wenn CfP-Daten vorhanden und Roboter bereit
        package_type = current_cfp_data.get("package_type")
        send_proposal(client, package_type)

def send_proposal(client, package_type):
    """
    Sendet ein Proposal basierend auf den CfP-Daten.
    """
    global roboter_battery, transport_type

    transmission_type = transport_type[0 if random.random() < 0.35 else 1]

    if transmission_type == "express":
        proposal = {
            "place": current_supplier if current_supplier else current_storage,
            "name": NAME,
            "package_type": package_type,
            "transport_type": 2,
            "battery": roboter_battery,
            "battery_cost": random.randint(8, 10),
            "estimated_time": random.randint(1, 2)
        }
        client.publish(ROBOT_PROPOSAL_TOPIC, json.dumps(proposal))  # Proposal senden
        #logger.info(f"Proposal gesendet: {proposal}")
    else:
        proposal = {
            "place": current_supplier if current_supplier else current_storage,
            "name": NAME,
            "package_type": package_type,
            "transport_type": 1,
            "battery": roboter_battery,
            "battery_cost": random.randint(4, 8),
            "estimated_time": random.randint(3, 4)
        }
        client.publish(ROBOT_PROPOSAL_TOPIC, json.dumps(proposal))  # Proposal senden

def process_package(client, package_type, battery_cost, package_time, package_timestamp, transport_type,quantity):
    """
    Simuliert die Verarbeitung eines Pakets und sendet eine Bestätigung.
    """
    global roboter_status, roboter_battery, process_tick_counter
    try:
        roboter_status = "busy"  # Setze Roboter auf "busy"
        process_tick_counter = package_time
        current_status = {
            "name": NAME,
            "status": roboter_status
        }
        client.publish(ROBOT_STATUS_TOPIC, json.dumps(current_status))

        # Bestätigung senden
        confirmation = {
            "name": NAME,
            "package_type": package_type,
            "transport_type": transport_type,
            "status": "completed",
            "storage": current_storage,
            "supplier": current_supplier,
            "timestamp": package_timestamp,
            "quantity": quantity
        }
        client.publish(PROCESSED_TOPIC, json.dumps(confirmation))  # Nachricht senden
        logger.info(f"Bestätigung gesendet: {confirmation}")
        roboter_battery = max(0,roboter_battery-battery_cost)
        
        data = {"battery": roboter_battery,}
        client.publish(DATA_TOPIC, json.dumps(data))
        logger.info(f"{NAME} AKKU= {roboter_battery}")



    except Exception as e:
        logger.error(f"Fehler bei der Bearbeitung des Pakets: {e}")

def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)
 
    # CfP-Topic abonnieren
    mqtt.subscribe(SUPPLIER_CFP_TOPIC)
    mqtt.subscribe_with_callback(SUPPLIER_CFP_TOPIC, on_cfp_message)
    logger.info(f"{mqtt.name} subscribed to CfP-Topic: {SUPPLIER_CFP_TOPIC}")

    # Award-Topic abonnieren
    mqtt.subscribe(AWARD_TOPIC)
    mqtt.subscribe_with_callback(AWARD_TOPIC, on_award_message)
    logger.info(f"{mqtt.name} subscribed to Award-Topic: {AWARD_TOPIC}")

    # Tick-Topic abonnieren
    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_tick_message)
    logger.info(f"{mqtt.name} subscribed to Tick-Topic: {TICK_TOPIC}")

    mqtt.subscribe(ROBOTER_REGISTER_CONFIRMATION_TOPIC)
    mqtt.subscribe_with_callback(ROBOTER_REGISTER_CONFIRMATION_TOPIC, on_registerConfirmationTopic)
    logger.info(f"{mqtt.name} subscribed to Tick-Topic: {ROBOTER_REGISTER_CONFIRMATION_TOPIC}")

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
