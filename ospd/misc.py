# $Id$
# Description:
# Miscellaneous classes and functions related to OSPD.
#
# Authors:
# Hani Benhabiles <hani.benhabiles@greenbone.net>
#
# Copyright:
# Copyright (C) 2014 Greenbone Networks GmbH
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2,
# or, at your option, any later version as published by the Free
# Software Foundation
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
#/

import uuid
import datetime
import argparse
import os

KEY_FILE = "/usr/var/lib/openvas/private/CA/clientkey.pem"
CERT_FILE = "/usr/var/lib/openvas/CA/clientcert.pem"
CA_FILE = "/usr/var/lib/openvas/CA/cacert.pem"
TIMEOUT = 3600
PORT = 1234
ADDRESS = "0.0.0.0"

class OSPLogger():
    """ Class to handle outputting log, debug and error messages. """

    def __init__(self, level=0):
        """ Initialize the instance. """

	self.level = level

    def set_level(self, level):
        """ Set the debugging level. """

	self.level = level

    def debug(self, level, message):
        """ Output a debug message if the provided level is equal or higher than
        the logger's.

        """

	if self.level >= level:
	    print 'DEBUG: {0}'.format(message)

    def error(self, message):
        """ Output an error message. """

        print 'ERROR: {0}'.format(message)

class ScanCollection(object):
    """ Scans collection, managing scans and results read and write, exposing
    only needed information.

    Each scan has meta-information such as scan ID, current progress (from 0 to
    100), start time, end time, scan target and options and a list of results.

    There are 3 types of results: Alarms, Logs and Errors.

    Todo:
    - Better checking for Scan ID existence and handling otherwise.
    - More data validation.
    - Mutex access per table/scan_info.

    """

    def __init__(self):
        """ Initialize the Scan Collection. """

        self.scans_table = dict()

    def add_alarm(self, scan_id, name="", value=""):
        """ Add a result of type Alarm to a scan in the table. """

        self.scans_table[scan_id]['results'].append((ResultType.ALARM, name,
                                                     value))

    def add_log(self, scan_id, name="", value=""):
        """ Add a result of type Log to a scan in the table. """

        self.scans_table[scan_id]['results'].append((ResultType.LOG, name,
                                                     value))

    def add_error(self, scan_id, name="", value=""):
        """ Add a result of type Error to a scan in the table. """

        self.scans_table[scan_id]['results'].append((ResultType.ERROR, name,
                                                     value))

    def set_progress(self, scan_id, progress):
        """ Sets scan_id scan's progress. """

        if progress > 0 and progress <= 100:
            self.scans_table[scan_id]['progress'] = progress
        if progress == 100:
            self.scans_table[scan_id]['end_time'] = datetime.datetime.now().strftime('%s')

    def results_iterator(self, scan_id):
        """ Returns an iterator over scan_id scan's results. """

        return iter(self.scans_table[scan_id]['results'])

    def ids_iterator(self):
        """ Returns an iterator over the collection's scan IDS. """

        return iter(self.scans_table.keys())

    def create_scan(self, target, options):
        """ Creates a new scan with provided target and options. """

        scan_info = dict()
        scan_info['results'] = list()
        scan_info['progress'] = 0
        scan_info['target'] = target
        scan_info['options'] = options
        scan_info['start_time'] = datetime.datetime.now().strftime('%s')
        scan_info['end_time'] = "0"
        scan_id = str(uuid.uuid4())
        scan_info['scan_id'] = scan_id
        self.scans_table[scan_id] = scan_info
        return scan_id

    def get_options(self, scan_id):
        """ Get scan_id scan's options list. """

        return self.scans_table[scan_id]['options']

    def set_option(self, scan_id, name, value):
        """ Set a scan_id scan's name option to value. """

        self.scans_table[scan_id]['options'][name] = value

    def get_progress(self, scan_id):
        """ Get a scan's current progress value. """

        return self.scans_table[scan_id]['progress']

    def get_start_time(self, scan_id):
        """ Get a scan's start time. """

        return self.scans_table[scan_id]['start_time']

    def get_end_time(self, scan_id):
        """ Get a scan's end time. """

        return self.scans_table[scan_id]['end_time']

    def get_target(self, scan_id):
        """ Get a scan's target. """

        return self.scans_table[scan_id]['target']

    def id_exists(self, scan_id):
        """ Check whether a scan exists in the table. """

        return self.scans_table.get(scan_id) is not None

    def delete_scan(self, scan_id):
        """ Delete a scan if fully finished. """

        if self.get_progress(scan_id) < 100:
            return False
        self.scans_table.pop(scan_id)
        return True

