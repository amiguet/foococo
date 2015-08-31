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

from pygame import midi
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

def _open_device(name='SSCOM MIDI 1'):
    '''Opens midi device with given name and port number'''
    # This code stinks. Is there any better way to find the device?

    for dn in range(midi.get_count()):
        md = midi.get_device_info(dn)
        if (md[1] == name) and (md[3] == 1): # md[3] == 1 <=> output device
            return midi.Output(dn)
        
    raise RuntimeError("Could not find a SoftStep Controller")

def _standalone(b):
    '''True for going standalone, False for so-called "tethered" mode'''

    # It seems to me that Tom's names for sysex messages are reversed,
    # but this seems to work
    
    standalone = 0 if b else 1
    
    softstep.write_sys_ex(0, sysex.messages['standalone'][standalone])
    softstep.write_sys_ex(0, sysex.messages['tether'][1-standalone])


# Public API

def init():
    '''Finds and initializes the device'''
    
    global softstep
    
    midi.init()
    softstep = _open_device('SSCOM MIDI 1')
    _standalone(False)
    
    display('HELO')
    reset_leds()


def close(back_to_standalone_mode=True):
    '''Closes the device and optionnaly returns to standalone mode'''
    
    display('Bye')
    reset_leds()
    
    if back_to_standalone_mode:
        _standalone(True)

    # TODO: fix the 'PortMidi: Bad Pointer' error that occurs when closing the midi device        
    softstep.close()
    

def backlight(b):
    '''True turns backlight on, False turns it off'''
    
    val = 1 if b else 0
    
    softstep.write_sys_ex(0, sysex.messages['backlight'][val])


def led(number, color, mode):
    '''Sets led number <led> (numbered from 1 to 10) to given color and mode'''
    
    softstep.write_short(0xB0,40,number-1) # select led, numbered from 0
    softstep.write_short(0xB0,41,color) # green = 0, red = 1, yellow = 2
    softstep.write_short(0xB0,42,mode) # range(x) = (off, on, blink, fast, flash)
    softstep.write_short(0xB0,0,0)
    softstep.write_short(0xB0,0,0)
    softstep.write_short(0xB0,0,0)


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
        softstep.write_short(176,50+n,ord(c))



if __name__ == '__main__':

    # Direct use example
    
    init()
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
    