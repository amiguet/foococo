KMI's SoftStep Foot Controller is a very nice device, but to get the full power,
you need to use KMI's proprietary software.

This is an alternative to KMI's software, allowing to use the SoftStep with
unsupported systems (e.g. Linux).

It already provides a few functionalities not available in KMI's software. If
you have a crazy idea about what you want to do with your SoftStep, this might
be the way to go.

A 10-minutes video presentation of the project is available here:

- [http://lac.linuxaudio.org/2014/video.php?id=5](http://lac.linuxaudio.org/2014/video.php?id=5)

    (Talk at the Linux Audio Conference 2014, Karlsruhe)

Note that the project's maturity is "works for me". I've used it with success in many gigs, but make sure to test it thoroughly before you take it with you on stage!

To make it work, you'll need

- a recent python 2.x
- a recent version of pyo: http://ajaxsoundstudio.com/software/pyo/
- pygame: http://www.pygame.org/
- some creativity

The `__main__` part of `foococo.py` shows how to use it.

Enjoy!

**Note about branches**:

- The `master` branch is the original project, using python/pyo to make a bridge between your SoftStep and other software.

- The `pyo` branch aims to make the SoftStep easy to use from a python/pyo program. This branch does not need pygame.