class ResultType(object):
    """ Various scan results types values. """

    ALARM = 0
    LOG = 1
    ERROR = 2

    @classmethod
    def get_str(self, result_type):
        if result_type == self.ALARM:
            return "Alarm"
        elif result_type == self.LOG:
            return "Log"
        elif result_type == self.ERROR:
            return "Error"
        else:
            return "Unknown"

def create_args_parser(description="OpenVAS's OSP Ovaldi Daemon."):
    """ Create a command-line arguments parser for OSPD. """

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-p', '--port', dest='port', type=int, nargs=1,
                        help='TCP Port to listen on. Default: {0}'.format(PORT))
    parser.add_argument('-b', '--bind-address', dest='address', type=str, nargs=1,
                        help='Address to listen on. Default: {0}'.format(ADDRESS))
    parser.add_argument('-k', '--key-file', dest='keyfile', type=str, nargs=1,
                        help='Server key file. Default: {0}'.format(KEY_FILE))
    parser.add_argument('-c', '--cert-file', dest='certfile', type=str, nargs=1,
                        help='Server cert file. Default: {0}'.format(CERT_FILE))
    parser.add_argument('--ca-file', dest='cafile', type=str, nargs=1,
                        help='CA cert file. Default: {0}'.format(CA_FILE))
    parser.add_argument('-t', '--timeout', dest='timeout', type=int, nargs=1,
                        help='Scanner timeout. Default: {0}'.format(TIMEOUT))
    parser.add_argument('-d', '--debug', dest='debug', type=int, nargs=1,
                        help='Debug level. Default: 0')

    return parser

def get_common_args(parser, parentdir):
    """ Return list of OSPD common command-line arguments from parser, after
    validating provided values or setting default ones.

    """

    # TCP Port to listen on.
    options = parser.parse_args()
    if options.port:
        port = int(options.port[0])
        if port <= 0 or port > 65535:
            print "--port must be in ]0,65535] interval.\n"
            parser.print_help()
            exit(1)
    else:
        port = PORT

    # Network address to bind listener to
    if options.address:
        address = options.address[0]
    else:
        address = ADDRESS

    # Scanner timeout.
    if options.timeout:
        timeout = int(options.timeout[0])
        if timeout <= 10:
            print "--timeout should be at least 10 seconds.\n"
            parser.print_help()
            exit(1)
    else:
        timeout = TIMEOUT

    # Debug level.
    if options.debug:
        debug = int(options.debug[0])
        if debug < 0 or debug > 2:
            print "--debug must be 0, 1 or 2.\n"
            parser.print_help()
            exit(1)
    else:
        debug = 0

    # Server key path.
    if options.keyfile:
        keyfile = options.keyfile[0]
    else:
        keyfile = KEY_FILE
    if not os.path.isfile(keyfile):
        print "{0}: Server key file not found.".format(keyfile)
        print "You can generate one using openvas-mkcert."
        parser.print_help()
        exit(1)

    # Server cert path.
    if options.certfile:
        certfile = options.certfile[0]
    else:
        certfile = CERT_FILE
    if not os.path.isfile(certfile):
        print "{0}: Server cert file not found.\n".format(certfile)
        print "You can generate one using openvas-mkcert."
        parser.print_help()
        exit(1)

    # CA cert path.
    if options.cafile:
        cafile = options.cafile[0]
    else:
        cafile = CA_FILE
    if not os.path.isfile(cafile):
        print "{0}: CA cert file not found.\n".format(cafile)
        print "You can generate one using openvas-mkcert."
        parser.print_help()
        exit(1)

    common_args = dict()
    common_args['port'] = port
    common_args['address'] = address
    common_args['timeout'] = timeout
    common_args['keyfile'] = keyfile
    common_args['certfile'] = certfile
    common_args['cafile'] = cafile
    common_args['debug'] = debug

    return common_args