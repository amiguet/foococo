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

# Adjust these values to determine which amount of pressure
# is considered as "Pressed"
# Note: SS2's sensors are much more sensitive than SS1's.
DEFAULT_THRESHOLD = .03
DEFAULT_THRESHOLD_SS2 = .3

# Default curve for Expression object
# higher values mean better control at slow speed
DEFAULT_CURVE = 2
DEFAULT_CURVE_SS2 = 20

# =====================================================
# Private stuff
# =====================================================

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
def _midi_stream(cc_num, **kwargs):
    try:
        return _midi_streams[cc_num]
    except KeyError:
        stream = pyo.Midictl(ctlnumber=cc_num, **kwargs)
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


def button(base, corner=None):
    
    ''' A pyo.Midictl wrapper to conviently access the SoftStep's buttons
        
    Examples:
    
    # The right arrow on the nav pad
    button('nav_right')
    
    # The button with number 1 (sum of 4 sensors, clipped to 0-127)
    button(1)
    
    # Top of button 1
    button(1,'t')
    
    # Top-left corner of button 1 (SoftStep 1 only)
    button(1,'tl')
    
    '''
        
    
    if isinstance(base, str): # one of the nav_* buttons
        stream = _midi_stream(_button2CC[base])
        return stream
    
    if corner is not None:
        try:
            stream = _midi_stream(_button2CC[base] + _corner2offset[corner])
            return stream
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
    return pyo.Clip(sum, min=0, max=1)
            

def extension_pedal(calib_min=None, calib_max=None):

    ''' Returns a "button" corresponding to the extension pedal '''

    # The raw values for the pedal are reversed (127 when pedal fully "closed"
    # 0, when fully "opened").
    # This is why we need some special code for that device.

    stream = _midi_stream(
        cc_num=86,
        minscale=1,
        maxscale=0,
    )
    
    if calib_min or calib_max:
        stream = pyo.Scale(stream, calib_min, calib_max, 0, 1)
    
    return stream

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
        
        self.trig = pyo.Thresh(input=source, threshold=threshold, dir=dir)
        
        if callback:
            inner = _single_callback_or_list(callback)
            self.trig_f = pyo.TrigFunc(input=self.trig, function=inner)
            
        
    def stop(self):
        
        self.trig.stop()
        self.trig_f.stop()
        
        return self
    
    def play(self):
        
        self.trig.play()
        self.trig_f.play()    
        
        return self
            

def Release(source, callback=None, threshold=None):
    
    ''' Like Press, but for release events. '''
    
    return Press(source, callback, threshold, dir='up')


class MultiState:
    
    ''' Rotate a list of states each time a button is pressed. '''
    
    def __init__(self, next, states, prev=None, threshold=None, init=0):
        
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
        
        if init is not None:
            self.state = init-1
            self.next()
        else:
            self.state = None
        
        self.trig = pyo.Thresh(input=next, threshold=threshold)
        self.trig_f = pyo.TrigFunc(input=self.trig, function=self.next)
        
        if prev is not None:
            self.prev_trig = pyo.Thresh(input=prev, threshold=threshold)
            self.prev_trig_f = pyo.TrigFunc(input=self.prev_trig, function=self.prev)
            self.prev = True
        else:
            self.prev = False
    
    def next(self):
        
        self.state = (self.state + 1) % self.length
        self.states[self.state]()


    def prev(self):
        
        self.state = (self.state - 1) % self.length
        self.states[self.state]()

    def stop(self):
        
        self.trig.stop()
        self.trig_f.stop()
        if self.prev:
            self.prev_trig.stop()
            self.prev_trig_f.stop()
        
        return self
    
    def play(self):
        
        self.trig.play()
        self.trig_f.play()
        if self.prev:
            self.prev_trig.play()
            self.prev_trig_f.play()
        
        if self.state is None:
            self.state = -1
            self.next()
        
        
        return self
        


class Pressure:
    
    ''' Execute callbacks each time the pressure on a button changes '''
    
    def __init__(self, source, callback):
        
        if isinstance(callback, list):
            def inner():
                for c in callback:
                    c(int(source.get()*100))
        else:
            inner = lambda: callback(int(source.get()*100))
        
        self.trig = pyo.Change(source)
        self.trig_f = pyo.TrigFunc(input=self.trig, function=inner)

    def stop(self):
        
        for o in [self.trig, self.trig_f]:
            o.stop()
            
        return self
    
    
    def play(self):
        
        for o in [self.trig, self.trig_f]:
            o.play()

        return self

    

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
                    c(int(self.value*100))
        else:
            changed = lambda: callback(int(self.value*100))
        

        def update():
            diff = up.get() - down.get()
            
            # Change the curve: fine control when diff is small
            # but still fast change when diff is big
            diff = (diff)**curve
            
            self.value += diff
            if self.value > 1:
                self.value = 1
            elif self.value < 0:
                self.value = 0
            
            changed()
        
        self.metro = pyo.Metro(time=.1)
        self.metro_f = pyo.TrigFunc(input=self.metro, function=update)
        
        self.trig_start = pyo.Thresh(input=up+down, dir=0, threshold=DEFAULT_THRESHOLD)
        self.trig_stop = pyo.Thresh(input=up+down, dir=1, threshold=DEFAULT_THRESHOLD)
        self.trig_start_f = pyo.TrigFunc(input=self.trig_start, function=self.metro.play)
        self.trig_stop_f = pyo.TrigFunc(input=self.trig_stop, function=self.metro.stop)

    def stop(self):
        
        for o in [self.trig_start, self.trig_stop, self.trig_start_f, self.trig_stop_f]:
            o.stop()
            
        return self
    
    
    def play(self):
        
        for o in [self.trig_start, self.trig_stop, self.trig_start_f, self.trig_stop_f]:
            o.play()

        return self

