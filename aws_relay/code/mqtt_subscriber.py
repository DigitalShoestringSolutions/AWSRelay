# ----------------------------------------------------------------------
#
#    AWS Relay -- This digital solution subscribe to a local mqtt broker,
#    forward the message to an endpoint in AWS.
#
#    Copyright (C) 2022  Shoestring and University of Cambridge
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 3 of the License.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see https://www.gnu.org/licenses/.
#
# ----------------------------------------------------------------------


import paho.mqtt.client as mqtt
import logging
import multiprocessing
import json

import zmq

logger = logging.getLogger("main.mqtt_subscriber")
context = zmq.Context()


class MQTTSubscriber(multiprocessing.Process):
    def __init__(self, config, zmq_conf):
        super().__init__()

        subscriber_conf = config['mqtt_subsciber']
        self.url = subscriber_conf['broker']
        self.port = int(subscriber_conf['port'])
        self.subscriptions = subscriber_conf['subscription']

        # declarations
        self.zmq_conf = zmq_conf
        self.zmq_out = None

    def do_connect(self):
        self.zmq_out = context.socket(self.zmq_conf['type'])
        if self.zmq_conf["bind"]:
            self.zmq_out.bind(self.zmq_conf["address"])
        else:
            self.zmq_out.connect(self.zmq_conf["address"])

    def run(self):
        logger.info("Starting")
        self.do_connect()
        logger.info("ZMQ Connected")

        client = mqtt.Client()
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.on_disconnect = self.on_disconnect

        client.connect(self.url, self.port, 60)
        client.loop_forever()

    def on_connect(self, client, _userdata, _flags, rc):
        logger.info("Connected with result code " + str(rc))
        # do subscribe
        for entry in self.subscriptions:
            if 'topic' in entry:
                qos = entry.get('qos', 0)
                topic = entry['topic']
                logger.info(f"Subscribing to {topic} at QOS {qos}")
                client.subscribe(topic, qos)

    def on_message(self, _client, _userdata, msg):
        output = {'topic': msg.topic, 'payload': json.loads(msg.payload)}
        logger.info(f"Forwarding {output}")
        self.zmq_out.send_json(output)

    def on_disconnect(self, _client, _userdata, rc):
        if rc != 0:
            print("Unexpected disconnection.")
