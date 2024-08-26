from tplinkrouterc6u import (
    TplinkRouterProvider,
    TplinkRouter,
    TplinkC1200Router,
    TPLinkMRClient,
    TPLinkCGIClient,
    TPLinkDecoClient,
    Connection,
    IPv4Reservation
)
from logging import Logger
from dataclasses import asdict

import macaddress
import ipaddress
import pprint

pp = pprint.PrettyPrinter(indent=2)

router = TPLinkCGIClient('http://192.168.0.1', 'admin', 'admin', verify_ssl = False)


# headers = router.HEADERS
# headers['Referer'] = router.host
# # response = router.req.post('http://192.168.0.1/cgi/logout', data=[], cookies={"Authorization": "Basic YWRtaW46YWRtaW4="}, headers=headers, timeout=4, verify=False)
# response = router.req.post('http://192.168.0.1/cgi?8', data='[/cgi/logout#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n', cookies={"Authorization": "Basic YWRtaW46YWRtaW4="}, headers=headers, timeout=4, verify=False)
# print(response)
# # 8\r\n[/cgi/logout#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n

#router.logout()

try:
#     acts = [
#             router.ActItem(5, 'LAN_DHCP_STATIC_ADDR', attrs=['enable', 'chaddr', 'yiaddr']),
#     ]
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
#     #data = '&'.join(act_types) + '\r\n' + ''.join(act_data)
#     data = ''.join(act_data)
#     print()
#     print(data)
#     print(router.host)
#
#     url = router._get_url('cgi', act_types)
#     print(url)
#     # url="http://192.168.0.1/cgi?5"
#
#     #print(router._req_rsa_key())
#     #exit(0)
# #    (code, response) = router._request(url, data_str=''.join(act_data), encrypt=False)
#
#     headers = router.HEADERS
#     headers['Referer'] = router.host
#     #response = router.req.post(url, data=''.join(act_data), cookies={"Authorization": "Basic YWRtaW46YWRtaW4="}, headers=headers, timeout=4, verify=False)
#     #response = router.req.post(url, data=''.join(act_data), cookies={"Authorization": "Basic YWRtaW46YWRtaW4="}, headers=headers, timeout=4, verify=False)
#     response = router.req.post(url, data=data, cookies={"Authorization": "Basic YWRtaW46YWRtaW4="}, headers=headers, timeout=4, verify=False)
#
#
#
#     result=router._merge_response(response.text)
#     #result=parse_response(response.text)
#     pp.pprint(response.text)
#
#     print(result)
#     values=result.get('0') if len(result) == 1 and result.get('0') else result
#     print(values)
#
#     #_, values = self.req_act(acts)
#
#     ipv4_reservations = []
#     for item in router._to_list(values):
#         print(item)
#         ipv4_reservations.append(
#             IPv4Reservation(
#                 macaddress.EUI48(item['chaddr']),
#                 ipaddress.IPv4Address(item['yiaddr']),
#                 '',
#                 bool(int(item['enable']))
#             ))
#     print(ipv4_reservations)


#    router.authorize()  # authorizing
    # Get firmware info - returns Firmware
    router.supports()
    firmware = router.get_firmware()
    pp.pprint(firmware)
    print()
    print()

    # Get status info - returns Status
    status = router.get_status()
    pp.pprint(status)
    print()
    print()

#    if not status.guest_2g_enable:  # check if guest 2.4G wifi is disable
#        router.set_wifi(Connection.GUEST_2G, True)  # turn on guest 2.4G wifi

    # st = router.get_ipv4_status()
    # pp.pprint(st)
    # print()
    # print()
    #exit(0)

    # Get Address reservations, sort by ipaddr
    reservations = router.get_ipv4_reservations()
    reservations.sort(key=lambda a: a.ipaddr)
    for res in reservations:
        print(f"{res.macaddr} {res.ipaddr:16s} {res.hostname:36} {res.enabled:6}")

    # Get DHCP leases, sort by ipaddr
    leases = router.get_ipv4_dhcp_leases()
    leases.sort(key=lambda a: a.ipaddr)
    for lease in leases:
        print(f"{lease.macaddr} {lease.ipaddr:16s} {lease.hostname:36} {lease.lease_time:12}")
finally:
    router.logout()  # always logout as TP-Link Web Interface only supports upto 1 user logged

