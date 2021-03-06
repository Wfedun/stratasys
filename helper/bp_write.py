#!/usr/bin/env python2

# Copyright (c) 2014, Benjamin Vanheuverzwijn <bvanheu@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the <organization> nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <BENJAMIN VANHEUVERZWIJN> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#
# Write on 1wire EEPROM of cartridge using a BusPirate
#

import serial
import re
import sys

def bin2hex(binary):
    return "".join(["0x%02X " % ord(b) for b in binary])

def ds2433_write_scratchpad(ta1, ta2, payload):
    return "0x0F " + ta1 + " " + ta2 + " " + payload

def ds2433_read_scratchpad():
    return "0xAA"

def ds2433_read_scratchpad_result(packet):
    return packet.split(" ", 3)

def ds2433_copy_scratchpad(ta1, ta2, es):
    return "0x55 " + ta1 + " " + ta2 + " " + es

def onewire_match_rom(rom_sequence):
    return "{ 0x55 " + rom_sequence

class BusPirate:
    def __init__(self, port="/dev/ttyUSB0", baudrate=115200, timeout=1):
        self.serial = serial.Serial(port, baudrate, timeout=timeout)
        #self.serial.open()

    def __del__(self):
        self.serial.close()

    def initialize(self):
        # Set bus pirate in 1-wire mode
        self.serial.write("m\n")
        self._read_until_prompt()
        self.serial.write("2\n")
        self._read_until_prompt()
        # Cycle PSU (cycle one-wire power)
        self.serial.write("w\n")
        self._read_until_prompt()
        self.serial.write("W\n")
        self._read_until_prompt()
        # Enable pull-up
        self.serial.write("P\n")
        self._read_until_prompt()

    def _read_until_prompt(self):
        line = self.serial.readline()
        while line != "":
            #print line,
            line = self.serial.readline()

    def onewire_macro_search(self):
        rom_sequence = None
        p = re.compile(r".*((?:0x[a-fA-F0-9 ]{2,3}){8})", re.IGNORECASE)

        self.serial.write("(0xF0)\n")

        line = self.serial.readline()
        while line != "":
            m = re.match(p, line)
            if m:
                rom_sequence = m.group(1)
            line = self.serial.readline()

        return rom_sequence

    def onewire_reset_bus(self):
        self.serial.write("{\n")
        self._read_until_prompt()

    def onewire_write(self, data):
        self.serial.write(data + "\n")
        self._read_until_prompt()

    def onewire_read(self, length):
        data = None
        p = re.compile(r"READ: ((?:0x[a-fA-F0-9 ]{2,3}){3,})", re.IGNORECASE)
        self.serial.write("r:%d\n" % length)

        line = self.serial.readline()
        while line != "":
            m = re.match(p, line)
            if m:
                data = m.group(1)
            line = self.serial.readline()

        return data

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: bp_write.py <serial port> <eeprom bin>")
        sys.exit(1)

    f = open(sys.argv[2], "r")
    data = f.read()
    data += "\x00" * (512-len(data))
    f.close()

    bp = BusPirate(port=sys.argv[1], timeout=0.2)
    bp.initialize()
    bp.onewire_reset_bus()

    rom_sequence = bp.onewire_macro_search()
    print("Device found: " + rom_sequence)

    match_rom_packet = onewire_match_rom(rom_sequence)

    if rom_sequence is None:
        raise(Exception("unable to find a device on this 1-wire bus"))

    print("Begin...")
    for i in range(512/32):
        offset = i * 32
        payload = bin2hex(data[i*32:i*32+32])

        # Write scratchpad
        bp.onewire_write(match_rom_packet)
        packet = ds2433_write_scratchpad("0x%02X" % (offset & 0xff), "0x%02X" % (offset >> 8 & 0xff), payload)
        bp.onewire_write(packet)

        # Read scratchpad
        bp.onewire_write(match_rom_packet)
        packet = ds2433_read_scratchpad()
        bp.onewire_write(packet)
        scratchpad_result = bp.onewire_read(35)

        (ta1, ta2, es, scratchpad) =  ds2433_read_scratchpad_result(scratchpad_result)
        if scratchpad != payload:
            raise(Exception("cannot copy scratchpad, scratchpad is " + scratchpad + " but i sent " + payload))

        # Copy scratchpad
        bp.onewire_write(match_rom_packet)
        packet =  ds2433_copy_scratchpad(ta1, ta2, es)
        bp.onewire_write(packet)

        print ".",

    print("Done!")

    sys.exit(0)
