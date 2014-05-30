#!/usr/bin/env python

# $Id$
# Description:
# remote-ovaldi wrapper for OSPD.
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

import shutil
import os
import inspect
import base64
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# Set OSPD Directory in syspaths, for imports
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
ospdir = os.path.dirname(os.path.dirname(currentdir))
os.sys.path.insert(0, ospdir)
# Local imports
from ospd.ospd import OSPDaemon
from ospd.misc import create_args_parser, get_common_args

# External modules.
try:
    import pexpect
except:
    print "pexpect not found."
    print "# pip install pexpect. (Or apt-get install python-pexpect.)"
    exit(1)

# ospd-ovaldi daemon class.
class OSPDOvaldi(OSPDaemon):
    """ Class for ospd-ovaldi daemon. """

    def __init__(self, certfile, keyfile, cafile, timeout, debug, rovaldi_path,
                 port, address):
        """ Initializes the ospd-ovaldi daemon's internal data. """
        super(OSPDOvaldi, self).__init__(certfile=certfile, keyfile=keyfile,
                                         cafile=cafile, timeout=timeout,
                                         debug=debug, port=port,
                                         address=address)

        self.version = "0.0.1"
        self.rovaldi_path = rovaldi_path
        self.set_command_elements\
              ("start_scan",
               {'username' : 'SSH Username for remote-ovaldi.',
               'password' : 'SSH Password for remote-ovaldi.',
               'definitions_file' : 'Definitions file content in base64',
               'port' : 'SSH Port for remote-ovaldi.'})

    def check(self):
        """ Checks that remote-ovaldi.sh is found and is executable. """
        try:
            output = pexpect.spawn(self.rovaldi_path)
        except pexpect.ExceptionPexpect, message:
            self.logger.error(message)
            return False
        return True

    def get_scanner_name(self):
        """ Gives the used scanner's name. """
        return "remote-ovaldi"

    def get_scanner_version(self):
        """ Gives the used scanner's version. """
        return "poc" # remote-ovaldi has no version.

    def handle_start_scan_command(self, scan_et):
        """ Handles the OSP <start_scan> command element tree. """
        # Validate scan information
        target = scan_et.attrib.get('target')
        if target is None:
            return "<start_scan status='400' status_text='No target attribute'/>"

        username = scan_et.find('username')
        if username is None or username.text is None:
            return "<start_scan status='400' status_text='No username element'/>"
        password = scan_et.find('password')
        if password is None or password.text is None:
            return "<start_scan status='400' status_text='No password element'/>"
        definitions = scan_et.find('definitions_file')
        if definitions is None or definitions.text is None:
            return "<start_scan status='400' status_text='No definitions_file element'/>"

        username = username.text
        password = password.text

        # Default port: 22.
        port = scan_et.find('port')
        if port is None:
            port = 22
        else:
            try:
                port = int(port.text)
            except ValueError:
                return "<start_scan status='400' status_text='Invalid port value'/>"

        options = dict()
        options['username'] = username
        options['password'] = password
        options['port'] = port
        options['definitions'] = definitions.text

        # Create new Scan
        scan_id = self.create_scan(target, options)

        # Start Scan
        self.start_scan(scan_id)

        # Return Response
        return self.create_response_string({'start_scan_response status="200"'
                                            ' status_text="OK"' :
                                             {'id' : scan_id}})

    def exec_scan(self, scan_id):
        """ Starts the ovaldi scanner for scan_id scan. """
        options = self.get_scan_options(scan_id)
        target = self.get_scan_target(scan_id)
        username = options['username']
        password = options['password']
        definitions = options['definitions']
        port = options['port']
        results_dir = '/tmp/ovaldi-results-{0}'.format(scan_id)
        os.mkdir(results_dir)
        defs_file = '{0}/ovaldi-defs.xml'.format(results_dir)

        # Write definitions to temporary file
        with open(defs_file, 'w') as f:
            try:
                decoded = base64.b64decode(definitions)
            except TypeError:
                self.add_scan_error(scan_id, value="Invalid definitions file")
                self.logger.debug(1, "Couldn't decode base64 definitions content.")
                self.finish_scan(scan_id)
                return
            f.write(decoded)

        # Pexpect
        output = pexpect.spawn('{0} -u {1} -h {2} -p {3} -o {4}'
                               ' --results-dir {5}/'
                                .format(self.rovaldi_path, username, target,
                                        port, defs_file, results_dir))
        output.timeout = self.timeout

        # Provide password for temp dir creation.
        try:
            self.logger.debug(2, "Waiting for temp dir prompt")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout on temp dir creation prompt.")
            self.handle_timeout(scan_id)
            shutil.rmtree(results_dir)
            return
        except pexpect.EOF:
            # SSH Connection failed.
            for line in output.before.split('\n'):
                if "[ERROR]" in line:
                    self.add_scan_error(scan_id, value=line)
            try:
                shutil.rmtree(results_dir)
            except OSError:
                pass
            self.finish_scan(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for scp setup script to remote host
        try:
            self.logger.debug(2, "Waiting for scp to target host prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout on scp to target host prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for making script executable
        try:
            self.logger.debug(2, "Waiting for making script executable prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout on making script executable prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # Handle Wrong SSH credentials case.
        if "Permission denied" in output.before:
            self.logger.debug(2, "{0}: SSH Permission denied".format(scan_id))
            self.add_scan_error(scan_id, value="SSH Permission denied.")
            shutil.rmtree(results_dir)
            self.finish_scan(scan_id)
            return

        # Provide password for running setup script on target
        try:
            self.logger.debug(2, "Waiting for running setup script prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout on running setup script prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for copying input files to target
        try:
            self.logger.debug(2, "Waiting for copying input files prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout waiting for copying input files prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for running ovaldi on target host
        try:
            self.logger.debug(2, "Waiting for running ovaldi prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "Timeout waiting for running ovaldi prompt.")
            self.handle_timeout(scan_id)
            return
        except pexpect.EOF:
            # Happens when ovaldi is not installed on target host.
            self.logger.debug(2, "Ovaldi not found on target host.")
            self.add_scan_error(scan_id, value="ovaldi not installed.")
            # Delete empty results directory
            shutil.rmtree(results_dir)
            self.finish_scan(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for copying results from target host
        try:
            self.logger.debug(2, "Waiting for results copying prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "ovaldi timeout waiting for results copying prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # Provide password for cleaning up temp directory
        try:
            self.logger.debug(2, "Waiting for temp dir cleanup prompt.")
            output.expect("password:")
        except pexpect.TIMEOUT:
            self.logger.debug(1, "ovaldi timeout waiting for temp dir cleanup prompt.")
            self.handle_timeout(scan_id)
            return
        output.sendline("{0}".format(password))

        # The end
        output.expect(pexpect.EOF)


        # One case where *.xml files are missing: Definitions file doesn't
        # match ovaldi version or its schema is not valid, thus only
        # ovaldi.log was generated and no further scan occured.
        # XXX: Extract/Reorganize files content into multiple results.
        # Parse ovaldi.log
        self.parse_ovaldi_log(results_dir, scan_id)
        # Parse results.xml
        self.parse_results_xml(results_dir, scan_id)
        # Parse oval_syschar.xml
        self.parse_oval_syschar_xml(results_dir, scan_id)

        shutil.rmtree(results_dir)
        # Set scan as finished
        self.finish_scan(scan_id)

    def parse_oval_syschar_xml(self, results_dir, scan_id):
        """ Parses the content of oval_syschar.xml file to scan results """

        file_path = "{0}/oval_syschar.xml".format(results_dir)
        try:
            with open(file_path, 'r') as f:
                file_content = f.read()

            # Extract /oval_system_characteristcs/system_info
            system_info = None
            tree = ET.fromstring(file_content)
            for child in tree:
                if child.tag.endswith('system_info'):
                    system_info = child
                elif child.tag.endswith('generator'):
                    generator = child
            for child in generator:
                name = 'syschar_generator:{0}'.format(child.tag.split('}')[1])
                self.add_scan_log(scan_id, name=name, value=child.text)

            for child in system_info:
                if not child.tag.endswith('interfaces'):
                    name = 'system_info:{0}'.format(child.tag.split('}')[1])
                    self.add_scan_log(scan_id, name=name, value=child.text)
                else:
                    # Extract interfaces info from <sytem_info><interfaces>...
                    self.parse_system_info_interfaces(child, scan_id)

            # XXX: Extract /oval_system_characteristcs/system_data/uname_item*
        except IOError:
            self.logger.debug(1, "{0}: Couldn't open file.".format(file_path))

    def parse_system_info_interfaces(self, interfaces, scan_id):
        """ Parses interfaces information in ovaldi's system_info's interfaces
        and insert it in scan results. """

        for interface in interfaces:
            name = str()
            address = str()
            mac = str()
            for child in interface:
                if child.tag.endswith('interface_name'):
                    name = child.text
                elif child.tag.endswith('ip_address'):
                    address = child.text
                elif child.tag.endswith('mac_address'):
                    mac = child.text
            result_str = '{0}|{1}|{2}'.format(name, address, mac)
            self.add_scan_log(scan_id, 'system_info:interface',
                              result_str)

    def parse_results_xml(self, results_dir, scan_id):
        """ Parses results file into scan results. """

        file_path = "{0}/results.xml".format(results_dir)
        try:
            with open(file_path, 'r') as f:
                file_content = f.read()
            # Extract oval definitions results and other relevant information.
            tree = ET.fromstring(file_content)
            for child in tree:
                if child.tag.endswith('generator'):
                    generator = child
                elif child.tag.endswith('oval_definitions'):
                    oval_defs = child
                elif child.tag.endswith('results'):
                    results = child
            for child in generator:
                name = 'results_generator:{0}'.format(child.tag.split('}')[1])
                self.add_scan_log(scan_id, name=name, value=child.text)
            self.parse_oval_results(oval_defs, results, scan_id)
        except IOError:
            self.logger.debug(1, "{0}: Couldn't open file.".format(file_path))

    def parse_oval_results(self, oval_defs, results, scan_id):
        """ Parses oval_definitions and results elements from results file. """

        for child in oval_defs:
            if child.tag.endswith('generator'):
                generator = child
            elif child.tag.endswith('definitions'):
                definitions = child
        for child in generator:
            name = 'defs_generator:{0}'.format(child.tag.split('}')[1])
            self.add_scan_log(scan_id, name=name, value=child.text)
        for definition in definitions:
            def_class = definition.attrib.get('class')
            def_id = definition.attrib.get('id')
            def_result = self.get_definition_result(def_id, results)
            if def_class == 'vulnerability':
                self.add_scan_alarm(scan_id, name=def_id, value=def_result)
            else:
                self.add_scan_log(scan_id, name=def_id, value=def_result)

    def get_definition_result(self, def_id, results):
        """ Gets an oval definition's result value in results element from
        results xml file. """
        for child in results:
            if child.tag.endswith('system'):
                system = child
                break
        for child in system:
            if child.tag.endswith('definitions'):
                definitions = child
                break
        for child in definitions:
            if child.attrib.get('definition_id') == def_id:
                return child.attrib.get('result')
        return "Not found"

    def parse_ovaldi_log(self, results_dir, scan_id):
        """ Parses the content of ovaldi.log file to scan results """

        file_path = "{0}/ovaldi.log".format(results_dir)
        try:
            with open(file_path, 'r') as f:
                file_content = f.read()
            self.add_scan_log(scan_id, name="ovaldi.log", value=file_content)
        except IOError:
            self.logger.debug(1, "{0}: Couldn't open file.".format(file_path))

# Main starts here
if __name__ == '__main__':
    # Common args parser.
    parser = create_args_parser("OSPD - Remote Ovaldi wrapper")

    # ospd-ovaldi specific.
    parser.add_argument('--remote-ovaldi', dest='rovaldi', type=str, nargs=1,
                        help='remote-ovaldi.sh path.'
                             ' (Default is remote-ovaldi.sh)')
    # Common args
    cargs = get_common_args(parser, ospdir)

    options = parser.parse_args()
    # Check for Remote Ovaldi script
    if options.rovaldi:
        rovaldi = options.rovaldi[0]
    else:
        rovaldi = "{0}/wrappers/ovaldi/remote-ovaldi.sh".format(ospdir)
    if not os.path.isfile(rovaldi):
        print "{0}: script not found.".format(rovaldi)
        print "\n"
        parser.print_help()
        exit(1)

    ospd_ovaldi = OSPDOvaldi(port=cargs['port'], timeout=cargs['timeout'],
                             keyfile=cargs['keyfile'], certfile=cargs['certfile'],
                             cafile=cargs['cafile'], debug=cargs['debug'],
                             rovaldi_path=rovaldi, address=cargs['address'])
    if not ospd_ovaldi.check():
        exit(1)
    ret = ospd_ovaldi.run()
    exit(ret)