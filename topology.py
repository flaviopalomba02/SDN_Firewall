#!/usr/bin/python
import threading
import random
import time
from mininet.log import setLogLevel, info
from mininet.topo import Topo
from mininet.net import Mininet, CLI
from mininet.node import OVSKernelSwitch, Host
from mininet.link import TCLink, Link
from mininet.node import RemoteController #Controller
import json

class Environment(object):
    def __init__(self):

        "Create a network."
        self.net = Mininet(controller=RemoteController, link=TCLink)

        info("*** Starting controller\n")
        c1 = self.net.addController( 'c1', controller=RemoteController) #Controller
        c1.start()

        info("*** Adding hosts and switches\n")
        self.h1 = self.net.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1')
        self.h2 = self.net.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2')
        self.h3 = self.net.addHost('h3', mac='00:00:00:00:00:03', ip='10.0.0.3')
        self.h4 = self.net.addHost('h4', mac='00:00:00:00:00:04', ip='10.0.0.4')

        self.cpe1 = self.net.addSwitch('s1', cls=OVSKernelSwitch)
        self.cpe2 = self.net.addSwitch('s2', cls=OVSKernelSwitch)
        self.core1 = self.net.addSwitch('s3', cls=OVSKernelSwitch)
        self.cpe3 = self.net.addSwitch('s4', cls=OVSKernelSwitch)

        info("*** Adding links\n")  
        self.net.addLink(self.h1, self.cpe1, bw=12, delay='0.0025ms')
        self.net.addLink(self.h4, self.cpe1, bw=12, delay='0.0025ms')
        self.net.addLink(self.h2, self.cpe2, bw=12, delay='0.0025ms')
        self.net.addLink(self.h3, self.cpe3, bw=12, delay='0.0025ms')

        self.net.addLink(self.cpe1, self.core1, bw=6, delay='25ms')
        self.net.addLink(self.cpe2, self.core1, bw=6, delay='25ms')
        self.net.addLink(self.cpe3, self.core1, bw=6, delay='25ms')

        info("*** Starting network\n")
        self.net.build()
        self.net.start()

        # Salva le informazioni sulla larghezza di banda in un file JSON
        self.save_link_bandwidths()
import threading
import random
import time
from mininet.log import setLogLevel, info
from mininet.topo import Topo
from mininet.net import Mininet, CLI
from mininet.node import OVSKernelSwitch, Host
from mininet.link import TCLink, Link
from mininet.node import RemoteController #Controller
import json

class Environment(object):
    def __init__(self):

        "Create a network."
        self.net = Mininet(controller=RemoteController, link=TCLink)

        info("*** Starting controller\n")
        c1 = self.net.addController( 'c1', controller=RemoteController) #Controller
        c1.start()

        info("*** Adding hosts and switches\n")
        self.h1 = self.net.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1')
        self.h2 = self.net.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2')
        self.h3 = self.net.addHost('h3', mac='00:00:00:00:00:03', ip='10.0.0.3')
        self.h4 = self.net.addHost('h4', mac='00:00:00:00:00:04', ip='10.0.0.4')

        self.cpe1 = self.net.addSwitch('s1', cls=OVSKernelSwitch)
        self.cpe2 = self.net.addSwitch('s2', cls=OVSKernelSwitch)
        self.core1 = self.net.addSwitch('s3', cls=OVSKernelSwitch)
        self.cpe3 = self.net.addSwitch('s4', cls=OVSKernelSwitch)

        info("*** Adding links\n")  
        self.net.addLink(self.h1, self.cpe1, bw=12, delay='0.0025ms')
        self.net.addLink(self.h4, self.cpe1, bw=12, delay='0.0025ms')
        self.net.addLink(self.h2, self.cpe2, bw=12, delay='0.0025ms')
        self.net.addLink(self.h3, self.cpe3, bw=12, delay='0.0025ms')

        self.net.addLink(self.cpe1, self.core1, bw=6, delay='25ms')
        self.net.addLink(self.cpe2, self.core1, bw=6, delay='25ms')
        self.net.addLink(self.cpe3, self.core1, bw=6, delay='25ms')

        info("*** Starting network\n")
        self.net.build()
        self.net.start()

        # Salva le informazioni sulla larghezza di banda in un file JSON
        self.save_link_bandwidths()

    def save_link_bandwidths(self):
        links = self.net.links
        link_bandwidths = {}
        for link in links:
            intf1, intf2 = link.intf1, link.intf2
            bw = link.intf1.params['bw']
            link_bandwidths[f'{intf1.node.name}-{intf2.node.name}'] = bw
        with open('/tmp/link_bandwidths.json', 'w') as f:
            json.dump(link_bandwidths, f)

if __name__ == '__main__':

    setLogLevel('info')
    info('starting the environment\n')
    env = Environment()

    info("*** Running CLI\n")
    CLI(env.net)
    def save_link_bandwidths(self):
        links = self.net.links
        link_bandwidths = {}
        for link in links:
            intf1, intf2 = link.intf1, link.intf2
            bw = link.intf1.params['bw']
            link_bandwidths[f'{intf1.node.name}-{intf2.node.name}'] = bw
        with open('/tmp/link_bandwidths.json', 'w') as f:
            json.dump(link_bandwidths, f)

if __name__ == '__main__':

    setLogLevel('info')
    info('starting the environment\n')
    env = Environment()

    info("*** Running CLI\n")
    CLI(env.net)