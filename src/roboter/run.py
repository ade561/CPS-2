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
CFP_TOPIC = os.environ.get('CFP_TOPIC')  # CfP-Thema
PROCESSED_TOPIC = os.environ.get('PROCESSED_TOPIC')
ROBOT_PROPOSAL_TOPIC = os.environ.get('ROBOTER_PROPOSAL_TOPIC')
ROBOT_REGISTER_TOPIC = os.environ.get('ROBOTER_REGISTER_TOPIC')
ROBOT_STATUS_TOPIC = os.environ.get('ROBOT_STATUS_TOPIC')
AWARD_TOPIC = "supplier/+/award"  # Thema für Gewinner
TICK_TOPIC = "tickgen/tick"

# Variablen
last_cfp_data = None  # Zwischenspeicherung der letzten CfP-Daten
current_cfp_data = None
roboter_status = "ready"  # Standardstatus des Roboters
roboter_battery = 100
register_flag = False
transport_type = {"express","standard"}

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
    global register_flag, roboter_status

    # Registrierungsdaten
    register_data = {"name": NAME}
    client.publish(ROBOT_REGISTER_TOPIC, json.dumps(register_data))
    logger.info(f"{NAME} hat sich erfolgreich beim Supplier registriert.")

    # Initialer Status
    status_data = {
        "name": NAME,
        "status": roboter_status  # Initialstatus: "ready"
    }
    client.publish(ROBOT_STATUS_TOPIC, json.dumps(status_data))
    logger.info(f"Initialer Status veröffentlicht: {status_data}")

    # Registrierung als abgeschlossen markieren
    register_flag = True

def charge_battery(client):
    """
    Simuliert das Aufladen des Roboters.
    """
    global roboter_battery, roboter_status
    roboter_status = "charging"
    logger.info(f"{NAME} beginnt mit dem Aufladen des Akkus.")

    charging_data = {
        "name": NAME,
        "status": roboter_status
    }

    client.publish(ROBOT_STATUS_TOPIC, json.dumps(charging_data))
    logger.info(f"{NAME} published den Beginn des Ladevorgang auf {ROBOT_STATUS_TOPIC}.")
    while roboter_battery < 100:
        time.sleep(5)  # Simuliere Ladezeit
        roboter_battery += 10
        roboter_battery = min(roboter_battery, 100)
        logger.info(f"{NAME} lädt auf... Akku: {roboter_battery}%")
    roboter_status = "ready"
    logger.info(f"{NAME} Akku vollständig aufgeladen. Status: {roboter_status}.")
    
    charging_data = {
        "name": NAME,
        "status": roboter_status
    }

    client.publish(ROBOT_STATUS_TOPIC, json.dumps(charging_data))
    logger.info(f"{NAME} published das Ende des Ladevorgang auf {ROBOT_STATUS_TOPIC}.")

def on_cfp_message(client, userdata, msg):
    """
    Callback für CfP-Nachrichten vom Supplier.
    Speichert die empfangenen CfP-Daten.
    """
    global current_cfp_data,last_cfp_data, register_flag
    try:
        cfp_data = json.loads(msg.payload.decode("utf-8"))
        if cfp_data != last_cfp_data:
            logger.info(f"Empfangene CfP-Daten: {cfp_data}")
            last_cfp_data = current_cfp_data
            current_cfp_data = cfp_data  # CfP-Daten zwischenspeichern
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der CfP-Nachricht: {e}")


def on_award_message(client, userdata, msg):
    """
    Callback für AWARD-Nachrichten vom Supplier.
    Überprüft, ob der Roboter ausgewählt wurde.
    """
    global roboter_status
    try:
        award_data = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"Empfangene Award-Daten: {award_data}")

        # Überprüfen, ob die notwendigen Felder vorhanden sind
        if not all(key in award_data for key in ["winner", "package_type", "estimated_time"]):
            logger.error("Ungültige Award-Daten. Auftrag wird ignoriert.")
            return

        if award_data["winner"] == NAME:
            #logger.info(f"{NAME} hat den Auftrag erhalten. Beginne Bearbeitung.")
            roboter_status = "busy"  # Setze Roboter auf "busy"
            #logger.info(f"Status des {NAME}: {roboter_status}.")
            process_package(client, award_data["package_type"], award_data["estimated_time"])
        else:
            logger.info(f"{NAME} hat den Auftrag nicht erhalten. Ignoriere Auftrag.")
    except json.JSONDecodeError as e:
        logger.error(f"Fehler beim Decodieren der Award-Nachricht: {e}")



