# Wrapper around pysnmp for easy access to snmp-based information
# (c)2008-2010 Dennis Kaarsemaker
#
# Latest version can be found on http://github.com/seveas/python-snmpclient
# 
# This script is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# version 3, as published by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import pysnmp.entity.rfc3413.oneliner.cmdgen as cmdgen
from pysnmp.smi import builder, view
from pysnmp.smi.error import SmiError
from pysnmp.proto import rfc1902

__all__ = ['V1', 'V2', 'V2C', 'add_mib_path', 'load_mibs',
           'nodeinfo', 'nodename', 'nodeid', 'SnmpClient', 'cmdgen']

# SNMP version constants
V1 = 0
V2 = V2C = 1

# The internal mib builder
__mibBuilder = builder.MibBuilder()
__mibViewController = view.MibViewController(__mibBuilder)


def add_mib_path(*path):
    """Add a directory to the MIB search path"""
    mibPath = __mibBuilder.getMibPath() + path
    __mibBuilder.setMibPath(*mibPath)


def load_mibs(*modules):
    """Load one or more mibs"""
    for m in modules:
        try:
            __mibBuilder.loadModules(m)
        except SmiError, e:
            if 'already exported' in str(e):
                continue
            raise


def nodeinfo(oid):
    """Translate dotted-decimal oid to a tuple with symbolic info"""
    if isinstance(oid, basestring):
        oid = tuple([int(x) for x in oid.split('.') if x])
    return (__mibViewController.getNodeLocation(oid),
            __mibViewController.getNodeName(oid))


def nodename(oid):
    """Translate dotted-decimal oid or oid tuple to symbolic name"""
    oid = __mibViewController.getNodeLocation(oid)
    name = '::'.join(oid[:-1])
    noid = '.'.join([str(x) for x in oid[-1]])
    if noid:
        name += '.' + noid
    return name


def nodeid(oid):
    """Translate named oid to dotted-decimal format"""
    ids = oid.split('.')
    symbols = ids[0].split('::')
    ids = tuple([int(x) for x in ids[1:]])
    mibnode, = __mibBuilder.importSymbols(*symbols)
    oid = mibnode.getName() + ids
    return oid


# Load basic mibs that come with pysnmp
load_mibs('SNMPv2-MIB',
          'IF-MIB',
          'IP-MIB',
          'HOST-RESOURCES-MIB',
          'FIBRE-CHANNEL-FE-MIB')


class SnmpClient(object):
    """Easy access to an snmp deamon on a host"""

    def __init__(self, host, port, read_authorizations, write_authorizations):
        """Set up the client and detect the community to use"""
        self.host = host
        self.port = port
        self.alive = False
        self.transport = cmdgen.UdpTransportTarget((self.host, self.port))

        # Determine which community to use for reading values
        noid = nodeid('SNMPv2-MIB::sysName.0')
        for auth in read_authorizations:
            (errorIndication, errorStatus, errorIndex, varBinds) = \
                cmdgen.CommandGenerator().getCmd(
                    cmdgen.CommunityData(auth['community'],
                                         mpModel=auth['version']),
                    self.transport,
                    noid)
            if errorIndication == 'requestTimedOut':
                continue
            else:
                self.alive = True
                self.readauth = cmdgen.CommunityData(auth['community'],
                                                     mpModel=auth['version'])
                break

        # Don't determine the write authorization since there's no temporary
        # location within SNMP to write to. Choose the first authorization.
        for auth in write_authorizations:
            self.writeauth = cmdgen.CommunityData(auth['community'],
                                                  mpModel=auth['version'])
            break

    def get(self, oid):
        """Get a specific node in the tree"""
        noid = nodeid(oid)
        (errorIndication, errorStatus, errorIndex, varBinds) = \
            cmdgen.CommandGenerator().getCmd(
                self.readauth,
                self.transport,
                noid)
        if errorIndication:
            raise RuntimeError("SNMPget of %s on %s failed" % (oid, self.host))
        return varBinds[0][1]

    def set(self, oid, value):
        """Set a specific value to a node in the tree"""
        initial_value = self.get(oid)

        # Types from RFC-1902
        if isinstance(initial_value, rfc1902.Counter32):
            set_value = rfc1902.Counter32(str(value))
        elif isinstance(initial_value, rfc1902.Counter64):
            set_value = rfc1902.Counter64(str(value))
        elif isinstance(initial_value, rfc1902.Gauge32):
            set_value = rfc1902.Gauge32(str(value))
        elif isinstance(initial_value, rfc1902.Integer):
            set_value = rfc1902.Integer(str(value))
        elif isinstance(initial_value, rfc1902.Integer32):
            set_value = rfc1902.Integer32(str(value))
        elif isinstance(initial_value, rfc1902.IpAddress):
            set_value = rfc1902.IpAddress(str(value))
        elif isinstance(initial_value, rfc1902.OctetString):
            set_value = rfc1902.OctetString(str(value))
        elif isinstance(initial_value, rfc1902.TimeTicks):
            set_value = rfc1902.TimeTicks(str(value))
        elif isinstance(initial_value, rfc1902.Unsigned32):
            set_value = rfc1902.Unsigned32(str(value))
        else:
            raise RuntimeError("Unknown type %s" % type(initial_value))

        noid = nodeid(oid)
        (errorIndication, errorStatus, errorIndex, varBinds) = \
            cmdgen.CommandGenerator().setCmd(
                self.writeauth,
                self.transport,
                (noid, set_value)
            )
        if errorIndication:
            raise RuntimeError("SNMPset of %s on %s failed" % (oid, self.host))
        return varBinds[0][1]

    def gettable(self, oid):
        """Get a complete subtable"""
        noid = nodeid(oid)
        (errorIndication, errorStatus, errorIndex, varBinds) = \
            cmdgen.CommandGenerator().nextCmd(
                self.readauth,
                self.transport,
                noid)
        if errorIndication:
            raise RuntimeError("SNMPget of %s on %s failed" % (oid, self.host))
        return [x[0] for x in varBinds]

    def matchtables(self, index, tables):
        """Match a list of tables using either a specific index table or the
           common tail of the OIDs in the tables"""
        oid_to_index = {}
        result = {}
        indexlen = 1
        if index:
            #  Use the index if available
            for oid, index in self.gettable(index):
                oid_to_index[oid[-indexlen:]] = index
                result[index] = []
        else:
            # Generate an index from the first table
            baselen = len(nodeid(tables[0]))
            for oid, value in self.gettable(tables[0]):
                indexlen = len(oid) - baselen
                oid_to_index[oid[-indexlen:]] = oid[-indexlen:]
                result[oid[-indexlen:]] = [value]
            tables = tables[1:]
        # Fetch the tables and match indices
        for table in tables:
            for oid, value in self.gettable(table):
                index = oid_to_index[oid[-indexlen:]]
                result[index].append(value)
        return result
