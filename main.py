#!/usr/bin/python

""" Copyright (c) 2020 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
           https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied. 
"""

import serial
import time
import json
import signal
import threading
import logging
import requests
import os
from dotenv import load_dotenv

from wsgiref.simple_server import make_server

def _sleep_handler(signum, frame):
    print("SIGINT Received. Stopping CAF")
    raise KeyboardInterrupt

def _stop_handler(signum, frame):
    print("SIGTERM Received. Stopping CAF")
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, _stop_handler)
signal.signal(signal.SIGINT, _sleep_handler)

PORT = 8000
HOST = "0.0.0.0"

load_dotenv()

class SerialThread(threading.Thread):
    def __init__(self):
        super(SerialThread, self).__init__()
        self.name = "SerialThread"
        self.setDaemon(True)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        INTERVAL = 10 # Interval between publishing in seconds
        URL = "https://www.fleeteyes.com/vehicle_update/cad_interface" # URL to post GPS data to

        FE_COMPANY_ID="<your-fleeteyes-company-id>"
        FE_USERNAME="<your-fleeteyes-username>"
        FE_PASSWORD="<your-fleeteyes-password>"
        FE_DEVICE_ID="<your-fleeteyes-device-id>"
        FE_DEVICE_NAME="<your-fleeteyes-device-name>"

        # Set up serial device
        serial_dev = os.getenv("gps1")
        if serial_dev is None:
            serial_dev="/dev/ttyNMEA1"

        sdev = serial.Serial(port=serial_dev)
        sdev.timeout = 5
        print("Serial:  %s\n", sdev)

        # Set up application logging
        try:
            directory = os.environ['CAF_APP_LOG_DIR'] + "/"
        except KeyError as e:
            directory = "./"
        logger = logging.getLogger('webapp')
        logger.setLevel(logging.INFO)
        file_handler = logging.FileHandler(directory + 'gps_data.log')
        formatter = logging.Formatter('%(msg)s')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Using serial port: {serial_dev}")
        
        # Main loop
        while True:
            if self.stop_event.is_set():
                break
            quality = None
            altitude = None
            
            while sdev.inWaiting() > 0:
                sensVal = sdev.readline()
                sensVal = sensVal.decode().split(",")
                format = sensVal[0][1:]

                # NMEA data formats: https://anavs.com/knowledgebase/nmea-format/
                if format == "GPGGA":
                    quality = sensVal[6]
                    altitude = sensVal[9]
                elif format == "GPRMC" and sensVal[2] == "A" and quality is not None:
                    payload = "<data>" + \
                                "<company>"  + \
                                    f"<id>{FE_COMPANY_ID}</id>"  + \
                                    f"<username>{FE_USERNAME}</username>"  + \
                                    f"<password>{FE_PASSWORD}</password>"  + \
                                "</company>"  + \
                                "<vehicles>"  + \
                                    "<vehicle>"  + \
                                        f"<id>{FE_DEVICE_ID}</id>"  + \
                                        f"<name>{FE_DEVICE_NAME}</name>"  + \
                                        "<status>Available</status>"  + \
                                        "<incidentid></incidentid>"  + \
                                        "<crew></crew>"  + \
                                        f"<latitude>{('' if sensVal[4]=='N' else '-') + str(float(sensVal[3][:2]) + (float(sensVal[3][2:])/60.0))}</latitude>"  + \
                                        f"<longitude>{('' if sensVal[6]=='E' else '-') + str(float(sensVal[5][:3]) + (float(sensVal[5][3:])/60.0))}</longitude>"  + \
                                        f"<speed>{float(sensVal[7])}</speed>"  + \
                                        f"<altitude>{altitude}</altitude>"  + \
                                        f"<heading>{sensVal[8]}</heading>" + \
                                    "</vehicle>" + \
                                "</vehicles>" + \
                                "<incidents>" + \
                                "</incidents>" + \
                            "</data>"

                    logger.info(f"Sent to FleetEyes (payload): {payload}")
                    
                    time.sleep(INTERVAL)

                    resp = requests.post(f"{URL}?data={payload}", headers={"Content-Type" : "application/xml"}, data=payload, verify=False)
                    logger.info(f"Response from FleetEyes (status code): {resp.status_code}")
                    logger.info(f"Response from FleetEyes (text): {resp.text}")
        sdev.close()

def simple_app(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'application/json')]
    start_response(status, headers)
    ret = json.dumps({"response" : "OK"})
    return ret

httpd = make_server(HOST, PORT, simple_app)
try:
    p = SerialThread()
    p.start()
    httpd.serve_forever()
except KeyboardInterrupt:
    p.stop()
    httpd.shutdown()