from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub
from operator import attrgetter
import json
import os

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.mac_to_port_consistency = {}
        self.blocked_ports = {}  # Dizionario per tracciare le porte bloccate

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def delete_flow(self, datapath, priority, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                                priority=priority, match=match,
                                instructions=[], table_id=0,
                                buffer_id=ofproto.OFP_NO_BUFFER)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        # Verifica se la porta Ã¨ bloccata
        if datapath.id in self.blocked_ports and in_port in self.blocked_ports[datapath.id]:
            self.logger.info("Dropping packet from blocked port %s on switch %s", in_port, datapath.id)
            return

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port_consistency.setdefault(dpid, {})

        self.logger.info("packet in %s %s %s %s", dpid, src, dst, in_port)

        if not self.is_mac_address_valid(src, in_port, dpid):
            self.logger.warning("MAC Spoofing detected: MAC %s on different port %s", src, in_port)
            return

        self.mac_to_port[dpid][src] = in_port
        self.mac_to_port_consistency[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def is_mac_address_valid(self, src_mac, in_port, dpid):
        # Verifica se l'indirizzo MAC Ã¨ giÃ  associato a una porta diversa
        if src_mac in self.mac_to_port_consistency[dpid] and self.mac_to_port_consistency[dpid][src_mac] != in_port:
            return False
        return True

class SimpleMonitor13(SimpleSwitch13):
    def __init__(self, *args, **kwargs):
        super(SimpleMonitor13, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

        self.previous_rx_bytes = {}
        self.alarm_status = {}
        self.times_no_exceeded = {}
        self.times_to_unblock = 5

        self.threshold = self.calculate_dynamic_threshold()

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body
        datapath = ev.msg.datapath

        self.logger.info('datapath         port     '
                        'rx-pkts  rx-bytes rx-error '
                        'tx-pkts  tx-bytes tx-error  '
                        'throughput')
        self.logger.info('---------------- -------- '
                        '-------- -------- -------- '
                        '-------- -------- -------- '
                        '------------')
        for stat in sorted(body, key=attrgetter('port_no')):
            throughput = self._calculate_throughput(datapath.id, stat.port_no, stat.rx_bytes, 1)

            self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d %10.2f',
                            datapath.id, stat.port_no, stat.rx_packets, 
                            stat.rx_bytes, stat.rx_errors, stat.tx_packets, 
                            stat.tx_bytes, stat.tx_errors, throughput)

            self._init_alarm_status(datapath.id, stat.port_no)
        
            if self._threshold_exceeded(throughput, self.threshold):
                self.logger.info('\nALARM!!! Throughput of switch s%x port %x exceeds the threshold\n', 
                                    datapath.id, stat.port_no)
                self._block_port_traffic(datapath, stat.port_no)
            else: 
                self._unblock_port_traffic(datapath, stat.port_no)

        self.logger.info('\n')

    def _calculate_throughput(self, datapath, port_number, rx_bytes, interval):
        if (datapath, port_number) in self.previous_rx_bytes:
            throughput = (rx_bytes - self.previous_rx_bytes[(datapath, port_number)]) / interval
        else:
            throughput = rx_bytes / interval
        if throughput < 0:
            throughput = 0
        self.previous_rx_bytes[(datapath, port_number)] = rx_bytes
        return throughput

    def _threshold_exceeded(self, throughput, threshold):
        return throughput > threshold

    def _init_alarm_status(self, datapath, port):
        if (datapath, port) not in self.alarm_status:
            self.alarm_status[(datapath, port)] = False

    def _set_alarm_status(self, datapath, port):
        self.alarm_status[(datapath, port)] = True

    def _reset_alarm_status(self, datapath, port):
        self.alarm_status[(datapath, port)] = False

    def _block_port_traffic(self, datapath, port):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(in_port=port)
        actions = []
        self.add_flow(datapath, 1000, match, actions)
        self.times_no_exceeded[(datapath.id, port)] = 0
        self.logger.info('\nBLOCK OPERATION: switch s%x port %x \n', 
                         datapath.id, port)
        self._set_alarm_status(datapath.id, port)

        # Aggiungi la porta bloccata al dizionario
        self.blocked_ports.setdefault(datapath.id, set()).add(port)

    def _unblock_port_traffic(self, datapath, port):
        if self.alarm_status[(datapath.id, port)] == True:
            self.times_no_exceeded[(datapath.id, port)] += 1
            if self.times_no_exceeded[(datapath.id, port)] == self.times_to_unblock:
                parser = datapath.ofproto_parser
                match = parser.OFPMatch(in_port=port)
                self.delete_flow(datapath, 1000, match)
                self.times_no_exceeded[(datapath.id, port)] = 0
                self.logger.info('\nUNBLOCK OPERATION: switch s%x port %x \n', 
                                 datapath.id, port)
                self._reset_alarm_status(datapath.id, port)

                # Rimuovi la porta bloccata dal dizionario
                if datapath.id in self.blocked_ports:
                    self.blocked_ports[datapath.id].discard(port)

    def get_link_bandwidths(self):
        # Verifica se il file esiste prima di tentare di aprirlo
        if os.path.exists('/tmp/link_bandwidths.json'):
            with open('/tmp/link_bandwidths.json', 'r') as f:
                return json.load(f)
        else:
            self.logger.error("Link bandwidths file not found. Using default values.")
            return {}

    def calculate_dynamic_threshold(self):
        link_bandwidths = self.get_link_bandwidths()
        min_bandwidth = min(link_bandwidths.values()) if link_bandwidths else 3
        return min_bandwidth * 1000000 * 1.33