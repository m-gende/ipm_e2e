# IPM e2e

This is a hotfix to the ipm_e2e library so that it can be used with
Python 3.8.


# Changes

* Fixed typing in e2e.py
  * Added Typing import for Tuple
  * Substituted calls to tuple for Tuple
* Added support for Python 3.8 in setup.cfg
  * Modified the required version of Python

## Features

- High level, interaction-oriented api


## Installation

```
git clone https://github.com/m-gende/ipm_e2e.git
pip install ipm_e2e/
```

### Dependencies (no python)

This library depends on several services and libraries, mainly c code,
that cannot be installed using pip:

  - AT-SPI service
  
  - GObject introspection libraries
  
  - Assistive Technology Service Provider Interface - shared library
  
  - Assistive Technology Service Provider (GObject introspection)

You should use your system's package manager to install them. The
installation process depends on your system, by example, for a debian
distro:

```
$ sudo apt install at-spi2-core gir1.2-atspi-2.0 
```

Note that, if you're using Gnome, some of these packages are already
installed.

### Dependencies (python)

This library depends on the following python library:

  - Python 3 bindings for gobject-introspection libraries

That `python3-gi` library itself depends on some libraries like
`gir1.2-glib-2.0`, `gir1.2-atspi-2.0`, ... If you've installed them
using your system's package manager, the safe bet would be to do the
same for this one. By example:

```
$ sudo apt install python3-gi
```


## Documentation

The documentation is available at [readthedocs](https://ipm-e2e.readthedocs.io/en/latest/).
