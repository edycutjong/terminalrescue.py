import paho.mqtt.client as mqtt
import config

def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("swarm/#", qos=1)

def on_message(client, userdata, message):
    print(message.topic, message.payload.decode('utf-8'))

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set("observer", "demopass")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.FOXMQ_HOST, config.FOXMQ_PORT)
    client.loop_forever()

if __name__ == "__main__":  # pragma: no cover
    main()