# =====================================================
# Scroll text on LCD Display
# =====================================================

class Scroller(object):
    ''' This class groups attributes and methods to scroll
    text on the LCD display.
    
    To simpy scroll a text, user the classmethod setText().
    
    To get a playable/stoppable object that scrolls text,
    instantiate the class.
    '''
    
    def __init__(self, text):
        self.text = text
    
    def play(self):
        self.__class__.setText(self.text)
    
    def stop(self):
        self.__class__.setText('')

    
    @classmethod
    def setText(cls, text, delay=.2):
        
        if text:
            cls.len = len(text)
            cls.text = text + '   ' + text[:4]
            cls.pos = 0
            try:
                cls.metro.play()
            except AttributeError: # nothing to scroll yet
                cls.metro = pyo.Metro(delay).play()
                cls.tf = pyo.TrigFunc(cls.metro, cls._update)
        else:
            cls.text = ''
            cls.pos = 0
            cls.len = 0
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


def led_off(nums):
    
    ''' Callback to switch off led number num '''
    
    mode = hardware.OFF
    
    if not isinstance(nums, list):
        nums = [nums]
    
    # To be sure to switch off, we have to make it for every color
    return lambda: [hardware.led(num % 10, c, mode) for c in range(2) for num in nums]


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
    

# =====================================================
# Initialization and main loop
# =====================================================


def init(server, text='', model=1, device_index=1):

    ''' Initialization. Must be called before creating the "patch".
    
        If several SoftStep's are connected to the computer,
        you can select the one you want with device_index.
        
        server must be an unbooted pyo Server.
        The server will be booted and started by this method.
    '''

    if model == 2:
        global _corner2offset
        global DEFAULT_THRESHOLD
        global DEFAULT_CURVE
        _corner2offset = _corner2offset_SS2
        DEFAULT_THRESHOLD = DEFAULT_THRESHOLD_SS2
        DEFAULT_CURVE = DEFAULT_CURVE_SS2
    
    hardware.init(server, text, device_index)

def close(text='', back_to_standalone_mode=True):
    
    hardware.close(text, back_to_standalone_mode)

        
def main_loop():

    ''' A convenience function to keep the program alive. '''
        
    import time
    while True:
        time.sleep(1) 
    

if __name__ == '__main__':

    import sys
    
    try:
        model = int(sys.argv[1])
    except:
        model = 1
        
    try:
        device_index = int(sys.argv[2])
    except:
        device_index = 1


    # Initializes foococo
    s = pyo.Server(audio='jack')
    init(s, model=model, device_index=device_index)
    
    # Scroll some text
    Scroller.setText('WELCOME TO FOOCOCO')
    
    # The main patch
    # Building a list is just a way to keep the objects referenced
    # so that they don't get garbage-collected.
    
    patch = [
        
        # Single action on single press:
        # Flash led #1 when button 1 is pressed
        # (might be more useful with a midi_PC(1, midi_out), though)
        Press(button(1), flash(1)),
        
        # Several actions on single press...
        Press(button(6), [
            led_on(6),
            display('Pr-6'),
        ]),
        
        # ... and release
        Release(button(6), [
            led_off(6),
            display('Re-6'),
        ]),
        
        # Single action on pressure change
        # In this case, the display action also displays
        # the pressure value
        Pressure(button(2), display('2>')),
        
        # To use the extension pedal, the logical way is
        # to use Pressure, although you might find creative uses
        # with other managers.
        Pressure(extension_pedal(calib_min=.1, calib_max=.9), display('Expr')),
        
        # You can also emulate expression pedals with
        # "normal" buttons, with vertical movements...
        Expression(
            up = button(3,'t'),
            down = button(3,'b'),
            callback= display('V')
        ),
        
        # Or horizontal
        Expression(
            up = button(8,'r'),
            down = button(8,'l'),
            callback= display('H')
        ),
        
        # You also can emulate an expression pedal with
        # TWO different buttons (AFAICT this is not available
        # in KMI's software)
        Expression(
            up = button(9),
            down = button(4),
            callback=display('2>')
        ),
        
        # To get an on-off pedal, use a MultiState:
        MultiState(
            button(5),
            [
                led_on(5, 'green'),
                led_on(5, 'red'),
            ],
        ),
        
        # Or, with several actions par state:
        MultiState(
            button(0),
            [
                [led_on(0, 'red'), display('off')],
                [led_on(0, 'green'), display('on')],
            ],
        ),
        
        # MultiState can also have more than two states
        # (also not available in KMI's software, I think)
        MultiState(
            next=button('nav_right'),
            prev=button('nav_left'),
            states = [display('PC%2d' % i) for i in range(1,11)]
        )
        
    ]
    
    main_loop()
    