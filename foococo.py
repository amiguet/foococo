#!/usr/bin/env python2
# encoding: utf-8

'''
FooCoCo, a (SoftStep) Foot Controller Controller.

Copyright 2014, Matthieu Amiguet

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

import operator
import pyo
import hardware
from pygame import midi

# Adjust these values to determine which amount of pressure
# is considered as "Pressed"
# Note: SS2's sensors are much more sensitive than SS1's.
DEFAULT_THRESHOLD = 5
DEFAULT_THRESHOLD_SS2 = 40

# Default curve for Expression object
# higher values mean better control at slow speed
DEFAULT_CURVE = 2
DEFAULT_CURVE_SS2 = 20

# =====================================================
# Private stuff
# =====================================================


def _find_device(device_index=1):
    for name, index in zip(*pyo.pm_get_input_devices()):
        if name == 'SSCOM MIDI 1':
            device_index -= 1
            if device_index == 0:
                return index
    
    raise RuntimeError("Could not find a SoftStep Controller")


# Button names/number to midi CC values
# The numbers can then be offset to find a single sensor
# e.g. _button2CC[1]+_corner2offset['tl'] returns he CC
# number for the top-left sensor of button 1

_button2CC = {
    1 : 44,
    2 : 52,
    3 : 60,
    4 : 68,
    5 : 76,
    
    6 : 40,
    7 : 48,
    8 : 56,
    9 : 64,
    0: 72,
    
    'nav_left' : 80,
    'nav_right' : 81,
    'nav_up' : 82,
    'nav_down' : 83,
}


_corner2offset = { #SoftStep 1
    'tl' : 0,
    'tr' : 1,
    'bl' : 2,
    'br' : 3,
}

_corner2offset_SS2 = { # SoftStep 2
    't' : 0,
    'r' : 1,
    'l' : 2,
    'b' : 3,
}

# pyo midi streams are made singletons for efficiency
_midi_streams = {}
def _midi_stream(cc_num):
    try:
        return _midi_streams[cc_num]
    except KeyError:
        stream = pyo.Midictl(ctlnumber=cc_num, minscale=0, maxscale=127)
        stream.setInterpolation(0)
        _midi_streams[cc_num] = stream
        return stream


def _single_callback_or_list(cb):
    
    if isinstance(cb, list):
        def inner():
            for c in cb:
                c()
    else:
        inner = cb
    
    return inner

# =====================================================
# Get access to raw values: Buttons & expression pedal
# =====================================================


class Button():
    
    ''' A class to represent the foot controller's sensors.
    
    These can be "whole buttons", corners, or combinations thereof. '''
    
    
    def __init__(self, base, corner=None):
    
        ''' Creates a new Button.
        
        Examples:
        
        # The right arrow on the nav pad
        Button('nav_right')
        
        # The button with number 1 (sum of 4 sensors, clipped to 0-127)
        Button(1)
        
        # Top of button 1
        Button(1,'t')
        
        # Top-left corner of button 1 (SoftStep 1 only)
        Button(1,'tl')
        
        '''
        
        if isinstance(base, pyo.PyoObject): # internal use: build button from other buttons
            self.stream = base
            return
        
        if isinstance(base, str): # one of the nav_* buttons
            self.stream = _midi_stream(_button2CC[base])
            return
    
        if corner is not None:
            try:
                self.stream = _midi_stream(_button2CC[base] + _corner2offset[corner])
                return
            except KeyError: # t/l/b/r for SoftStep 1 is a combination of sensors
                if corner in ['t', 'l', 'b', 'r']:
                    offsets = [v for k, v in _corner2offset.iteritems() if corner in k]
                    source = [_midi_stream(_button2CC[base]+offset) for offset in offsets]
                else: # invalid corner specification
                    raise
                    
        else: # combine the four sensors under one numbered button
            source = [_midi_stream(_button2CC[base]+offset) for offset in range(4)]
        
        # If we got here, we've got a combination of sensors to sum-clip
        sum = reduce(operator.add, source)
        self.stream = pyo.Clip(sum, min=0, max=127)
            
            
    def __add__(self, other):
        
        ''' Adds the values of two buttons, clipping to 0-127 '''
        
        new_stream = pyo.Clip(self.stream + other.stream, min=0, max=127)
        return Button(new_stream)
    

def extension_pedal():

    ''' Returns a "button" corresponding to the extension pedal '''

    # The raw values for the pedal are reversed (127 when pedal fully "closed"
    # 0, when fully "opened").
    # This is why we need some special code for that device.

    # TODO: pedal calibration

    cc_num = 86

    try:
        stream = _midi_streams[cc_num]
    except KeyError:
        stream = pyo.Midictl(ctlnumber=cc_num, minscale=127, maxscale=0)
        stream.setInterpolation(0)
        _midi_streams[cc_num] = stream
    
    return Button(stream)

# =====================================================
# Events handlers: press, pressure, ...
# =====================================================


class Press:
    
    ''' A class to manage single button presses. '''
    
    dir2num = {
        'down': 0,
        'up': 1,
        'both': 2,
    }
    
    def __init__(self, source, callback=None, threshold=None, dir='down'):
        
        ''' Create a new Press-event manager.
        
        source is a button (or sum of buttons).
        
        callback is a fonction or list of functions that we be called
        when the button is pressed "harder" than threshold.
        
        dir is the direction of the foot: 'down' corresponds to presses
        and up to releases (but for code clarity use the Release fonction)
        
        '''
        
        if threshold is None:
            threshold = DEFAULT_THRESHOLD
        
        dir = Press.dir2num[dir]
        
        self.trig = pyo.Thresh(input=source.stream, threshold=threshold, dir=dir)
        
        if callback:
            inner = _single_callback_or_list(callback)
            self.trig_f = pyo.TrigFunc(input=self.trig, function=inner)

def Release(source, callback=None, threshold=None):
    
    ''' Like Press, but for release events. '''
    
    return Press(source, callback, threshold, dir='up')


class MultiState:
    
    ''' Rotate a list of states each time a button is pressed. '''
    
    def __init__(self, next, states, prev=None, threshold=None):
        
        ''' Creates a MultiState manager.
        
        next is the button to press to go to next state.
        
        Optional prev is the button to press to go to the previous state.
        
        States is a list of callbacks (or a list of lists of callbacks) that will
        be executed on next or prev presses.
        
        NB: the first state in states will be executed when the MultiState is created.
        
        '''
        
        if threshold is None:
            threshold=DEFAULT_THRESHOLD
        
        self.states = [_single_callback_or_list(s) for s in states]
        self.length = len(states)
        
        self.state = -1
        self.next()
        
        self.trig = pyo.Thresh(input=next.stream, threshold=threshold)
        self.trig_f = pyo.TrigFunc(input=self.trig, function=self.next)
        
        if prev is not None:
            self.prev_trig = pyo.Thresh(input=prev.stream, threshold=threshold)
            self.prev_trig_f = pyo.TrigFunc(input=self.prev_trig, function=self.prev)
    
    def next(self):
        
        self.state = (self.state + 1) % self.length
        self.states[self.state]()


    def prev(self):
        
        self.state = (self.state - 1) % self.length
        self.states[self.state]()


class Pressure:
    
    ''' Execute callbacks each time the pressure on a button changes '''
    
    def __init__(self, source, callback):
        
        if isinstance(callback, list):
            def inner():
                for c in callback:
                    c(int(source.stream.get()))
        else:
            inner = lambda: callback(int(source.stream.get()))
        
        self.trig = pyo.Change(source.stream)
        self.trig_f = pyo.TrigFunc(input=self.trig, function=inner)
    

class Expression:
    
    ''' Emulate an expression pedal from two "buttons".
    
    This can be two physical buttons, or parts of them:
    
    # button 2 to go up, 1 to go down
    Expression(Button(2), Button(1), display('E'))
    
    # up-down motion on button 1
    Expression(
        up = Button(1,'t'),
        down = Button(1,'b'),
        callback= display('E')
    )
    
    '''
    
    def __init__(self, up, down, callback, init=0, curve=None):
        
        if curve is None:
            curve = DEFAULT_CURVE*2+1
        
        self.value = init
        
        if isinstance(callback, list):
            def changed():
                for c in callback:
                    c(int(self.value))
        else:
            changed = lambda: callback(int(self.value))
        

        def update():
            diff = up.stream.get() - down.stream.get()
            
            # Change the curve: fine control when diff is small
            # but still fast change when diff is big
            diff = (diff/127.0)**curve
            
            self.value += diff
            if self.value > 127:
                self.value = 127
            elif self.value < 0:
                self.value = 0
            
            changed()
        
        self.metro = pyo.Metro(time=.01)
        self.metro_f = pyo.TrigFunc(input=self.metro, function=update)
        
        self.trig_start = pyo.Thresh(input=up.stream+down.stream, dir=0)
        self.trig_stop = pyo.Thresh(input=up.stream+down.stream, dir=1, threshold=1)
        self.trig_start_f = pyo.TrigFunc(input=self.trig_start, function=self.metro.play)
        self.trig_stop_f = pyo.TrigFunc(input=self.trig_stop, function=self.metro.stop)

# =====================================================
# Scroll text on LCD Display
# =====================================================

class Scroller(object):
    ''' This class groups attributes and methods to scroll
    text on the LCD display.
    
    Don't instatiate this class, use the classmethods.
    '''
    
    def __new__(cls):
        ''' This class is not meant to be instatiated '''
        raise Exception("Don't instantiate Scroller. Use the classmethods instead.")
    
    @classmethod
    def setText(cls, text, delay=.2):
        
        if text:
            cls.len = len(text)
            cls.text = text + '   ' + text[:4]
            cls.pos = 0
            cls.metro = pyo.Metro(delay).play()
            cls.tf = pyo.TrigFunc(cls.metro, cls._update)
        else:
            cls.text = ''
            cls._update()
            try:
                cls.metro.stop()
            except AttributeError: # nothing to scroll yet
                pass
    
    @classmethod
    def _update(cls):
        
        hardware.display(cls.text[cls.pos:cls.pos+4])
        cls.pos = (cls.pos + 1) % (cls.len+3)

    @classmethod
    def pause(cls, delay=1):
      
        try:
            metro = cls.metro
        except AttributeError: # No text scrolling yet, nothing to do
            return
            
        if metro.isPlaying():
            metro.stop()
            cls.ca = pyo.CallAfter(cls.metro.play,1)

        

# =====================================================
# Callback actions
# =====================================================



def flash(num, color='green'):
    
    ''' Callback to flash led number num with color (green/red/yellow, defaults to green) '''
    
    mode = hardware.FLASH
    color = getattr(hardware, color.upper())
    
    return lambda: hardware.led(num, color, mode)


def led_on(num, color='green'):
    
    ''' Callback to switch on led number num with color (green/red/yellow, defaults to green) '''
    
    mode = hardware.ON
    color = getattr(hardware, color.upper())
    if num == 0:
        num = 10
    
    return lambda: hardware.led(num, color, mode)


def led_off(num):
    
    ''' Callback to switch off led number num '''
    
    mode = hardware.OFF
    if num == 0:
        num = 10
    
    # To be sure to switch off, we have to make it for every color
    return lambda: [hardware.led(num, c, mode) for c in range(3)]


def display(text):

    ''' Callback to display text on the LCD.
    
    When "callbacked" with no argument, display the text.
    
    When "callbacked" with argument (e.g. from Expression()), display the text (left-justified)
    and value (right-justified). If the values gets big, the text will be truncated.
    
    '''
    
    def inner(n=None, text=text):
        
        if n is not None:
            n = str(n)
            l = len(n)
            text = text.ljust(4-l)[:4-l] +n
            
        Scroller.pause()
        hardware.display(text)
        
    return inner
    
    
def midi_PC(num, output, channel=0):
    
    ''' Callback to send a midi program change message '''
    
    return lambda: output.set_instrument(num, channel)


def midi_CC(num, output, value=None):
    
    ''' Callback to send a midi control change message '''
    
    return lambda x=value: output.write_short(0xb0, num, x)


# =====================================================
# Initialization and main loop
# =====================================================


def init(server=None, text='Helo', model=1, device_index=1):

    ''' Initialization. Must be called before creating the "patch".
    
        If several SoftStep's are connected to the computer,
        you can select the one you want with device_index.
    '''

    if model == 2:
        global _corner2offset
        global DEFAULT_THRESHOLD
        global DEFAULT_CURVE
        _corner2offset = _corner2offset_SS2
        DEFAULT_THRESHOLD = DEFAULT_THRESHOLD_SS2
        DEFAULT_CURVE = DEFAULT_CURVE_SS2
    
    if server is None:

        # make it global so that the object doesn't get garbage-collected
        global pyo_server
        
        pyo_server = pyo.Server()
        pyo_server.setMidiInputDevice(_find_device(device_index))
        pyo_server.boot()
        pyo_server.start()
    
    else:
        
        server.setMidiInputDevice(_find_device(device_index))

    hardware.init(text, device_index)

        
def main_loop():

    ''' A convenience function to keep the program alive. '''
        
    import time
    while True:
        time.sleep(1) 
    

if __name__ == '__main__':

    # Find a suitable midi output. On Linux the default will probably
    # be an alsa "Midi Through" port, which is convenient for testing
    # (because clients won't be disconnected when you restart the patch)
    midi.init()
    midi_out = midi.Output(midi.get_default_output_id())


    # Initializes foococo
    init(model=1) # Use model=2 for a SoftStep 2
    
    # Scroll some text
    Scroller.setText('WELCOME TO FOOCOCO')
    
    # The main patch
    # Building a list is just a way to keep the objects referenced
    # so that they don't get garbage-collected.
    
    patch = [
        
        # Single action on single press:
        # Flash led #1 when button 1 is pressed
        # (might be more useful with a midi_PC(1, midi_out), though)
        Press(Button(1), flash(1)),
        
        # Several actions on single press...
        Press(Button(6), [
            led_on(6),
            display('Pr-6'),
            midi_PC(6, midi_out),
        ]),
        
        # ... and release
        Release(Button(6), [
            led_off(6),
            display('Re-6'),
            midi_PC(7, midi_out)
        ]),
        
        # Single action on pressure change
        # In this case, the display action also displays
        # the pressure value
        Pressure(Button(2), display('2>')),
        
        # To use the extension pedal, the logical way is
        # to use Pressure, although you might find creative uses
        # with other managers.
        Pressure(extension_pedal(), [
            midi_CC(7, midi_out),
            display('Expr')
        ]),
        
        # You can also emulate expression pedals with
        # "normal" buttons, with vertical movements...
        Expression(
            up = Button(3,'t'),
            down = Button(3,'b'),
            callback= display('V')
        ),
        
        # Or horizontal
        Expression(
            up = Button(8,'r'),
            down = Button(8,'l'),
            callback= display('H')
        ),
        
        # You also can emulate an expression pedal with
        # TWO different buttons (AFAICT this is not available
        # in KMI's software)
        Expression(
            up = Button(9),
            down = Button(4),
            callback= [display('2>'), midi_CC(7, midi_out)]
        ),
        
        # To get an on-off pedal, use a MultiState:
        MultiState(
            Button(5),
            [
                led_on(5, 'green'),
                led_on(5, 'red'),
            ],
        ),
        
        # Or, with several actions par state:
        MultiState(
            Button(0),
            [
                [led_on(0, 'red'), display('off')],
                [led_on(0, 'green'), display('on')],
            ],
        ),
        
        # MultiState can also have more than two states
        # (also not available in KMI's software, I think)
        MultiState(
            next=Button('nav_right'),
            prev=Button('nav_left'),
            states = [[display('PC%2d' % i), midi_PC(i, midi_out)] for i in range(1,11)]
        )
        
    ]
    
    main_loop()
    