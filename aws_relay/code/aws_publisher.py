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

from awscrt import mqtt, http
from awsiot import mqtt_connection_builder

import multiprocessing
import logging
import zmq
import json

context = zmq.Context()
logger = logging.getLogger("main.aws_publisher")


class AWSPublisher(multiprocessing.Process):
    def __init__(self, config, zmq_conf):
        super().__init__()

        aws_conf = config['aws_publisher']
        self.endpoint = aws_conf['endpoint']
        self.port = int(aws_conf['port'])
        self.cert_path = aws_conf['cert_path']
        self.private_key_path = aws_conf['private_key_path']
        self.ca_path = aws_conf['ca_path']

        self.clientId = aws_conf['client_id']

        # declarations
        self.zmq_conf = zmq_conf
        self.zmq_in = None

    def do_connect(self):
        self.zmq_in = context.socket(self.zmq_conf['type'])
        if self.zmq_conf["bind"]:
            self.zmq_in.bind(self.zmq_conf["address"])
        else:
            self.zmq_in.connect(self.zmq_conf["address"])

    def mqtt_connect(self, client):
        logger.info(f'connecting to {self.endpoint}:{self.port}')
        connect_future = client.connect()
        connect_future.result()  # will raise error on failure

    def on_connection_interrupted(self, connection, error, **kwargs):
        logger.error("Connection interrupted. error: {}".format(error))

    # Callback when an interrupted connection is re-established.
    def on_connection_resumed(self, connection, return_code, session_present, **kwargs):
        logger.info("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

        if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
            logger.warning("Session did not persist. Resubscribing to existing topics...")
            resubscribe_future, _ = connection.resubscribe_existing_topics()

            # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
            # evaluate result with a callback instead.
            resubscribe_future.add_done_callback(self.on_resubscribe_complete)

    def on_resubscribe_complete(self, resubscribe_future):
        resubscribe_results = resubscribe_future.result()
        logger.info("Resubscribe results: {}".format(resubscribe_results))

        for topic, qos in resubscribe_results['topics']:
            if qos is None:
                logger.error("Server rejected resubscribe to topic: {}".format(topic))

    def on_disconnect(self, client, _userdata, rc):
        if rc != 0:
            logger.error(f"Unexpected MQTT disconnection (rc:{rc}), reconnecting...")
            self.mqtt_connect(client)

    def run(self):
        self.do_connect()

        client = mqtt_connection_builder.mtls_from_path(
            endpoint=self.endpoint,
            port=self.port,
            cert_filepath=self.cert_path,
            pri_key_filepath=self.private_key_path,
            ca_filepath=self.ca_path,
            on_connection_interrupted=self.on_connection_interrupted,
            on_connection_resumed=self.on_connection_resumed,
            client_id=self.clientId,
            clean_session=False,
            keep_alive_secs=60)

        self.mqtt_connect(client)

        run = True
        while run:
            while self.zmq_in.poll(50, zmq.POLLIN):
                try:
                    msg = self.zmq_in.recv(zmq.NOBLOCK)
                    msg_json = json.loads(msg)
                    msg_topic = msg_json['topic']
                    msg_payload = msg_json['payload']
                    logger.debug(f'pub topic:{msg_topic} msg:{msg_payload}')
                    client.publish(
                        topic=msg_topic,
                        payload=json.dumps(msg_payload),
                        qos=mqtt.QoS.AT_LEAST_ONCE)
                except zmq.ZMQError:
                    pass
            # client.loop(0.05)
