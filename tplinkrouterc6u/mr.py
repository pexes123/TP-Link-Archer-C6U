import base64
import hashlib
import re
import json
import time
import urllib
import requests
import datetime
import macaddress
import ipaddress
from logging import Logger
from tplinkrouterc6u.encryption import EncryptionWrapper, EncryptionWrapperMR
from tplinkrouterc6u.enum import Connection
from tplinkrouterc6u.dataclass import Firmware, Status, Device, IPv4Reservation, IPv4DHCPLease, IPv4Status
from tplinkrouterc6u.exception import ClientException, ClientError
from tplinkrouterc6u.client import TPLinkCGIClient

# UNFINISHED
# this file is unfinished attempt to save the specifics of MR router relative to TBD common CGI core
# idea was to have both files of the as same as possible content with each part commented here xor there, to track the core extraction
# have nowhere to test, whether the former TPLinkMRClient still works

class TPLinkMRClient(TPLinkCGIClient):
    # REQUEST_RETRIES = 3
    #
    # HEADERS = {
    #     'Accept': '*/*',
    #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
    #     'Referer': 'http://192.168.1.1/'  # updated on the fly
    # }

    ACT_PROXY_URL = 'cgi_gdpr'
    ENCRYPT_ACT = True
    ROUTER_CLASS = 'MR'

    # HTTP_RET_OK = 0
    # HTTP_ERR_CGI_INVALID_ANSI = 71017
    HTTP_ERR_USER_PWD_NOT_CORRECT = 71233
    HTTP_ERR_USER_BAD_REQUEST = 71234
    #
    # CLIENT_TYPES = {
    #     0: Connection.WIRED,
    #     1: Connection.HOST_2G,
    #     3: Connection.HOST_5G,
    #     2: Connection.GUEST_2G,
    #     4: Connection.GUEST_5G,
    # }
    #
    # WIFI_SET = {
    #     Connection.HOST_2G: '1,1,0,0,0,0',
    #     Connection.HOST_5G: '1,2,0,0,0,0',
    #     Connection.GUEST_2G: '1,1,1,0,0,0',
    #     Connection.GUEST_5G: '1,2,1,0,0,0',
    # }
    #
    # class ActItem:
    #     GET = 1
    #     SET = 2
    #     ADD = 3
    #     DEL = 4
    #     GL = 5
    #     GS = 6
    #     OP = 7
    #     CGI = 8
    #
    #     def __init__(self, type: int, oid: str, stack: str = '0,0,0,0,0,0', pstack: str = '0,0,0,0,0,0',
    #                  attrs: list = []):
    #         self.type = type
    #         self.oid = oid
    #         self.stack = stack
    #         self.pstack = pstack
    #         self.attrs = attrs

    def __init__(self, host: str, password: str, username: str = 'admin', logger: Logger = None,
                 verify_ssl: bool = True, timeout: int = 30) -> None:
        super().__init__(host, password, username, logger, verify_ssl, timeout)

        # self.req = requests.Session()
        self._token = None
        self._hash = hashlib.md5((self.username + self.password).encode()).hexdigest()
        self._nn = None
        self._ee = None
        self._seq = None

        self._encryption = EncryptionWrapperMR()

    def supports(self) -> bool:
        try:
            self._req_rsa_key()
            return True
        except AssertionError:
            return False

    def authorize(self) -> None:
        '''
        Establishes a login session to the host using provided credentials
        '''
        # hash the password

        # request the RSA public key from the host
        self._nn, self._ee, self._seq = self._req_rsa_key()

        # authenticate
        self._req_login()

        # request TokenID
        self._token = self._req_token()

    # def logout(self) -> None:
    #     '''
    #     Logs out from the host
    #     '''
    #     if self._token is None:
    #         return
    #
    #     acts = [
    #         # 8\r\n[/cgi/logout#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n
    #         self.ActItem(self.ActItem.CGI, '/cgi/logout')
    #     ]
    #
    #     response, _ = self.req_act(acts)
    #     ret_code = self._parse_ret_val(response)
    #
    #     if ret_code == self.HTTP_RET_OK:
    #         self._token = None
    #
    # def get_firmware(self) -> Firmware:
    #     acts = [
    #         self.ActItem(self.ActItem.GET, 'IGD_DEV_INFO', attrs=[
    #             'hardwareVersion',
    #             'modelName',
    #             'softwareVersion'
    #         ])
    #     ]
    #     _, values = self.req_act(acts)
    #
    #     firmware = Firmware(values.get('hardwareVersion', ''), values.get('modelName', ''),
    #                         values.get('softwareVersion', ''))
    #
    #     return firmware

    def get_status(self) -> Status:
        status = Status()
        acts = [
            self.ActItem(self.ActItem.GS, 'LAN_IP_INTF', attrs=['X_TP_MACAddress', 'IPInterfaceIPAddress']),
            self.ActItem(self.ActItem.GS, 'WAN_IP_CONN',
                         attrs=['enable', 'MACAddress', 'externalIPAddress', 'defaultGateway']),
            self.ActItem(self.ActItem.GL, 'LAN_WLAN', attrs=['enable', 'X_TP_Band']),
            self.ActItem(self.ActItem.GL, 'LAN_WLAN_GUESTNET', attrs=['enable', 'name']),
            self.ActItem(self.ActItem.GL, 'LAN_HOST_ENTRY', attrs=[
                'IPAddress',
                'MACAddress',
                'hostName',
                'X_TP_ConnType',
                'active',
            ]),
            self.ActItem(self.ActItem.GS, 'LAN_WLAN_ASSOC_DEV', attrs=[
                'associatedDeviceMACAddress',
                'X_TP_TotalPacketsSent',
                'X_TP_TotalPacketsReceived',
            ]),
        ]
        _, values = self.req_act(acts)

        if values['0'].__class__ == list:
            values['0'] = values['0'][0]

        status._lan_macaddr = macaddress.EUI48(values['0']['X_TP_MACAddress'])
        status._lan_ipv4_addr = ipaddress.IPv4Address(values['0']['IPInterfaceIPAddress'])

        for item in self._to_list(values.get('1')):
            if int(item['enable']) == 0 and values.get('1').__class__ == list:
                continue
            status._wan_macaddr = macaddress.EUI48(item['MACAddress']) if item.get('MACAddress') else None
            status._wan_ipv4_addr = ipaddress.IPv4Address(item['externalIPAddress'])
            status._wan_ipv4_gateway = ipaddress.IPv4Address(item['defaultGateway'])

        if values['2'].__class__ != list:
            status.wifi_2g_enable = bool(int(values['2']['enable']))
        else:
            status.wifi_2g_enable = bool(int(values['2'][0]['enable']))
            status.wifi_5g_enable = bool(int(values['2'][1]['enable']))

        if values['3'].__class__ != list:
            status.guest_2g_enable = bool(int(values['3']['enable']))
        else:
            status.guest_2g_enable = bool(int(values['3'][0]['enable']))
            status.guest_5g_enable = bool(int(values['3'][1]['enable']))

        devices = {}
        for val in self._to_list(values.get('4')):
            if int(val['active']) == 0:
                continue
            conn = self.CLIENT_TYPES.get(int(val['X_TP_ConnType']))
            if conn is None:
                continue
            elif conn == Connection.WIRED:
                status.wired_total += 1
            elif conn.is_guest_wifi():
                status.guest_clients_total += 1
            elif conn.is_host_wifi():
                status.wifi_clients_total += 1
            devices[val['MACAddress']] = Device(conn,
                                                macaddress.EUI48(val['MACAddress']),
                                                ipaddress.IPv4Address(val['IPAddress']),
                                                val['hostName'])

        for val in self._to_list(values.get('5')):
            if val['associatedDeviceMACAddress'] not in devices:
                status.wifi_clients_total += 1
                devices[val['associatedDeviceMACAddress']] = Device(
                    Connection.HOST_2G,
                    macaddress.EUI48(val['associatedDeviceMACAddress']),
                    ipaddress.IPv4Address('0.0.0.0'),
                    '')
            devices[val['associatedDeviceMACAddress']].packets_sent = int(val['X_TP_TotalPacketsSent'])
            devices[val['associatedDeviceMACAddress']].packets_received = int(val['X_TP_TotalPacketsReceived'])

        status.devices = list(devices.values())
        status.clients_total = status.wired_total + status.wifi_clients_total + status.guest_clients_total

        return status

    # def get_ipv4_reservations(self) -> [IPv4Reservation]:
    #     acts = [
    #         self.ActItem(5, 'LAN_DHCP_STATIC_ADDR', attrs=['enable', 'chaddr', 'yiaddr']),
    #     ]
    #     _, values = self.req_act(acts)
    #
    #     ipv4_reservations = []
    #     for item in self._to_list(values):
    #         ipv4_reservations.append(
    #             IPv4Reservation(
    #                 macaddress.EUI48(item['chaddr']),
    #                 ipaddress.IPv4Address(item['yiaddr']),
    #                 '',
    #                 bool(int(item['enable']))
    #             ))
    #
    #     return ipv4_reservations

    def get_ipv4_dhcp_leases(self) -> [IPv4DHCPLease]:
        acts = [
            self.ActItem(5, 'LAN_HOST_ENTRY', attrs=['IPAddress', 'MACAddress', 'hostName', 'leaseTimeRemaining']),
        ]
        _, values = self.req_act(acts)

        dhcp_leases = []
        for item in self._to_list(values):
            lease_time = item['leaseTimeRemaining']
            dhcp_leases.append(
                IPv4DHCPLease(
                    macaddress.EUI48(item['MACAddress']),
                    ipaddress.IPv4Address(item['IPAddress']),
                    item['hostName'],
                    str(datetime.timedelta(seconds=int(lease_time))) if lease_time.isdigit() else 'Permanent',
                ))

        return dhcp_leases

    def get_ipv4_status(self) -> IPv4Status:
        acts = [
            self.ActItem(self.ActItem.GS, 'LAN_IP_INTF',
                         attrs=['X_TP_MACAddress', 'IPInterfaceIPAddress', 'IPInterfaceSubnetMask']),
            self.ActItem(self.ActItem.GET, 'LAN_HOST_CFG', '1,0,0,0,0,0', attrs=['DHCPServerEnable']),
            self.ActItem(self.ActItem.GS, 'WAN_IP_CONN',
                         attrs=['enable', 'MACAddress', 'externalIPAddress', 'defaultGateway', 'name', 'subnetMask',
                                'DNSServers']),
        ]
        _, values = self.req_act(acts)

        ipv4_status = IPv4Status()
        ipv4_status._lan_macaddr = macaddress.EUI48(values['0']['X_TP_MACAddress'])
        ipv4_status._lan_ipv4_ipaddr = ipaddress.IPv4Address(values['0']['IPInterfaceIPAddress'])
        ipv4_status._lan_ipv4_netmask = ipaddress.IPv4Address(values['0']['IPInterfaceSubnetMask'])
        ipv4_status.lan_ipv4_dhcp_enable = bool(int(values['1']['DHCPServerEnable']))

        for item in self._to_list(values.get('2')):
            if int(item['enable']) == 0 and values.get('2').__class__ == list:
                continue
            ipv4_status._wan_macaddr = macaddress.EUI48(item['MACAddress'])
            ipv4_status._wan_ipv4_ipaddr = ipaddress.IPv4Address(item['externalIPAddress'])
            ipv4_status._wan_ipv4_gateway = ipaddress.IPv4Address(item['defaultGateway'])
            ipv4_status.wan_ipv4_conntype = item['name']
            ipv4_status._wan_ipv4_netmask = ipaddress.IPv4Address(item['subnetMask'])
            dns = item['DNSServers'].split(',')
            ipv4_status._wan_ipv4_pridns = ipaddress.IPv4Address(dns[0])
            ipv4_status._wan_ipv4_snddns = ipaddress.IPv4Address(dns[1])

        return ipv4_status

    def set_wifi(self, wifi: Connection, enable: bool) -> None:
        acts = [
            self.ActItem(
                self.ActItem.SET,
                'LAN_WLAN' if wifi in [Connection.HOST_2G, Connection.HOST_5G] else 'LAN_WLAN_MSSIDENTRY',
                self.WIFI_SET[wifi],
                attrs=['enable={}'.format(int(enable))]),
        ]
        self.req_act(acts)

    def send_sms(self, phone_number: str, message: str) -> None:
        acts = [
            self.ActItem(
                self.ActItem.SET, 'LTE_SMS_SENDNEWMSG', attrs=[
                    'index=1',
                    'to={}'.format(phone_number),
                    'textContent={}'.format(message),
                ]),
        ]
        self.req_act(acts)

    # def reboot(self) -> None:
    #     acts = [
    #         self.ActItem(self.ActItem.OP, 'ACT_REBOOT')
    #     ]
    #     self.req_act(acts)

    # def req_act(self, acts: list):
    #     '''
    #     Requests ACTs via the ACT_PROXY_URL cgi proxy
    #     '''
    #     act_types = []
    #     act_data = []
    #
    #     for act in acts:
    #         act_types.append(str(act.type))
    #         act_data.append('[{}#{}#{}]{},{}\r\n{}\r\n'.format(
    #             act.oid,
    #             act.stack,
    #             act.pstack,
    #             len(act_types) - 1,  # index, starts at 0
    #             len(act.attrs),
    #             '\r\n'.join(act.attrs)
    #         ))
    #
    #     data = '&'.join(act_types) + '\r\n' + ''.join(act_data)
    #
    #     url = self._get_url(self.ACT_PROXY_URL)
    #     (code, response) = self._request(url, data_str=data, encrypt=self.ENCRYPT_ACT)
    #
    #     if code != 200:
    #         error = 'TplinkRouter - {} -  Response with error; Request {} - Response {}'.format(self.ROUTER_CLASS, data, response)
    #         if self._logger:
    #             self._logger.error(error)
    #         raise ClientError(error)
    #
    #     result = self._merge_response(response)
    #
    #     return response, result.get('0') if len(result) == 1 and result.get('0') else result

    # @staticmethod
    # def _to_list(response: dict | list | None) -> list:
    #     if response is None:
    #         return []
    #
    #     return [response] if response.__class__ != list else response
    #
    # @staticmethod
    # def _merge_response(response: str) -> dict:
    #     result = {}
    #     obj = {}
    #     lines = response.split('\n')
    #     for l in lines:
    #         if l.startswith('['):
    #             regexp = re.search('\[\d,\d,\d,\d,\d,\d\](\d)', l)
    #             if regexp is not None:
    #                 obj = {}
    #                 index = regexp.group(1)
    #                 item = result.get(index)
    #                 if item is not None:
    #                     if item.__class__ != list:
    #                         result[index] = [item]
    #                     result[index].append(obj)
    #                 else:
    #                     result[index] = obj
    #             continue
    #         if '=' in l:
    #             keyval = l.split('=')
    #             assert len(keyval) == 2
    #
    #             obj[keyval[0]] = keyval[1]
    #
    #     return result if result else []

    # def _get_url(self, endpoint: str, params: dict = {}, include_ts: bool = True) -> str:
    #     # add timestamp param
    #     if include_ts:
    #         params['_'] = str(round(time.time() * 1000))
    #
    #     # format params into a string
    #     params_arr = []
    #     for attr, value in params.items():
    #         params_arr.append('{}={}'.format(attr, value))
    #
    #     # format url
    #     return '{}/{}{}{}'.format(
    #         self.host,
    #         endpoint,
    #         '?' if len(params_arr) > 0 else '',
    #         '&'.join(params_arr)
    #     )

    def _req_token(self):
        '''
        Requests the TokenID, used for CGI authentication (together with cookies)
            - token is inlined as JS var in the index (/) html page
              e.g.: <script type="text/javascript">var token="086724f57013f16e042e012becf825";</script>

        Return value:
            TokenID string
        '''
        url = self._get_url('')
        (code, response) = self._request(url, method='GET')
        assert code == 200

        result = re.search('var token="(.*)";', response)

        assert result is not None
        assert result.group(1) != ''

        return result.group(1)

    def _req_rsa_key(self):
        '''
        Requests the RSA public key from the host

        Return value:
            ((n, e), seq) tuple
        '''
        url = self._get_url('cgi/getParm')
        (code, response) = self._request(url)
        assert code == 200

        # assert return code
        assert self._parse_ret_val(response) == self.HTTP_RET_OK

        # parse public key
        ee = re.search('var ee="(.*)";', response)
        nn = re.search('var nn="(.*)";', response)
        seq = re.search('var seq="(.*)";', response)

        assert ee and nn and seq
        ee = ee.group(1)
        nn = nn.group(1)
        seq = seq.group(1)
        assert len(ee) == 6
        assert len(nn) == 128
        assert seq.isnumeric()

        return nn, ee, int(seq)

    def _req_login(self) -> None:
        '''
        Authenticates to the host
            - sets the session token after successful login
            - data/signature is passed as a GET parameter, NOT as a raw request data
              (unlike for regular encrypted requests to the /cgi_gdpr endpoint)

        Example session token (set as a cookie):
            {'JSESSIONID': '4d786fede0164d7613411c7b6ec61e'}
        '''
        # encrypt username + password

        sign, data = self._prepare_data(self.username + '\n' + self.password, True)
        assert len(sign) == 256

        data = {
            'data': urllib.parse.quote(data, safe='~()*!.\''),
            'sign': sign,
            'Action': 1,
            'LoginStatus': 0,
            'isMobile': 0
        }

        url = self._get_url('cgi/login', data)
        (code, response) = self._request(url)
        assert code == 200

        # parse and match return code
        ret_code = self._parse_ret_val(response)
        error = ''
        if ret_code == self.HTTP_ERR_USER_PWD_NOT_CORRECT:
            info = re.search('var currAuthTimes=(.*);\nvar currForbidTime=(.*);', response)
            assert info is not None

            error = 'TplinkRouter - MR - Login failed, wrong password. Auth times: {}/5, Forbid time: {}'.format(
                info.group(1), info.group(2))
        elif ret_code == self.HTTP_ERR_USER_BAD_REQUEST:
            error = 'TplinkRouter - MR - Login failed. Generic error code: {}'.format(ret_code)
        elif ret_code != self.HTTP_RET_OK:
            error = 'TplinkRouter - MR - Login failed. Unknown error code: {}'.format(ret_code)

        if error:
            if self._logger:
                self._logger.error(error)
            raise ClientException(error)

    def _request(self, url, method='POST', data_str=None, encrypt=False):
        '''
        Prepares and sends an HTTP request to the host
            - sets up the headers, handles token auth
            - encrypts/decrypts the data, if needed

        Return value:
            (status_code, response_text) tuple
        '''
        headers = self.HEADERS

        # add referer to request headers,
        # otherwise we get 403 Forbidden
        headers['Referer'] = self.host

        # add token to request headers,
        # used for CGI auth (together with JSESSIONID cookie)
        if self._token is not None:
            headers['TokenID'] = self._token

        # encrypt request data if needed (for the /cgi_gdpr endpoint)
        if encrypt:
            sign, data = self._prepare_data(data_str, False)
            data = 'sign={}\r\ndata={}\r\n'.format(sign, data)
        else:
            data = data_str

        retry = 0
        while retry < self.REQUEST_RETRIES:
            # send the request
            if method == 'POST':
                r = self.req.post(url, data=data, headers=headers, timeout=self.timeout, verify=self._verify_ssl)
            elif method == 'GET':
                r = self.req.get(url, data=data, headers=headers, timeout=self.timeout, verify=self._verify_ssl)
            else:
                raise Exception('Unsupported method ' + str(method))

            # sometimes we get 500 here, not sure why... just retry the request
            if r.status_code != 500 and '<title>500 Internal Server Error</title>' not in r.text:
                break

            time.sleep(0.05)
            retry += 1

        # decrypt the response, if needed
        if encrypt and (r.status_code == 200) and (r.text != ''):
            return r.status_code, self._decrypt_response(r.text)
        else:
            return r.status_code, r.text

    # def _parse_ret_val(self, response_text):
    #     '''
    #     Parses $.ret value from the response text
    #
    #     Return value:
    #         return code (int)
    #     '''
    #     result = re.search('\$\.ret=(.*);', response_text)
    #     assert result is not None
    #     assert result.group(1).isnumeric()
    #
    #     return int(result.group(1))

    def _prepare_data(self, data: str, is_login: bool) -> tuple[str, str]:
        encrypted_data = self._encryption.aes_encrypt(data)
        data_len = len(encrypted_data)
        # get encrypted signature
        signature = self._encryption.get_signature(int(self._seq) + data_len, is_login, self._hash, self._nn, self._ee)

        # format expected raw request data
        return signature, encrypted_data

    def _decrypt_response(self, data: dict) -> dict:
        return self._encryption.aes_decrypt(data)
