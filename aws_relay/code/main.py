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

# packages
import tomli
import time
import logging
import zmq
# local
import aws_publisher
import topic_rewriter
import json_message_rewriter
import mqtt_subscriber

logger = logging.getLogger("main")
logging.basicConfig(level=logging.DEBUG)  # move to log config file using python functionality


def get_config():
    with open("./config/config.toml", "rb") as f:
        toml_conf = tomli.load(f)
    logger.info(f"config:{toml_conf}")
    return toml_conf


def config_valid(config):
    return True


def create_building_blocks(config):
    bbs = {}

    mqtt_out = {"type": zmq.PUSH, "address": "tcp://127.0.0.1:4000", "bind": True}
    topic_rewrite_in = {"type": zmq.PULL, "address": "tcp://127.0.0.1:4000", "bind": False}
    topic_rewrite_out = {"type": zmq.PUSH, "address": "tcp://127.0.0.1:4002", "bind": True}
    message_rewrite_in = {"type": zmq.PULL, "address": "tcp://127.0.0.1:4002", "bind": False}
    message_rewrite_out = {"type": zmq.PUSH, "address": "tcp://127.0.0.1:4001", "bind": True}
    publisher_in = {"type": zmq.PULL, "address": "tcp://127.0.0.1:4001", "bind": False}

    bbs["mqtt_subscriber"] = mqtt_subscriber.MQTTSubscriber(config, mqtt_out)
    bbs["topic_rewriter"] = topic_rewriter.TopicRewriter(config, {'in': topic_rewrite_in, 'out': topic_rewrite_out})
    bbs["message_rewriter"] = json_message_rewriter.MessageRewriter(config, {'in': message_rewrite_in, 'out': message_rewrite_out})
    bbs["aws_publish"] = aws_publisher.AWSPublisher(config, publisher_in)

    logger.debug(f"bbs {bbs}")
    return bbs


def start_building_blocks(bbs):
    for key in bbs:
        p = bbs[key].start()


def monitor_building_blocks(bbs):
    while True:
        time.sleep(1)
        for key in bbs:
            # logger.debug(f"{bbs[key].exitcode}, {bbs[key].is_alive()}")
            # todo actually monitor
            pass


if __name__ == "__main__":
    conf = get_config()
    # todo set logging level from config file
    if config_valid(conf):
        bbs = create_building_blocks(conf)
        start_building_blocks(bbs)
        monitor_building_blocks(bbs)
    else:
        raise Exception("bad config")
