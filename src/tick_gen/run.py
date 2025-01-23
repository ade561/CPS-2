import sys
import json
import time
import logging
from datetime import datetime, timedelta
from mqtt.mqtt_wrapper import MQTTWrapper



TICK_TOPIC = "tickgen/tick"
RECONFIG_TIMER_TOPIC = "reconfig/time"
SPEEDFACTOR_TOPIC = "tickgen/speed_factor"
interval_sec = 30
speed_factor = 10
reconfig_counter = 4

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def on_message_speedfactor(client, userdata, msg):
    global speed_factor
    new_speed_factor = float(msg.payload.decode("utf-8"))
    if speed_factor >= 0.1:
        speed_factor = new_speed_factor

def main():
    START_DATE = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    tick_sec = 0
    
    mqtt = MQTTWrapper('mqttbroker', 1883, name='tick_generator')
    mqtt.publish(SPEEDFACTOR_TOPIC, speed_factor)
    mqtt.subscribe(SPEEDFACTOR_TOPIC)
    mqtt.subscribe_with_callback(SPEEDFACTOR_TOPIC, on_message_speedfactor)



    try:
        while True:
            ts = START_DATE + timedelta(seconds=tick_sec)
            ts_iso = ts.isoformat()

            mqtt.publish(TICK_TOPIC, ts_iso)
            tick_sec = tick_sec + 30
            time.sleep(interval_sec * (1.0 / speed_factor))

            global reconfig_counter
            reconfig_counter -= 1
            if reconfig_counter == 0:
                mqtt.publish(RECONFIG_TIMER_TOPIC, json.dumps(0))
                logger.info(f"Reconfig Counter abgelaufen. 0 auf {RECONFIG_TIMER_TOPIC} veröffentlicht.")
                reconfig_counter = 5
            elif reconfig_counter == 1:
                mqtt.publish(RECONFIG_TIMER_TOPIC, json.dumps(1))
                logger.info(f"Reconfig Counter abgelaufen. 1 auf {RECONFIG_TIMER_TOPIC} veröffentlicht.")
                

    except(KeyboardInterrupt, SystemExit):
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    main()
