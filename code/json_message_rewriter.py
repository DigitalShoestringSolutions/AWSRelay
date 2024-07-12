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

from jsonpath_rw import parse
from enum import Enum, auto

context = zmq.Context()
logger = logging.getLogger("main.message_rewriter")

class LEAF(Enum):
    JSONPATH = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    NULL = auto()

class MessageRewriter(multiprocessing.Process):
    def __init__(self, config, zmq_conf):
        super().__init__()

        msg_rw_conf = config['json_message_rewriter']
        # todo fix
        self.topic_tree, self.entry_list = build_entry_tree(msg_rw_conf['entry'])

        logger.debug(f"topic_tree: {self.topic_tree}")
        logger.debug(f"entry_list: {self.entry_list}")

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
                        msg_payload = self.rewrite_message(msg_topic,msg_payload)
                    except Exception as e:
                        logger.error(e)
                    self.zmq_out.send_json({'topic': msg_topic, 'payload': msg_payload})
                except zmq.ZMQError:
                    pass


    def rewrite_message(self, topic, payload):
        topic_tokens = topic.split('/')
        uid = self.recursive_search(topic_tokens, self.topic_tree)
        if uid:
            entry = self.entry_list[uid]
            spec = entry['spec']
            append = entry['append']
            return transform_message(payload, spec, append)
        else:
            return payload

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

def transform_message(message, spec, append=True):
    logger.debug(f"Transform: {'append' if append else 'new'};{spec};{message};")
    out = {} if not append else to_flat_tree(message)
    for leaf_path, leaf_value in to_flat_tree(spec).items():
        leaf_type, true_value = get_leaf_type(leaf_value)
        if leaf_type == LEAF.JSONPATH:
            res = parse(true_value).find(message)
            if len(res) == 0:
                # not found
                logger.warning(f"json_path {leaf_value} return no data and was ignored")
                continue

            if len(res) > 1:
                logger.warning("json_path {leaf_value} returned more than one result - using first entry")
            leaf = res[0]
            value = leaf.value
            out[leaf_path] = value

            if append and str(leaf.full_path) != leaf_path:
                out.pop(str(leaf.full_path), None)
        else:
            out[leaf_path] = true_value
    return from_flat_tree(out)

def get_leaf_type(leaf_value):
    if leaf_value[0] == '#':
        return LEAF.STRING, leaf_value[1:]
    if leaf_value[0] == '=':
        rem = leaf_value[1:]
        if rem.casefold() == 'true':
            return LEAF.BOOLEAN, True
        if rem.casefold() == 'false':
            return LEAF.BOOLEAN, False
        if rem.casefold() == 'null':
            return LEAF.NULL, None
        else:
            try:
                return LEAF.NUMBER, int(rem)
            except ValueError:
                try:
                    return LEAF.NUMBER, float(rem)
                except ValueError:
                    logger.warning(f"Unable to parse {leaf_value} treating as string")
                    return LEAF.STRING, rem
    else:
        return LEAF.JSONPATH,leaf_value

def to_flat_tree(nested_dict, path=""):
    acc = {}
    for key, value in nested_dict.items():
        path_string = f"{path}{'.' if path else ''}{key}"
        if isinstance(value, dict):
            acc.update(to_flat_tree(value, path_string))
        # elif isinstance(value, list): #check if list of objects
        #     # throw error?
        #     pass
        else:  # should be an int or a string
            acc[path_string] = value
    return acc


def from_flat_tree(path_leave_dict):
    acc = {}

    for path_string, leaf_value in path_leave_dict.items():
        path_element_list = path_string.split('.')
        recursive_set_value(acc, path_element_list, leaf_value)

    return acc


def recursive_set_value(current_dict, path_list, value):
    current_element = path_list.pop(0)
    if len(path_list) == 0:
        current_dict[current_element] = value
    else:
        if current_element not in current_dict:
            current_dict[current_element] = {}
        recursive_set_value(current_dict[current_element], path_list, value)
        

# Utility Functions:
def build_entry_tree(entry_list):
    counter = 0
    topic_tree = SimpleTreeNode()
    out_list = {}
    for entry in entry_list:
        topic = entry['topic']

        topic_tokens = topic.split('/')

        uid = f"uid_{counter}"
        add_to_tree(topic_tokens, topic_tree, uid)
        spec = {}
        if 'spec_json' in entry:
            try:
                spec = json.loads(entry['spec_json'])
            except:
                logger.error(f"Unable to parse json spec: {entry['spec_json']}")
        elif 'spec' in entry:
            spec = spec

        out_list[uid] = {'append':entry.get('append',True),'spec':spec}
        counter += 1
    return topic_tree, out_list


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

