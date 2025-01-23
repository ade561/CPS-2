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

RECONFIG_TIMER_TOPIC = "reconfig/time"
RECONFIGURE_DATA = "+/+/reconfig"

# Variablen
lastRegisteredSupplier = ""
lastRegisteredStorage = ""
last_cfp_data = None  # Zwischenspeicherung der letzten CfP-Daten
current_cfp_data = None
roboter_status = "ready"  # Standardstatus des Roboters
roboter_battery = 100
register_flag = False
charging_flag = False
transport_type = ["express", "standard"]
current_storage = "storage/1"
current_supplier = "supplier/1"
reconfig_data = []  # Reconfig-Daten als Feld
charging_tick_counter = 0
process_tick_counter = 0
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
    global roboter_status,current_supplier,current_storage,lastRegisteredStorage,lastRegisteredSupplier

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

    if lastRegisteredStorage == None or lastRegisteredStorage == "":
        client.unsubscribe(f"{lastRegisteredStorage}/cfp", on_cfp_message)
    else:
        client.unsubscribe(f"{lastRegisteredStorage}/cfp", on_cfp_message)

    if current_supplier == None or current_supplier == "":
        client.message_callback_add(f"{current_supplier}/cfp", on_cfp_message)
    else:
        client.message_callback_add(f"{current_storage}/cfp", on_cfp_message)

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
    global last_cfp_data, roboter_battery,charging_tick_counter,roboter_status,process_tick_counter

    if register_flag == False:
        register_robot(client)

    # Akku prüfen
    data = {"battery": roboter_battery,}
    client.publish(DATA_TOPIC, json.dumps(data))
    
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
#############Reconfigure##############################

####Neues Position berechnen ########
def sum_robots(data):
    return sum(item[1] for item in data if 'storage' in item[0])

def sum_fullness(data):
    return sum(item[3] for item in data)

def relativ_fullness(data, total_fullness):
    for item in data:
        item[3] = item[3] / total_fullness
    return data

def sort_reconfig_data(data):
    data.sort(key=lambda x: (x[0].split('/')[0].lower(), int(x[0].split('/')[1])))
    return data

def calculate_robots(data):
    total_robots = sum_robots(data)
    total_fullness = sum_fullness(data)
    data = relativ_fullness(data, total_fullness)

    proportional_robots = [item[3] * total_robots for item in data]
    rounded_robots = [round(num) for num in proportional_robots]
    difference = total_robots - sum(rounded_robots)

    if difference != 0:
        adjustments = sorted(enumerate(proportional_robots), key=lambda x: x[1] - round(x[1]), reverse=(difference > 0))
        for i in range(abs(difference)):
            idx = adjustments[i][0]
            rounded_robots[idx] += 1 if difference > 0 else -1

    for i, item in enumerate(data):
        item[1] = rounded_robots[i]

    return sort_reconfig_data(data)

def calculate_moving(data):
    data = calculate_robots(data)
    excess_robots = []

    for entry in data:
        while len(entry[2]) > entry[1]:
            excess_robots.append(entry[2].pop())

    for entry in data:
        while len(entry[2]) < entry[1]:
            if excess_robots:
                entry[2].append(excess_robots.pop(0))
            else:
                print(f"Warning: Not enough robots available to fulfill requirements for {entry}.")
                break

    return data

def give_new_position(data, name):
    data = calculate_moving(data)
    supplier = ""
    storage = ""

    for entry in data:
        if name in entry[2]:
            if 'supplier' in entry[0]:
                supplier = entry[0]
                supplier_number = entry[0].split('/')[1]
                storage = f"storage_{supplier_number}"
            elif 'storage' in entry[0]:
                storage = entry[0]
                supplier = ""

    return supplier, storage

#####################################

def on_message_reconfig_timer(client, userdata, msg):
    global current_supplier, current_storage, reconfig_data, register_flag

    message = msg.payload.decode("utf-8").strip().lower()

    if message == '0':
        current_supplier, current_Storage = give_new_position(reconfig_data.copy(), NAME)
        logger.info(f"Neue Positionen: {current_supplier}, {current_Storage}")

        if current_Storage != lastRegisteredStorage or current_supplier != lastRegisteredSupplier:
            register_flag = False

def on_message_reconfig_data(client, userdata, msg):
    global reconfig_data
    try:
        data = json.loads(msg.payload.decode("utf-8"))

        logger.info(f"message_reconfig{data}")

        name = data.get("name")
        count_robots = data.get("count_robots", 0)
        registered_robots = data.get("registered_robots", 0)
        fullness = data.get("fullness", 0)

        #logger.info(f"Reconfig-Daten empfangen: {data}")

        if name:
            # Überprüfen, ob es bereits einen Eintrag mit dem Namen gibt
            for entry in reconfig_data:
                if entry[0] == name:
                    entry[1] = count_robots
                    entry[2] = registered_robots
                    entry[3] = fullness
                    break
            else:
                reconfig_data.append([name, count_robots, registered_robots, fullness])
            logger.info(f"Reconfig-Daten: {reconfig_data}")
        else:
            logger.error("Reconfig-Daten ohne Namen empfangen.")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Reconfig-Daten-Nachricht: {e}")

######################################################
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

    mqtt.subscribe(RECONFIG_TIMER_TOPIC)
    logger.info(f"Subscribing to tick topic: {RECONFIG_TIMER_TOPIC}")
    mqtt.subscribe_with_callback(RECONFIG_TIMER_TOPIC, on_message_reconfig_timer)

    mqtt.subscribe(RECONFIGURE_DATA)
    logger.info(f"Subscribing to tick topic: {RECONFIGURE_DATA}")
    mqtt.subscribe_with_callback(RECONFIGURE_DATA, on_message_reconfig_data)


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
