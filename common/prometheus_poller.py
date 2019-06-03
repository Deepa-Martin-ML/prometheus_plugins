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

#sys.path.append(path.dirname(path.abspath('prometheus_poller.py')) + '/plugins')
#sys.path.append(path.dirname(path.dirname(path.abspath('prometheus_poller.py'))))

import plugin
from constants import *


class PrometheusStats(plugin.Plugin):
    """
    class PrometheusStats
    """

    def __init__(self, cfg, port):
        """
        :param cfg:
        :param port:
        """
        super(PrometheusStats, self).__init__(cfg, port)
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
        self.metrics_file = ""
        self.plugin_mapping = {}
        self.load_metrics_list(self.metrics_file)
        self.replace_target_info()

    def ping_server(self):
        """
        func : check if the server is reachable from the controller
        :return:
        """
        cmd = shlex.split("ping -c1 %s" % self.host)
        try:
            subprocess.check_output(cmd)
        except subprocess.CalledProcessError:
            self.status[self.host]["pingStatus"] = "Failed"
            logging.error("Ping to %s failed.", self.host)
        else:
            self.status[self.host]["pingStatus"] = "Success"
            logging.info("Ping to %s successfull", self.host)

    def instantiate_status_variables(self):
        """
        func: instantiate the status variables
        :return:
        """
        self.status[self.host] = {}

    def load_metrics_list(self, filepath):
        """
        load metric from file
        :return:
        """
        try:
            with self._lock:
                logging.info("loading metrics file... %s", filepath)
                with open(filepath, "r") as fin:
                    self.prometheus_regex = json.loads(fin.read())
        except Exception as err:
            logging.error(err)
            logging.error("Failed to load prometheus_metrics.json")

    def poll_metrics(self):
        '''
        func: Poll prometheus metrics from exporter running on the endpoint
        :return: prometheus metrics exposed by the exporter.
        '''
        try:
            logging.info("Establishing connection with prometheus exporter %s on host %s:%s"
                         , self.plugin_name, self.host, self.port)
            url = "http://{}:{}/metrics".format(self.host, self.port)
            headers = {'content-type': 'application/json'}
        except Exception as err:
            logging.error("Error constructing URL for prometheus exporter %s on host %s:%s."
                          , self.plugin_name, self.host, self.port)
            return

        try:
            logging.info("Sending GET request to exporter running on %s:%s \
                            for prometheus exporter %s."
                         , self.host, self.port, self.plugin_name)
            resp = requests.get(url, headers=headers, timeout=60)
        except Exception as err:
            logging.error("Error getting metrics from %s:%s for prometheus server %s."
                          , self.host, self.port, self.plugin_name)
            logging.error("%s", str(err))
            return

        if resp.status_code == 200:
            logging.info("Successfully polled metrics for host %s for metric %s"
                         , self.host, self.plugin_name)
            return resp.content

        logging.error("Response code for metrics request from %s:%s for prometheus server %s is %s."
                      , self.host, self.port, self.plugin_name, resp.status_code)

    def convert_metrics(self, prometheus_metrics):
        """
        func: Convert the metrics collected from the endpoint to a readable Json object
        :param plugin_detail:
        :return:
        """
        # TBA : Convert only those metrics to Json object which is mentioned
        # in prometheus_regex.json.

        logging.info("Converting the metrics to Json format for further processing for \
                        host %s for plugin %s."
                     , self.host, self.plugin_name)
        prometheus_json = {}
        prometheus_json["host"] = self.host
        prometheus_json["port"] = self.port
        prometheus_json[self.plugin_name] = {}
        metric_dict = {}
        metric_dict["metrics"] = []
        document_name = None
        count = 0
        for line in prometheus_metrics.splitlines():
            try:
                count += 1
                if "# HELP" in line:
                    document_name = line.split(" ")[2]
                    logging.info("Converting metrics to json for host %s for \
                                    plugin %s for document %s"
                                 , self.host, self.plugin_name, document_name)
                    prometheus_json[self.plugin_name][document_name] = {}
                    metric_dict["HELP"] = " ".join(line.split(" ")[3:])
                    continue

                elif "# TYPE" in line:
                    metric_dict["TYPE"] = line.split(" ")[3]
                    continue

                else:
                    metric = {}
                    if "{" in line:
                        if "}" in line:
                            items = line.split("{")[1].split("} ")[0].split(",")
                        else:
                            items = line.split("{")[1].split(" ")[0].strip("}").split(",")

                        for item in items:
                            # metric[re.sub('[^A-Za-z0-9.]+', '', item.split("=")[0])] = \
                            #     re.sub('[^A-Za-z0-9.]+', '', item.split("=")[1])
                            metric[re.sub('[^A-Za-z0-9/()-_.]+', '', item.split("=")[0])] = \
                                re.sub('[^A-Za-z0-9/()-_.]+', '', item.split("=")[1])
                    if "}" in line:
                        metric["value"] = line.split("} ")[1]
                    else:
                        metric["value"] = line.split(" ")[1]
                    metric["flag"] = False
                    metric_dict["metrics"].append(metric)

                    if count == len(prometheus_metrics.splitlines()):
                        prometheus_json[self.plugin_name][document_name] = metric_dict
                        break

                    elif "# HELP" in prometheus_metrics.splitlines()[count]:
                        prometheus_json[self.plugin_name][document_name] = metric_dict
                        metric_dict = {}
                        metric_dict["metrics"] = []

            except Exception as err:
                logging.error("Error converting file based metrics from %s:%s for \
                                prometheus plugin %s to dictionary format."
                              , self.host, self.port, self.plugin_name)
                logging.error("%s", str(err))
                return

        logging.info("Successfully converted the metrics collected from \
                    host %s for plugin %s to dictionary format",
                     self.host, self.plugin_name)
        return prometheus_json

    def write_mapping(self):
        """
        func: Write mapping details to plugin_mapping.json.
        :return:
        """
        # Multiple workloads can try to write to the same plugin_mapping.json file,
        # this needs to br properly serialized, what we can do presently is write
        # self.plugin_mapping manually to this file and commit it to master.
        pass

    def create_mapping(self, mapping_key=None, metric_key=None, metric_value=None, aggregator=None, no_info=False):
        """
        mapping_key : Actual key for plugin_mapping.json which may be
                        modified using label or record_classifier.
        metric_key : The key provided by prometheus to extract teh HELP and TYPE.
        metric_value : The metric_value in prometheus_regex.json containing the DOCUMENTTYPE.
        aggregator : AGGREGATOR like SUM, MAX, MIN, AVG provided which needs to be
                        appended to mapping_key.
        no_info : If True add the mapping_key to self.plugin_mapping without any
                        DESC, UNIT and DATATYPE
        func: Populate plugin_mapping.json for the documents created
        :return:
        """

        logging.debug("Update self.plugin_mapping for metric: %s of plugin: %s.",
                      mapping_key, self.plugin_name)
        mapping = {}
        try:
            if no_info:
                mapping[mapping_key] = {}
                mapping[mapping_key]["Datatype"] = ""
                mapping[mapping_key]["Label"] = mapping_key.replace("_", " ").title()
                mapping[mapping_key]["Desc"] = ""
                mapping[mapping_key]["Unit"] = ""
            else:
                if aggregator:
                    mapping_key = str(aggregator).lower() + "_" + mapping_key

                mapping[mapping_key] = {}
                mapping[mapping_key]["Datatype"] = ""
                mapping[mapping_key]["Label"] = mapping_key.replace("_", " ").title()
                if aggregator:
                    mapping[mapping_key]["Desc"] = "[" + str(aggregator) + "] " + str(
                        self.exporter_metrics[self.plugin_name][metric_key]["HELP"])
                else:
                    mapping[mapping_key]["Desc"] = self.exporter_metrics[self.plugin_name][metric_key]["HELP"]

                mapping[mapping_key]["Unit"] = self.exporter_metrics[self.plugin_name][metric_key]["TYPE"]

            if metric_value[DOCUMENTTYPE] not in self.plugin_mapping[self.plugin_name]:
                self.plugin_mapping[self.plugin_name][metric_value[DOCUMENTTYPE]] = []

            for item in self.plugin_mapping[self.plugin_name][metric_value[DOCUMENTTYPE]]:
                if item.get(mapping_key):
                    return

            self.plugin_mapping[self.plugin_name][metric_value[DOCUMENTTYPE]].append(mapping)
            logging.info("Successfully added metric: %s to plugin_mapping for plugin: %s _documentType: %s",
                         mapping_key, self.plugin_name, metric_value[DOCUMENTTYPE])

        except Exception as error:
            logging.error("Failed to create mapping for metric %s due to error %s.", mapping_key, error)
            return

    def result_transformation(self, value, transformation_rule):
        """
        func : Transform the result into the desired unit.
        DIV :DIVIDE value by transformation_rule["DIV"]
        MUL :MULTIPLY value by transformation_rule["DIV"]
        :return:
        """
        try:
            for operation, unit in transformation_rule.items():
                if operation == "DIV":
                    logging.info("Operation: %s being performed on value: %s by units: %s.",
                                 operation, value, unit)
                    value = value / unit
                elif operation == "MUL":
                    logging.info("Operation: %s being performed on value: %s by units: %s.",
                                 operation, value, unit)
                    value = value * unit
            return value

        except ZeroDivisionError as error:
            logging.error("Error in result_transformation %s.", error)
            return

    def result_aggregation(self, aggregator, list):
        """
        func: Aggregating teh results SUM, MIN, MAX, AVG
        :return:
        """
        if aggregator == "SUM":
            return sum(list)
        elif aggregator == "AVG":
            return float(sum(list))/len(list)
        elif aggregator == "MAX":
            return max(list)
        elif aggregator == "MIN":
            return min(list)

    def filter_rule(self, item, filter_rule):
        """

        :return:
        """
        flag = True
        if any(filter_rule["must"]):
            for key, value in filter_rule["must_not"].items():
                if isinstance(value, list):
                    if item[key] not in value:
                        return False
                else:
                    if item[key] != value:
                        return False
        if any(filter_rule["must_not"]):
            for key, value in filter_rule["must_not"].items():
                if isinstance(value, list):
                    if item[key] in value:
                        return False
                else:
                    if item[key] == value:
                        return False
        return flag

    def prometheus_expression_1(self, metric_key, metric_value):
        """
        func: Match the simple regular expression and create ES documents
        expression : apache_accesses_total = value
        :return: ES documents for the matching regex.
        filter_rule : NA
        record_classifier : NA
        aggregation : NA
        _documentType : MANDATORY
        result_transformation : OPTIONAL
        label : OPTIONAL
        """

        try:
            logging.debug("Polling for metric: %s of plugin: %s.", metric_key, self.plugin_name)
            document = {}
            label = metric_value[0]["label"]
            if label == "":
                label = metric_key

            # Find metric value
            # NOTE: metrics will always have a single element in this case.
            document[label] = float(self.exporter_metrics[self.plugin_name][metric_key]["metrics"][0]["value"])

            # Implement result transformation
            if any(metric_value[0]["result_transformation"]):
                logging.debug("Applying result transformation for metric: %s of plugin: %s.", metric_key,
                              self.plugin_name)
                document[label] = self.result_transformation(document[label], metric_value[0]["result_transformation"])

            # Check if DOCUMENTTYPE is present in self.es_documents
            if not self.es_documents.get(metric_value[0][DOCUMENTTYPE]):
                self.es_documents[metric_value[0][DOCUMENTTYPE]] = []

            # Update document to es_documents
            self.es_documents[metric_value[0][DOCUMENTTYPE]].append(document)

            if self.poll_count == 0:
                logging.debug("Creating mapping for metric %s of plugin %s in first poll.", label, self.plugin_name)
                # Create plugin_mapping file
                self.create_mapping(mapping_key=label, metric_key=metric_key, metric_value=metric_value[0])

            return

        except Exception as error:
            logging.error("Failed to create document and mapping for metric %s of plugin %s due to error: %s.",
                          metric_key,
                          self.plugin_name, error)
            return

    def prometheus_expression_2(self, metric_key, metric_value):
        """
        func: Match the regular expression and create ES documents
        expression : node_procs_* = value
        :return: ES documents for the matching regex.
        filter_rule : NA
        record_classifier : NA
        aggregation : OPTIONAL
        _documentType : MANDATORY
        result_transformation : OPTIONAL
        label : MANDATORY
        """

        try:
            logging.debug("Polling for metric %s for plugin %s.", metric_key, self.plugin_name)
            metric_key = metric_key.replace("_*", "")
            for expression in metric_value:
                document = {}
                aggregation = []
                for key, value in self.exporter_metrics[self.plugin_name].items():
                    if key.startswith(metric_key):
                        if expression["label"] == "":
                            label = key
                        else:
                            label = str(key).replace(metric_key, expression["label"])

                        #document[label] = float(value["metrics"][0]["value"])
                        document[label] = (value["metrics"][0]["value"])
                        aggregation.append(document[label])

                        # Apply result transformation
                        if any(expression["result_transformation"]):
                            document[label] = self.result_transformation(document[label],
                                                                         expression["result_transformation"])

                        # Create plugin_mapping
                        if self.poll_count == 0:
                            self.create_mapping(mapping_key=label, metric_key=key, metric_value=expression)

                # Check if DOCUMENTTYPE is present in self.es_documents
                if not self.es_documents.get(expression[DOCUMENTTYPE]):
                    self.es_documents[expression[DOCUMENTTYPE]] = []

                for aggregator in expression["aggregation"]:
                    if expression["label"]:
                        document[str(aggregator).lower() + "_" + expression["label"]] = self.result_aggregation(
                            aggregator, aggregation)
                    else:
                        document[str(aggregator).lower() + "_" + metric_key] = self.result_aggregation(aggregator,
                                                                                                       aggregation)

                self.es_documents[expression[DOCUMENTTYPE]].append(document)

            return

        except Exception as error:
            logging.error("Failed to create document and mapping for metric %s of plugin %s due to error: %s.",
                          metric_key, self.plugin_name, error)
            return

    def prometheus_expression_3(self, metric_key, metric_value):
        """
        func: Match the regular expression and create ES documents
        expression : node_cpu{*} = value
        :return: ES documents for the matching regex.
        filter_rule : OPTIONAL
        record_classifier : OPTIONAL
        aggregation : OPTIONAL
        _documentType : MANDATORY
        result_transformation : OPTIONAL
        label : OPTIONAL
        """
        try:
            logging.debug("Polling for metric %s for plugin %s.", metric_key, self.plugin_name)
            metric_key = metric_key.replace("{*}", "")
            for expression in metric_value:
                len_record_classifier = len(expression["record_classifier"]["classifiers"])
                len_aggregation = len(expression["aggregation"])

                if expression["label"] == "":
                    label = metric_key
                elif isinstance(expression['label'], dict):
                    label = expression['label']
                else:
                    label = expression["label"]

                # SUBCASE 01 : record_classifer : present, aggregation : present
                # check if prefix
                if expression["record_classifier"][PREFIX] is True:
                    # TBA : When prefix is true this case will genearally not appear in case of multiple attributes
                    pass
                else:
                    if len_record_classifier > 0 and len_aggregation > 0:
                        logging.debug("metric %s fall in category prometheus_expression_3 SUBCASE 01.", metric_key)
                        metrics = self.exporter_metrics[self.plugin_name][metric_key]["metrics"]
                        unique = {}
                        for metrics1 in range(0, len(metrics)):
                            if metrics[metrics1]["flag"]:
                                continue
                            document = {}
                            for classifier in expression["record_classifier"]["classifiers"]:
                                unique[classifier] = metrics[metrics1][classifier]
                                document[classifier] = metrics[metrics1][classifier]
                                self.create_mapping(classifier, metric_value=expression, no_info=True)

                            aggregation = []

                            for metrics2 in range(metrics1, len(metrics)):
                                if metrics[metrics2]["flag"]:
                                    continue

                                # Check for filter rule
                                if not self.filter_rule(metrics[metrics2], expression["filter_rule"]):
                                    continue

                                unique_flag = True
                                for classifier in expression["record_classifier"]["classifiers"]:
                                    if metrics[metrics2][classifier] == unique[classifier]:
                                        continue
                                    else:
                                        unique_flag = False
                                        break

                                if unique_flag is True:
                                    aggregation.append(float(metrics[metrics2]["value"]))
                                    metrics[metrics2]["flag"] = True

                                if metrics2 == (len(metrics) - 1):
                                    # Check if DOCUMENTTYPE is present in self.es_documents
                                    if not self.es_documents.get(expression[DOCUMENTTYPE]):
                                        self.es_documents[expression[DOCUMENTTYPE]] = []

                                    for aggregator in expression["aggregation"]:
                                        # Apply aggregation rule
                                        document[str(aggregator).lower() + "_" + label] = self.result_aggregation(
                                            aggregator, aggregation)

                                        # Apply result transformation
                                        if any(expression["result_transformation"]):
                                            document[
                                                str(aggregator).lower() + "_" + label] = \
                                                self.result_transformation(
                                                    document[str(aggregator).lower() + "_" + expression["label"]],
                                                    expression["result_transformation"])

                                        self.es_documents[expression[DOCUMENTTYPE]].append(document)

                                        # Create plugin_mapping
                                        if self.poll_count == 0:
                                            self.create_mapping(mapping_key=label, metric_key=metric_key,
                                                                metric_value=expression, aggregator=aggregator)

                # SUBCASE 02 : record_classifer : present, aggregation : absent
                # In this case it will output all the documents with all the attributes

                if len_record_classifier > 0 and len_aggregation == 0:

                    logging.debug("metric %s fall in category prometheus_expression_3 SUBCASE 02.", metric_key)
                    for item in self.exporter_metrics[self.plugin_name][metric_key]["metrics"]:
                        # Check if item obeys the filter rule
                        if not self.filter_rule(item, expression["filter_rule"]):
                            continue

                        document = {}
                        # Check for prefix
                        if expression["record_classifier"]["prefix"] is True:
                            sub_label = ""
                            for classifier in expression["record_classifier"]["classifiers"]:
                                sub_label = item[classifier] + "_" + label
                            document[sub_label] = float(item["value"])

                            # Apply result transformation
                            if any(expression["result_transformation"]):
                                document[sub_label] = self.result_transformation(document[sub_label],
                                                                                 expression["result_transformation"])

                            # Check if DOCUMENTTYPE is present in self.es_documents
                            if not self.es_documents.get(expression[DOCUMENTTYPE]):
                                self.es_documents[expression[DOCUMENTTYPE]] = []

                            # Add mapping keys
                            if self.poll_count == 0:
                                self.create_mapping(sub_label, metric_key=metric_key, metric_value=expression,
                                                    no_info=True)

                            self.es_documents[expression[DOCUMENTTYPE]].append(document)

                        else:
                            document.update(item)
                            document.pop("value")
                            document.pop("flag")
                            if isinstance(label, dict):
                                if label.get("prefix"):
                                    document[item[label["classifier"]] + label["prefix"]] = float(item["value"])
                                else:
                                    document[item[label["classifier"]]] = float(item["value"])
                                document.pop(label["classifier"])
                            else:
                                document[label] = float(item["value"])

                            # Apply result transformation
                            if any(expression["result_transformation"]):
                                document[label] = self.result_transformation(document[label],
                                                                             expression["result_transformation"])

                            # Check if DOCUMENTTYPE is present in self.es_documents
                            if not self.es_documents.get(expression[DOCUMENTTYPE]):
                                self.es_documents[expression[DOCUMENTTYPE]] = []

                            if self.poll_count == 0:
                                if isinstance(label, dict):
                                    self.create_mapping(item[label["classifier"]], metric_key, expression)
                                else:
                                    self.create_mapping(label, metric_key, expression)
                                for key in document.keys():
                                    if key not in ["prefix", label]:
                                        self.create_mapping(key, metric_value=expression, no_info=True)

                            self.es_documents[expression[DOCUMENTTYPE]].append(document)

                # SUBCASE 03 : record_classifer : absent, aggregation : present
                if len_record_classifier == 0 and len_aggregation > 0:
                    logging.debug("metric %s fall in category prometheus_expression_3 SUBCASE 03.", metric_key)
                    logging.warning("This functionality has not been implemented, as it is a corner case.")
                    # TBA : It's a corner case, handle when required.

                # SUBCASE 04 : record_classifer : absent, aggregation : absent
                if len_record_classifier == 0 and len_aggregation == 0:
                    logging.debug("metric %s fall in category prometheus_expression_3 SUBCASE 04.", metric_key)
                    logging.warning("This functionality has not been implemented, as it is a corner case.")
                    document ={}
                    for item in self.exporter_metrics[self.plugin_name][metric_key]["metrics"]:
                        document.update(item)
                        document.pop("value")
                        document.pop("flag")
                        document[label] = item["value"]

                        if self.poll_count == 0:
                            for key in document.keys():
                                self.create_mapping(key, metric_value=expression, no_info=True)

                    self.es_documents[expression[DOCUMENTTYPE]].append(document)
                    # TBA : It's a corner case, handle when required.

                return
        except Exception as error:
            logging.error("Failed to create document and mapping for metric: %s of plugin: %s due to error: %s.",
                          metric_key, self.plugin_name, error)
            return

    def prometheus_expression_4(self, metric_key, metric_value):
        """
        func: Match the regular expression and create ES documents
        expression : node_disk_*{*} = value
        :return: ES documents for the matching regex.
        filter_rule : OPTIONAL
        record_classifier : OPTIONAL
        aggregation : OPTIONAL
        _documentType : MANDATORY
        result_transformation : OPTIONAL
        label : MANDATORY
        """
        metric_key = metric_key.replace("_*{*}", "")
        for expression in metric_value:
            len_record_classifier = len(expression["record_classifier"])
            len_aggregation = len(expression["aggregation"])

            # SUBCASE 01 : record_classifer : present, aggregation : present
            if len_record_classifier > 0 and len_aggregation > 0:
                logging.debug("metric %s fall in category prometheus_expression_4 SUBCASE 01.", metric_key)
                logging.warning("This functionality has not been implemented, as it is a corner case.")
                # TBA : It's a corner case, handle when required.

            # SUBCASE 02 : record_classifer : present, aggregation : absent
            # In this case it will output all the documents with all the attributes
            if len_record_classifier > 0 and len_aggregation == 0:
                logging.debug("metric %s fall in category prometheus_expression_4 SUBCASE 02.", metric_key)
                sub_documents = []
                for key, value in self.exporter_metrics[self.plugin_name].items():
                    if key.startswith(metric_key):
                        for item in value["metrics"]:

                            # Check for filter rule
                            if not self.filter_rule(item, expression["filter_rule"]):
                                continue

                            if expression["label"]:
                                label = str(key).replace(metric_key, expression["label"])
                            else:
                                label = key

                            flag = True
                            for doc in sub_documents:
                                for classifier in expression["record_classifier"]["classifiers"]:
                                    if item[classifier] == doc[classifier]:
                                        doc[str(key).replace(metric_key, expression["label"])] = item["value"]
                                        if self.poll_count == 0:
                                            self.create_mapping(mapping_key=label, metric_key=key,
                                                                metric_value=expression)
                                        flag = False

                            if flag:
                                document = {}
                                for classifier in expression["record_classifier"]["classifiers"]:
                                    document[classifier] = item[classifier]
                                    if self.poll_count == 0:
                                        self.create_mapping(mapping_key=classifier, metric_value=expression,
                                                            no_info=True)

                                document[label] = item["value"]

                                # Apply result transformation
                                if any(expression["result_transformation"]):
                                    document[label] = self.result_transformation(label,
                                                                                 expression["result_transformation"])

                                if self.poll_count == 0:
                                    self.create_mapping(mapping_key=label, metric_key=key, metric_value=expression)

                                sub_documents.append(document)

                # Check if DOCUMENTTYPE is present in self.es_documents
                if not self.es_documents.get(expression[DOCUMENTTYPE]):
                    self.es_documents[expression[DOCUMENTTYPE]] = []
                for doc in sub_documents:
                    self.es_documents[expression[DOCUMENTTYPE]].append(doc)

            # SUBCASE 03 : record_classifer : absent, aggregation : present
            if len_record_classifier == 0 and len_aggregation > 0:
                logging.debug("metric %s fall in category prometheus_expression_4 SUBCASE 03.", metric_key)
                logging.warning("This functionality has not been implemented, as it is a corner case.")
                # TBA : It's a corner case, handle when required.

            # SUBCASE 04 : record_classifer : absent, aggregation : absent
            if len_record_classifier == 0 and len_aggregation == 0:
                logging.debug("metric %s fall in category prometheus_expression_4 SUBCASE 04.", metric_key)
                logging.warning("This functionality has not been implemented, as it is a corner case.")
                # TBA : It's a corner case, handle when required.
            return

    def match_regex(self, metric_key, metric_value):
        """
        func: Match the regular expression for prometheus transformation
        and call the appropriate function.
        :return: ES documents for the matching regex.
        """

        logging.info("Matching regular expression for metric: %s of plugin: %s", metric_key, self.plugin_name)
        if metric_key.endswith("_*"):
            return self.prometheus_expression_2(metric_key, metric_value)

        elif metric_key.endswith("_*{*}"):
            return self.prometheus_expression_4(metric_key, metric_value)

        elif metric_key.endswith("{*}"):
            return self.prometheus_expression_3(metric_key, metric_value)

        else:
            return self.prometheus_expression_1(metric_key, metric_value)

    def add_common_params(self, es_document):
        """
        func: Add common parameters to the document created.
        :return:
        """
        es_document[PLUGIN] = self.plugin_name
        es_document[HOST] = self.host
        es_document[TIME] = int(round(time.time()))
        return es_document


    def merge_documents(self):
        """
        func : Merge all the documents with same DOCUMENTTYPE
        :return:
        """
        final_documents = []
        for document_type, documents in self.es_documents.items():
            #CASE 01: All the keys in every document is identical.
            # if len(documents[0].keys()) == len(self.plugin_mapping[self.plugin_name][document_type]):
            if len(documents[0].keys()) == len(self.plugin_mapping[self.plugin_name][document_type]):
                logging.info("All the mapping entries for documentType %s are present in document %s, "
                             "hence post all the documents separately to ES", document_type, documents[0])
                for document in documents:
                    document[DOCUMENTTYPE] = document_type
                    final_documents.append(document)

            #CASE 02: Some keys but all are identical in all the documents
            # 1. Find the identical keys
            # 2. Merge the documents with same identical key values
            elif len(documents[0].keys()) < len(self.plugin_mapping[self.plugin_name][document_type]) and len(set(documents[0].keys()) & set(documents[1].keys())) > 1:
                identical_keys = list(set(documents[0].keys()) & set(documents[1].keys()))
                # identical_keys = []
                for idx, document in enumerate(documents):
                    if idx == (len(documents) - 1):
                        break
                    identical_keys = list(set(identical_keys) & set(documents[idx + 1].keys()))

                identical_documents = {}
                for document in documents:
                    hash_key = ""
                    for key in identical_keys:
                        if hash_key == "":
                            hash_key += str(document[key])
                        else:
                            hash_key += "_" + str(document[key])
                    if identical_documents.get(hash_key):
                        identical_documents[hash_key].update(document)
                    else:
                        identical_documents[hash_key] = document

                for document in identical_documents.values():
                    document[DOCUMENTTYPE] = document_type
                    final_documents.append(document)

            #CASE 03: All the keys in every document is unique.
            else:
                logging.info("Merging all the documents for document_type %s together.", document_type)
                merged_document = {}
                for document in documents:
                    merged_document.update(document)
                merged_document[DOCUMENTTYPE] = document_type
                final_documents.append(merged_document)

        return final_documents

    def poll(self):
        """
        func : Poll for prometheus metrics in regular polling interval
                and send the documents to datasource.
        :return:
        """

        host_details = self._cfg["config"]["host_details"]
        self.plugin_name = self._cfg["name"]
        if self.poll_count == 0:
            self.plugin_mapping[self.plugin_name] = {}

        workload_tags = self.convert_tag_keys(self._cfg["config"]["tags"])
        for host_detail in host_details:
            target_details = host_detail["targets"]
            self.host = host_detail["ip"]
            self.port = host_detail["port"]
            logging.info("Polling metrics for host %s for plugin %s.", self.host, self.plugin_name)
            host_tags = self.convert_tag_keys(host_detail["tags"])
            tags = workload_tags.copy()
            tags.update(host_tags)
            logging.info("Configured tags at host and workload level for host %s: %s"
                         , self.host, tags)
            self.instantiate_status_variables()

            self.ping_server()

            if self.status[self.host]["pingStatus"] == "Success":
                try:
                    es_documents = []

                    # Poll metrics from the exporter running on the endpoint.
                    prometheus_metrics = self.poll_metrics()

                    # Raise exception if prometheus exporter is not running
                    if prometheus_metrics is None:
                        logging.error("Prometheus exporter is not running on host %s for plugin %s", self.host,
                                      self.plugin_name)
                        raise Exception("Exporter not running exception.")

                    # Convert the metrics file to a Json object for processing.
                    self.exporter_metrics = self.convert_metrics(prometheus_metrics)

                    # Read the regex file and create ES documents.
                    for metric_key, metric_value in self.prometheus_regex[self.plugin_name].items():
                        try:
                            logging.info("Applying transformation rules for metric: %s of plugin: %s", metric_key,
                                         self.plugin_name)
                            documents = self.match_regex(metric_key, metric_value)

                        except Exception as error:
                            logging.error("Metric: %s of plugin: %s did not create any document due to error %s.",
                                          metric_key,
                                          self.plugin_name, error)
                    # Create final documents depending on DOCUMENTTYPE
                    final_documents = self.merge_documents()

                    # Add tags to each ES_document
                    for document in final_documents:
                        document.update(tags)
                        document = self.add_common_params(document)
                        es_documents.append(document)

                    for target in target_details:
                        if target["type"] == "elasticsearch":
                            res = self.write_to_elastic(es_documents, target)
                            if res.status_code == 201:
                                logging.info(
                                    "Successfully sent ES documents for host: %s and \
                                        plugin: %s to datasource"
                                    , self.host, self.plugin_name)
                            else:
                                logging.error("Failed to send ES documents for host: %s and "
                                              "plugin: %s to datasource"
                                              , self.host, self.plugin_name)

                except Exception as err:
                    logging.error("%s", str(err))
                    logging.error("Poll failed for host: %s for plugin: %s", self.host, self.plugin_name)
            else:
                logging.error("Failed to ping the host: %s", self.host)

        self.poll_count += 1

    # To get the status of the poll from the MySQL server
    def get_status(self):
        resp_status = {}
        resp_status["prometheus"] = self.status
        self.status["running"] = self._running
        return True, resp_status


if __name__ == '__main__':
    PORT = int(sys.argv[1])
    CFG = json.loads(sys.argv[2])
    LOG_DIR = CFG["log_dir"]
    LOG_DIR = LOG_DIR.replace("'", "")
    LOG_FILE = path.join(LOG_DIR, "prometheus" + "." + "log")
    logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, filemode='a',
                        format="[%(asctime)s] %(levelname)s [%(filename)s:%(funcName)s:%(lineno)s] %(message)s",
                        datefmt='%d/%b/%Y %H:%M:%S')
    OBJ = PrometheusStats(CFG, PORT)
    OBJ.start()