def on_tick_message(client, userdata, msg):
    """
    Callback für Tick-Nachrichten.
    Prüft, ob ein Proposal basierend auf den letzten CfP-Daten gesendet werden soll.
    """
    global last_cfp_data, roboter_status, roboter_battery,register_flag
    #ts_iso = msg.payload.decode("utf-8")
    logger.info(f"{NAME}: status {roboter_status} und Akku={roboter_battery}")
    if register_flag == False:
        register_robot(client)
    # Akku prüfen
    if roboter_battery < 20:
        logger.info(f"{NAME} Akku ist zu niedrig ({roboter_battery}%). Lade Akku auf.")
        charge_battery(client)
        return  # Kein Proposal senden, wenn der Akku geladen wird.

    logger.info(f"Current CFP Data: {current_cfp_data}.")
    logger.info(f"Last CFP Data: {last_cfp_data}.")
    if current_cfp_data and current_cfp_data != last_cfp_data and roboter_status == "ready":  # Nur wenn CfP-Daten vorhanden und Roboter bereit
        send_proposal(client)



def send_proposal(client):
    """
    Sendet ein Proposal basierend auf den CfP-Daten.
    """
    global roboter_status,roboter_battery,transport_type

    transmission_type = transport_type[0 if random.random() < 0.35 else 1]

    if transmission_type == "express":
        proposal = {
            "name": NAME,
            "transport_type":2,
            "battery": roboter_battery,
            "battery_cost": random.randint(8, 20),
            "estimated_time": random.randint(1, 4)
        }
        client.publish(ROBOT_PROPOSAL_TOPIC, json.dumps(proposal))  # Proposal senden
        logger.info(f"Proposal gesendet: {proposal}")
    else:
        proposal = {
            "name": NAME,
            "transport_type":1,
            "battery": roboter_battery,
            "battery_cost": random.randint(4, 15),
            "estimated_time": random.randint(3, 6)
        }
        client.publish(ROBOT_PROPOSAL_TOPIC, json.dumps(proposal))  # Proposal senden
        logger.info(f"Proposal gesendet: {proposal}")


def process_package(client, package_type, package_time):
    """
    Simuliert die Verarbeitung eines Pakets und sendet eine Bestätigung.
    """
    global roboter_status, roboter_battery
    try:
       # logger.info(f"{NAME} beginnt mit der Bearbeitung von Paket Typ {package_type}.")
        time.sleep(package_time)  # Simuliere Bearbeitungszeit
       # logger.info(f"{NAME} hat die Bearbeitung von Paket Typ {package_type} abgeschlossen.")

        # Bestätigung senden
        confirmation = {
            "name": NAME,
            "package_type": package_type,
            "status": "completed"
        }
        client.publish(PROCESSED_TOPIC, json.dumps(confirmation))  # Nachricht senden
        logger.info(f"Bestätigung gesendet: {confirmation}")
        roboter_battery -= package_time
       # logger.info(f"{NAME} AKKU= {roboter_battery}")
        roboter_status = "ready"  # Roboter ist wieder bereit
       # logger.info(f"Status des {NAME}: {roboter_status}.")

        data = {
            "battery": roboter_battery,
        }
        client.publish(DATA_TOPIC, json.dumps(data))
        #logger.info(f"{NAME} Daten veröffentlicht: {data}")


    except Exception as e:
        logger.error(f"Fehler bei der Bearbeitung des Pakets: {e}")




def main():
    """
    Main function to initialize the MQTT client and start the event loop.
    """
    logger.info(f"Initializing MQTT client with name: {NAME}")
    mqtt = MQTTWrapper('mqttbroker', 1883, name=NAME)


    logger.info(f"STATUS_TOPIC: {ROBOT_STATUS_TOPIC}")
    logger.info(f"ROBOT_REGISTER_TOPIC: {ROBOT_REGISTER_TOPIC}")
    # CfP-Topic abonnieren
    mqtt.subscribe(CFP_TOPIC)
    mqtt.subscribe_with_callback(CFP_TOPIC, on_cfp_message)
    logger.info(f"{mqtt.name} subscribed to CfP-Topic: {CFP_TOPIC}")

    # Award-Topic abonnieren
    mqtt.subscribe(AWARD_TOPIC)
    mqtt.subscribe_with_callback(AWARD_TOPIC, on_award_message)
    logger.info(f"{mqtt.name} subscribed to Award-Topic: {AWARD_TOPIC}")

    # Tick-Topic abonnieren
    mqtt.subscribe(TICK_TOPIC)
    mqtt.subscribe_with_callback(TICK_TOPIC, on_tick_message)
    logger.info(f"{mqtt.name} subscribed to Tick-Topic: {TICK_TOPIC}")

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
