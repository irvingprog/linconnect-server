'''
    LinConnect: Mirror Android notifications on Linux Desktop

    Copyright (C) 2013  Will Hauck

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

from __future__ import print_function

# Imports
import json
import os
import sys
import select
import threading
import platform

import cherrypy
import subprocess
from gi.repository import Notify
import pybonjour

version = "3"

# Global Variables
_notification_header = ""
_notification_description = ""

# Configuration
current_dir = os.path.abspath(os.path.dirname(__file__))
conf_file = os.path.join(current_dir, 'conf.json')

if os.path.exists(conf_file):
    with open(conf_file) as conf_json:
        print('Loading and open conf.json')
        conf = json.load(conf_json)
else:
    conf = {
        "connection": {
            "enable_bonjour": "1", 
            "port": "9090"
        }, 
        "other": {
            "enable_instruction_webpage": "1", 
            "notify_timeout": "5000"
        }
    }
    with open(conf_file, 'w') as conf_json:
        print('Making conf.json')
        json.dump(conf, conf_json, sort_keys=True, indent=4)

# Must append port because Java Bonjour library can't determine it
_service_name = platform.node()

icon_path = os.path.join(current_dir, "icon_cache.png")

class Notification(object):
    if int(conf['other']['enable_instruction_webpage']) == 1: 
        with open(os.path.join(current_dir, 'index.html'), 'rb') as f:
            _index_source = f.read()

        def index(self):
            return self._index_source % (version, get_local_ip("<br>"))

        index.exposed = True

    def notif(self, notificon):
        global _notification_header
        global _notification_description

        # Get icon
        try:
            os.remove("icon_cache.png")
        except:
            print("Creating icon cache...")
        file_object = open("icon_cache.png", "a")
        while True:
            data = notificon.file.read(8192)
            if not data:
                break
            file_object.write(str(data))
        file_object.close()

        # Ensure the notification is not a duplicate
        if (_notification_header != cherrypy.request.headers['NOTIFHEADER']) \
        or (_notification_description != cherrypy.request.headers['NOTIFDESCRIPTION']):

            # Get notification data from HTTP header
            _notification_header = cherrypy.request.headers['NOTIFHEADER'].replace('\x00', '').decode('iso-8859-1', 'replace').encode('utf-8')
            _notification_description = cherrypy.request.headers['NOTIFDESCRIPTION'].replace('\x00', '').decode('iso-8859-1', 'replace').encode('utf-8')

            # Send the notification
            notif = Notify.Notification.new(_notification_header, _notification_description, icon_path)
            if conf['other']['notify_timeout']:
                notif.set_timeout(int(conf['other']['notify_timeout']))
            try:
                notif.show()
            except:
                # Workaround for org.freedesktop.DBus.Error.ServiceUnknown
                Notify.uninit()
                Notify.init("com.willhauck.linconnect")
                notif.show()

        return "true"
    notif.exposed = True


def register_callback(sdRef, flags, errorCode, name, regtype, domain):
    if errorCode == pybonjour.kDNSServiceErr_NoError:
        print("Registered Bonjour service " + name)


def initialize_bonjour():
    sdRef = pybonjour.DNSServiceRegister(name=_service_name,
                                     regtype="_linconnect._tcp",
                                     port=int(conf['connection']['port']),
                                     callBack=register_callback)
    try:
        try:
            while True:
                ready = select.select([sdRef], [], [])
                if sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(sdRef)
        except KeyboardInterrupt:
            pass
    finally:
        sdRef.close()


def get_local_ip(delim):
    ips = ""
    for ip in subprocess.check_output("/sbin/ip address | grep -i 'inet ' | awk {'print $2'} | sed -e 's/\/[^\/]*$//'", shell=True).split("\n"):
        if "127" not in ip and ip.__len__() > 0:
            ips += "{0}:{1}{2}".format(ip, conf['connection']['port'],delim)
    return ips

# Initialization
if not Notify.init("com.willhauck.linconnect"):
    raise ImportError("Error initializing libnotify")

# Start Bonjour if desired
if int(conf['connection']['enable_bonjour']) == 1:
    thr = threading.Thread(target=initialize_bonjour)
    thr.start()

config_instructions = "Configuration instructions at http://localhost:" + conf['connection']['port']
print(config_instructions)
notif = Notify.Notification.new("Notification server started", config_instructions, "info")
notif.show()

cherrypy.server.socket_host = '0.0.0.0'
cherrypy.server.socket_port = int(conf['connection']['port'])

cherrypy.quickstart(Notification())
