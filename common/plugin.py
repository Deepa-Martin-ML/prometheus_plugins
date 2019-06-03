"""
*******************
*Copyright 2017, MapleLabs, All Rights Reserved.
*
********************
"""

import copy
import json
import logging
import threading
import time
import socket
import traceback
import requests


class Plugin(object):

    """
    Baseclass for all Plugins
    """
    BUF_SIZE = 4096
    DELIMITER = '|'

    def __init__(self, cfg, port):

        self._cfg = cfg
        self._port = port
        self._running = False
        self._newPollInterval = 0
        self._newConfig = False
        self._lock = threading.Lock()
        self._thread = None
        self.stop = False

        logging.basicConfig(filename='plugin.log', level=logging.DEBUG, filemode='a',
                            format="[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)s] %(message)s",
                            datefmt='%d/%b/%Y %H:%M:%S')
        self._plugin_name = "[{},{}] ".format(
            self._cfg['type'], self._cfg['name'])

    def start(self):
        self.log_info("plugin start")

        # set config and start polling
        self._start_poll_thread()

        # start comm thread
        self._comm(self._port)

        # wait for polling thread to complete
        self._thread.join()
        self._thread = None

        self.log_info("plugin end")

    def _comm(self, port):
        cmds = None

        try:
            # create socket and bind to port
            skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            skt.bind(('localhost', port))

            self.log_debug("socket bound to port {}".format(port))

            while True:
                # listen and acception connection on socket
                skt.listen(1)
                conn, addr = skt.accept()

                # receive message
                # data = conn.recv(self.BUF_SIZE)
                data = ""
                message = conn.recv(self.BUF_SIZE)

                data += message

                while not len(message) < self.BUF_SIZE:
                    message = conn.recv(self.BUF_SIZE)
                    data += message
                cmds = data[:-1].split(self.DELIMITER)

                self.log_debug("Plugin received command %s from controller" %(cmds[0]))

                if cmds[0] == 'KILL':
                    try:
                        ret, obj = self._stop_poll()
                        self.log_debug("command: %s function: _stop_poll() returned ret:%s obj:%s"%(cmds[0], ret, obj))
                    except Exception as err:
                        self.log_error("error in command KILL %s" %(err))
                        raise
                elif cmds[0] == 'SET_CONFIG':
                    try:
                        ret, obj = self.set_config(json.loads(cmds[1]))
                       # self.log_debug("command: %s function: set_config() returned ret:%s obj:%s" % (cmds[0], ret, obj))
                    except Exception as err:
                        self.log_error("error in command SET_CONFIG %s" % (err))
                        raise
                elif cmds[0] == 'GET_CONFIG':
                    ret, obj = self.get_config()
                    self.log_debug("command: %s function: get_config() returned ret:%s obj:%s" % (cmds[0], ret, obj))
                elif cmds[0] == 'GET_STATUS':
                    ret, obj = self.get_status()
                elif cmds[0] == 'SET_COMMAND':
                    ret, obj = self.get_exec_command(json.loads(cmds[1]))
                else:
                    ret = False
                    obj = {'error': 'Unsupported command - ' + cmds[0]}
                    self.log_error(
                        "received unsupported command - {}".format(cmds[0]))

                msg = 'PASS' if ret else 'FAIL'
                msg += self.DELIMITER + json.dumps(obj)
               # self.log_debug("Message being returned to controller from plugin: %s" %(msg))
                try:
                    conn.sendall(msg)
                except:
                    self.log_debug("Exception occurred communicating to controller.")
                conn.close()

                if cmds[0] == 'KILL':
                    self.log_debug("Closing socket %s as command triggered was KILL"%(port))
                    skt.close()
                    break
        except socket.error as err:
            self.log_error("Got error in socket communication module, stopping poll on hosts.")
            logging.critical("traceback : %s", str(err), exc_info=True)
            self.log_critical(str(err))
            #ret ,obj = self._stop_poll()
            if(cmds and cmds[0] == 'SET_CONFIG'):
                self.log_error("Raising error for SET_CONFIG.")
                raise
            return

    def _start_poll_thread(self):
        with self._lock:
            running = self._running
            if self.config_exists():
                enabled = self._cfg['config']['enabled']
            else:
                enabled = True

        # start thread if there isn't one already running
        if enabled and not running:
            # start polling thread
            thread = threading.Thread(target=self._poll, args=())
            thread.daemon = True
            thread.start()

            with self._lock:
                self._running = True
                self._thread = thread

            self.log_debug("started polling thread")

    def _stop_poll(self):
        if self._running and self.config_exists():
            with self._lock:
                # set enabled to false, so that polling stops on next cycle
                self._cfg['config']['enabled'] = False
                self.stop = True
                self.log_debug("KILL command recieved setting flag enabled to %s and stop to %s" %(self._cfg['config']['enabled'], self.stop))

        return True, None

    def set_config(self, cfg):
        with self._lock:
            self._cfg = copy.deepcopy(cfg)
            self._plugin_name = "[{},{}] ".format(
                self._cfg['type'], self._cfg['name'])
            self.log_debug("new config - {}".format(self._cfg))

        self._start_poll_thread()
        return True, cfg

    def get_config(self):
        with self._lock:
            cfg = copy.deepcopy(self._cfg)

        return True, cfg

    def get_status(self):
        with self._lock:
            cfg = {'running': self._running}
        return cfg

    def get_exec_command(self, cfg):
        with self._lock:
            exec_cfg = copy.deepcopy(cfg)
            if exec_cfg["command"] == "get_last_sample":
                data = self.get_last_sample()
                return True, data

    def wait_poll(self, time_taken, interval):
        sleep_time = interval - time_taken
        self.log_debug("Time taken for poll %s and time interval for workload %s, hence time left for following poll to start %s." % (time_taken, interval, sleep_time))
        if(sleep_time > 0):
            while(sleep_time > 0 and not self.stop):
                # self.log_debug("Waiting for %s seconds before another poll" %(sleep_time))

                # break the sleep cycle if there is a new config available to be applied
                with self._lock:
                    if self._newConfig:
                        self.log_debug("NewConfig has been recieved, skipping the sleep cycle")
                        self._newPollInterval = sleep_time
                        ##self._newConfig = False
                        break

                time.sleep(10)
                sleep_time -= 10
        return


    def _poll(self):
        while True:
            ret, cfg = self.get_config()

            # check if polling is disabled
            if self.config_exists() and not cfg['config']['enabled']:
                break

            start_time = time.time()
            self.log_debug("poll started")

            pol = self.poll()

            end_time = time.time()
            self.log_debug("poll ended")
            time_taken = end_time - start_time

            with self._lock:
                if self._newConfig:
                    self.log_debug("########## newConfig flag is true, skipping the sleep cycle")
                    self._newPollInterval = cfg['config']['interval'] - time_taken
                    continue

            if self.config_exists():
                interval = cfg['config']['interval']
                self.wait_poll(time_taken, interval)
                # if time_taken < interval:
                #     time.sleep(interval - time_taken)
            else:
                time.sleep(10)

        with self._lock:
            self._running = False

    def poll(self, cfg):
        docs = self.read(cfg)
        print docs

        if docs:
            self.write(cfg, docs)
            # TODO: update status

    def config_exists(self):
        logging.info("checking enabled in configuration")
        if 'config' in self._cfg.keys() and 'enabled' in self._cfg['config'].keys():
            return True
        return False

    def read(self, cfg):
        # child class will define this function
        pass

    def write(self, cfg, docs):
        for target in cfg['targets']:
            if target['type'] == 'stdout':
                self.write_stdout(docs)
            elif target['type'] == 'elasticsearch':
                self.write_to_elastic(docs, target)

    def write_stdout(self, docs):
        for doc in docs:
            print doc

    def write_to_elastic(self, data, details, ds_type = "_doc"):
        # To send the data to Elasticsearch
        url = "http://%s:%s/%s/%s/"
        headers = {'content-type': 'application/json'}
        timeout = 30
        res = ''
        details_config = details["config"]
        ds_host = details_config["host"]
        ds_port = details_config["port"]
        ds_index = details_config["index"]+"_write"
        try:
            es_url = url % (ds_host, ds_port, ds_index, ds_type)
            logging.info("Writing to Database %s" % ds_host)
            if isinstance(data, dict):
                for details_type, details in data.items():
                    res = requests.post(es_url, data=json.dumps(details), headers=headers, timeout=timeout)
            elif isinstance(data, list):
                for document in data:
                    res = requests.post(es_url, data=json.dumps(document), headers=headers, timeout=timeout)

        except Exception as e:
            logging.error("Exception in the write elastic due to %s" % e)
            res = 'Error Writting to ES => ' + traceback.format_exc().splitlines()[-1]
        logging.info("Writing to Database %s successfull" % ds_host)
        return res

    def GET(self, url):
        """
        :param url: URL for HTTP GET request
        :return: Status code + content of the GET request
        """
        res = requests.get(url)
        if(res.status_code == 200):
            return res.json()
        else:
            return None

    def convert_tag_keys(self, tag_dict):
        new_tag_dict = {}
        for key in tag_dict:
            new_tag_dict["_tag_" + key] = tag_dict[key]

        return new_tag_dict

    # To replace the target string from the cfg to the actual info
    def replace_target_info(self):
        logging.info("Replacing target information for hosts.")
        for host in self._cfg["config"]["host_details"]:
            target_list_new = []
            for name in host["targets"]:
                for target_global in self._cfg["targets"]:
                    if name == target_global["name"]:
                        target_list_new.append(target_global)
                        host["targets"] = list(target_list_new)
                        break

    def data_size_format(self, data):
        if data is None:
            data = "0"
        if data == 'None':
            data = "0"
        data = ''.join(i for i in data if i.isdigit())
        return long(data)

    def conv_b_to_mb(self, input_bytes):
        if input_bytes is None:
            input_bytes = 0
        if input_bytes == 'None':
            input_bytes = 0
        convert_mb = input_bytes / (1024 * 1024)
        return convert_mb

    # Utility functions for conversions and writer plugin
    def conv_kb_to_mb(self, input_kilobyte):
        if input_kilobyte is None:
            input_kilobyte = 0
        if input_kilobyte == 'None':
            input_kilobyte = 0
        convert_mb = input_kilobyte / 1024
        return convert_mb


    def log_debug(self, msg):
        """
           Logging method
        """
        logging.debug(self._plugin_name + msg)

    def log_info(self, msg):
        """
        Logging method
        """
        logging.info(self._plugin_name + msg)

    def log_warning(self, msg):
        """
        Logging method
        """
        logging.warning(self._plugin_name + msg)

    def log_error(self, msg):
        """
        Logging method
        """
        logging.error(self._plugin_name + msg)

    def log_critical(self, msg):
        """
        Logging method
        """
        logging.critical(self._plugin_name + msg)
