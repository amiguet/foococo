#!/usr/bin/env python2
# coding: utf-8

'''Code to talk to the softstep foot controller.

Copyright 2014, Matthieu Amiguet

The midi sniffing has been done by Tom Swirly. 
https://github.com/rec/swirly/blob/master/js/swirly/softstep/enable.js

This file is part of FooCoCo.

FooCoCo is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import pyo
import sysex

# CONSTANTS

GREEN = 0
RED = 1
YELLOW = 2

OFF = 0
ON = 1
BLINK = 2
FAST_BLINK = 3
FLASH = 4



# Private functions

def _find_device(devices, device_index=1):
    for name, index in zip(*devices):
        if name == 'SSCOM MIDI 1':
            device_index -= 1
            if device_index == 0:
                return index
        
    raise RuntimeError("Could not find a SoftStep Controller")

def _standalone(b):
    '''True for going standalone, False for so-called "tethered" mode'''

    # It seems to me that Tom's names for sysex messages are reversed,
    # but this seems to work
    
    standalone = 0 if b else 1
    
    _sys_ex(0, sysex.messages['standalone'][standalone])
    _sys_ex(0, sysex.messages['tether'][1-standalone])

def _sys_ex(_, message):
    msg = ''.join([chr(n) for n in message])
    pyo_server.sysexout(msg)


# Public API

def init(server, text='', device_index=1):
    '''Finds and initializes the device
    
    server is an unbooted pyo Server object.
    This method will boot and start the server.
    '''
    
    global pyo_server
    
    server.setMidiInputDevice(
        _find_device(pyo.pm_get_input_devices(), device_index),
    )
    server.setMidiOutputDevice(
        _find_device(pyo.pm_get_output_devices(), device_index),
    )
    pyo_server = server
    server.boot().start()
    
    _standalone(False)
    
    display(text)
    reset_leds()


def close(text='', back_to_standalone_mode=True):
    '''Closes the device and optionnaly returns to standalone mode'''
    
    display(text)
    reset_leds()
    
    if back_to_standalone_mode:
        _standalone(True)
    

def backlight(b):
    '''True turns backlight on, False turns it off'''
    
    val = 1 if b else 0
    
    _sys_ex(0, sysex.messages['backlight'][val])


def led(number, color, mode):
    '''Sets led number <led> (numbered from 1 to 10) to given color and mode'''
    
    pyo_server.ctlout(40,number-1) # select led, numbered from 0
    pyo_server.ctlout(41,color) # green = 0, red = 1, yellow = 2
    pyo_server.ctlout(42,mode) # range(x) = (off, on, blink, fast, flash)
    pyo_server.ctlout(0,0)
    pyo_server.ctlout(0,0)
    pyo_server.ctlout(0,0)


def reset_leds():
    '''Switch all leds off'''
    
    for l in range(1,11):
        for c in range(3):
            led(l,c,0)


def display(text):
    '''Sets the text on the device's display. The text gets truncated to 4 chars'''
    
    # We want exctly 4 chars in the string
    text = text[:4]
    text = text + (' ' * (4-len(text)))
    
    # Now send to the device
    for n, c in enumerate(text):
        pyo_server.ctlout(50+n,ord(c))



if __name__ == '__main__':

    # Direct use example
    
    s = pyo.Server()
    init(s, device_index=1)
    
    backlight(False)
    led(1,GREEN,ON)
    led(2,RED,ON)
    led(3,YELLOW,ON)
    
    import time
    time.sleep(2)
    
    backlight(True)
    display('Cool')
    led(6,GREEN,BLINK)
    led(7,RED,FAST_BLINK)
    led(8,YELLOW,FLASH)
    
    time.sleep(2)
    
    backlight(False)
    
    close()
    