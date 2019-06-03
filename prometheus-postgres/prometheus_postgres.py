"""
*******************
*Copyright 2017, MapleLabs, All Rights Reserved.
*
********************
"""
from os import path

import re
import json
import sys
import logging
import shlex
import subprocess
import time
import requests

sys.path.append(path.dirname(path.dirname(path.abspath('prometheus_postgres.py'))))

from common import prometheus_poller,constants


class PrometheusPostgresStats(prometheus_poller.PrometheusStats):
    """
    class PrometheusPostgresStats
    """

    def __init__(self, cfg, port):
        """
        :param cfg:
        :param port:
        """
        super(PrometheusPostgresStats, self).__init__(cfg, port)
        self.poll_count = 0
        self.host = None
        self.port = None
        self.status = {}
        self.prometheus_regex = None
        self.exporter_metrics = None
        self.interval = None
        self.plugin_name = None
        self.status = {}
        self.es_documents = {}
        # self.metrics_file = "prometheus_regex.json"
        self.metrics_file = path.dirname(path.abspath('prometheus_linux.py')) + "/prometheus_regex.json"
        self.plugin_mapping = {}
        self.load_metrics_list(self.metrics_file)
        self.replace_target_info()


if __name__ == '__main__':
    PORT = int(sys.argv[1])
    CFG = json.loads(sys.argv[2])
    LOG_DIR = CFG["log_dir"]
    LOG_DIR = LOG_DIR.replace("'", "")
    LOG_FILE = path.join(LOG_DIR, "prometheus_linux" + "." + "log")
    logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, filemode='a',
                        format="[%(asctime)s] %(levelname)s [%(filename)s:%(funcName)s:%(lineno)s] %(message)s",
                        datefmt='%d/%b/%Y %H:%M:%S')
    OBJ = PrometheusPostgresStats(CFG, PORT)
    OBJ.start()
