import snmpclient

router = '10.100.184.62'
port = 161
public_auth = [{'community': 'public', 'version': snmpclient.V2C}]
priavte_auth = [{'community': 'private', 'version': snmpclient.V2C}]

client = snmpclient.SnmpClient(router, port, public_auth, priavte_auth)
print client.alive
print client.get('SNMPv2-MIB::sysName.0')
print client.gettable('UDP-MIB::udpLocalAddress')
print client.matchtables('IF-MIB::ifIndex', ('IF-MIB::ifDescr', 'IF-MIB::ifPhysAddress', 'IF-MIB::ifOperStatus'))
