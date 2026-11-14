#!/usr/bin/env python3
"""
avahi_follow.py - what tests/mdns/follow.sh needs the host's Avahi to do,
over D-Bus, on a timeline (seconds from the start):

  0   20 instances F01..F20 of _followtest._tcp (port 7101..7120, TXT v=1);
      AddrTest (_addrtest._tcp, port 7200, TXT a=1) on its own host,
      addrhost.local, with the address 192.168.166.81
  25  every F.. says v=2                (followed ones: UPDATE)
  25  addrhost.local gains 2001:db8::81  (an address added)
  40  F01..F16 withdrawn                (room for the others)
  40  addrhost.local loses 2001:db8::81  (an address removed)
  50  F17..F20 say v=3                  (all followed now: UPDATE each)
  55  addrhost.local's IPv4 address is 192.168.166.82 instead
  70  everything withdrawn
"""
import sys
import time

import dbus

IF_UNSPEC = -1
PROTO_UNSPEC = -1
NO_REVERSE = 16          # AVAHI_PUBLISH_NO_REVERSE


def txt(item):
    return [dbus.Array([dbus.Byte(b) for b in item.encode()], signature="y")]


class Avahi:
    def __init__(self):
        self.bus = dbus.SystemBus()
        self.server = dbus.Interface(
            self.bus.get_object("org.freedesktop.Avahi", "/"),
            "org.freedesktop.Avahi.Server")

    def group(self):
        return dbus.Interface(
            self.bus.get_object("org.freedesktop.Avahi",
                                self.server.EntryGroupNew()),
            "org.freedesktop.Avahi.EntryGroup")

    def service(self, name, stype, port, item, host=""):
        g = self.group()
        g.AddService(IF_UNSPEC, PROTO_UNSPEC, dbus.UInt32(0), name, stype,
                     "", host, dbus.UInt16(port), txt(item))
        g.Commit()
        return g

    def address(self, host, addr):
        g = self.group()
        g.AddAddress(IF_UNSPEC, PROTO_UNSPEC, dbus.UInt32(NO_REVERSE), host,
                     addr)
        g.Commit()
        return g


def update(g, name, stype, item):
    g.UpdateServiceTxt(IF_UNSPEC, PROTO_UNSPEC, dbus.UInt32(0), name, stype,
                       "", txt(item))


def main():
    a = Avahi()
    start = time.monotonic()

    def at(t):
        time.sleep(max(0.0, start + t - time.monotonic()))

    names = ["F%02d" % i for i in range(1, 21)]
    groups = {n: a.service(n, "_followtest._tcp", 7100 + i + 1, "v=1")
              for i, n in enumerate(names)}
    addr4 = a.address("addrhost.local", "192.168.166.81")
    a.service("AddrTest", "_addrtest._tcp", 7200, "a=1", "addrhost.local")
    at(25)
    for n in names:
        update(groups[n], n, "_followtest._tcp", "v=2")
    addr6 = a.address("addrhost.local", "2001:db8::81")
    at(40)
    for n in names[:16]:
        groups.pop(n).Free()
    addr6.Free()
    at(50)
    for n in names[16:]:
        update(groups[n], n, "_followtest._tcp", "v=3")
    at(55)
    addr4.Free()
    addr4 = a.address("addrhost.local", "192.168.166.82")
    at(70)


if __name__ == "__main__":
    sys.exit(main())
