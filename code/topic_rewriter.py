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


import multiprocessing
import zmq
import logging
import json

context = zmq.Context()
logger = logging.getLogger("main.topic_rewriter")


class TopicRewriter(multiprocessing.Process):
    def __init__(self, config, zmq_conf):
        super().__init__()

        topic_rw_conf = config['topic_rewriter']
        self.mapping_tree, self.mapping_list = build_mapping_tree(topic_rw_conf['topic'])

        logger.debug(self.mapping_tree)
        logger.debug(self.mapping_list)

        # declarations
        self.zmq_conf = zmq_conf
        self.zmq_in = None
        self.zmq_out = None

    def do_connect(self):
        self.zmq_in = context.socket(self.zmq_conf['in']['type'])
        if self.zmq_conf['in']["bind"]:
            self.zmq_in.bind(self.zmq_conf['in']["address"])
        else:
            self.zmq_in.connect(self.zmq_conf['in']["address"])

        self.zmq_out = context.socket(self.zmq_conf['out']['type'])
        if self.zmq_conf['out']["bind"]:
            self.zmq_out.bind(self.zmq_conf['out']["address"])
        else:
            self.zmq_out.connect(self.zmq_conf['out']["address"])

    def run(self):
        logger.info("Starting")
        self.do_connect()
        logger.info("ZMQ Connected")
        run = True
        while run:
            while self.zmq_in.poll(50, zmq.POLLIN):
                try:
                    msg = self.zmq_in.recv(zmq.NOBLOCK)
                    msg_json = json.loads(msg)

                    msg_topic = msg_json['topic']
                    msg_payload = msg_json['payload']
                    try:
                        msg_topic = self.remap_topic(msg_topic)
                    except Exception as e:
                        logger.error(e)
                    self.zmq_out.send_json({'topic': msg_topic, 'payload': msg_payload})
                except zmq.ZMQError:
                    pass

    def remap_topic(self, topic):
        topic_tokens = topic.split('/')
        uid = self.recursive_search(topic_tokens,self.mapping_tree)
        if uid:
            return self.transform_topic(topic, uid)
        else:
            return topic

    def recursive_search(self, tokens, current_tree_level):
        if len(tokens) == 0:
            # logger.debug(f"No more tokens, returning current node value {current_tree_level.getValue()}")
            return current_tree_level.getValue()

        token = tokens[0]

        if token in current_tree_level:
            # logger.debug(f">{token} at level")
            uid = self.recursive_search(tokens[1:], current_tree_level[token])
            if uid is not None:
                return uid

        if '+' in current_tree_level:
            # logger.debug(f">'+' at level for {token}")
            uid = self.recursive_search(tokens[1:], current_tree_level['+'])
            if uid is not None:
                return uid

        if '#' in current_tree_level:
            # logger.debug(f">'#' at level for {token}, returning {current_tree_level['#'].getValue()}")
            return current_tree_level['#'].getValue()
        else:  # no match
            # logger.debug(f"No match for {token} at {current_tree_level}")
            return None

    def transform_topic(self, topic, uid):
        if uid not in self.mapping_list:
            logger.error(f"Unable to find mapping for topic {topic} at id {uid}")
            return topic
        mapping = self.mapping_list[uid]

        logger.debug(f"remapping {topic} with {mapping}")

        # if no pattern - we are in replace mode
        if 'pattern' not in mapping or not mapping['pattern']:
            topic = sanitise(mapping['remote_prefix'])
        else:
            # strip local prefix
            if 'local_prefix' in mapping and mapping['local_prefix']:
                # might lead to a bug if local prefix isn't present, but should be ok given prior checks
                topic = topic.replace(sanitise(mapping['local_prefix']) + '/', '')

            # add remote prefix
            if 'remote_prefix' in mapping and mapping['remote_prefix']:
                topic = sanitise(mapping['remote_prefix']) + '/' + topic

        return topic


# Utility Functions:
def build_mapping_tree(mapping_list):
    counter = 0
    map_tree = SimpleTreeNode()
    map_list = {}
    for mapping in mapping_list:
        if 'local_prefix' not in mapping or not mapping['local_prefix']:
            full_topic = mapping['pattern']
        elif 'pattern' not in mapping or not mapping['pattern']:
            full_topic = mapping['local_prefix']
        else:
            full_topic = sanitise(mapping['local_prefix']) + '/' + mapping['pattern']

        full_topic_tokens = full_topic.split('/')

        uid = f"uid_{counter}"
        add_to_tree(full_topic_tokens, map_tree, uid)
        map_list[uid] = mapping
        counter += 1
    return map_tree, map_list


def add_to_tree(tokens, current_level, uid):
    token = tokens.pop(0)

    if len(tokens) == 0 or token == '#':  # if no more tokens or wildcard
        current_level[token] = uid
    else:
        if token not in current_level:
            current_level.createNode(token)
        # recurse at next level down
        add_to_tree(tokens, current_level[token], uid)


def sanitise(prefix):
    prefix.replace('#', '')
    prefix.replace('+', '')
    return prefix


# Tree Class

class SimpleTreeNode:
    def __init__(self):
        self.__value = None
        self.__next = {}

    def setValue(self, value):
        self.__value = value

    def getValue(self):
        return self.__value

    def createNode(self, key):
        self.__next[key] = SimpleTreeNode()

    def __contains__(self, item):
        return item in self.__next

    def __getitem__(self, key):
        return self.__next[key]

    def __setitem__(self, key, value):
        self.__next[key] = SimpleTreeNode()
        self.__next[key].setValue(value)

    def __str__(self, level=1):
        node_strings = "\n"
        tabs = "\t" * level
        for key, node in self.__next.items():
            node_strings += f'{tabs}{key}:{node.__str__(level + 1)}'
        # node_strings += '\n'
        return f"{self.__value} {node_strings}"
