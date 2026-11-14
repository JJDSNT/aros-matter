#!/usr/bin/env python3
"""
avahi_update.py NAME TYPE PORT FIRST SECOND FIRST_SECONDS SECOND_SECONDS

Publishes a service through the host's Avahi (D-Bus) with the TXT item
FIRST, changes its TXT to SECOND in place after FIRST_SECONDS - the same
service, not withdrawn (Avahi's UpdateServiceTxt) - and withdraws it, with
its goodbye, SECOND_SECONDS later. For a browse that must tell a change of
what an instance says.
"""
import sys
import time

import dbus

IF_UNSPEC = -1
PROTO_UNSPEC = -1


def txt(item):
    return [dbus.Array([dbus.Byte(b) for b in item.encode()], signature="y")]


def main():
    name, stype, port, first, second, t1, t2 = sys.argv[1:8]
    bus = dbus.SystemBus()
    server = dbus.Interface(bus.get_object("org.freedesktop.Avahi", "/"),
                            "org.freedesktop.Avahi.Server")
    group = dbus.Interface(
        bus.get_object("org.freedesktop.Avahi", server.EntryGroupNew()),
        "org.freedesktop.Avahi.EntryGroup")
    group.AddService(IF_UNSPEC, PROTO_UNSPEC, dbus.UInt32(0), name, stype,
                     "", "", dbus.UInt16(int(port)), txt(first))
    group.Commit()
    time.sleep(float(t1))
    group.UpdateServiceTxt(IF_UNSPEC, PROTO_UNSPEC, dbus.UInt32(0), name,
                           stype, "", txt(second))
    time.sleep(float(t2))
    group.Free()                    # withdrawn, with its goodbye
    time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
