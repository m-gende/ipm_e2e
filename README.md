# IPM e2e

This library implements the usual functions that we'll need to write
_end to end_ tests.

It offers a functional api that performs programmatically the usual
interactions with the graphical interface, on behalf of a human user.

In order to do its job, this library uses the at-spi api, so the
corresponding service must be available and the applications under
test must implement this api.


## Features

- High level, interaction-oriented api


## Installation

```
pip install ipm_e2e
```

Also, you must install the following dependencies:

  - AT-SPI service
  
  - GObject introspection libraries
  
  - Assistive Technology Service Provider Interface - shared library
  
  - Assistive Technology Service Provider (GObject introspection)

  - Python 3 bindings for gobject-introspection libraries
  

The installation process depends on your system. By example, for a debian
distro:

```
$ sudo apt install at-spi2-core python3-gi gir1.2-atspi-2.0 
```

Note that, if you're using Gnome, some of these packages are already
installed.

If you're using a virtual environment, probably you'll prefer not to
install `libatspi`, `gi`, ... in that _venv_. Instead of that, it's
easier to install `vext`:

```
$ pip install vext vext.gi
```


## Support

Please (github.com/cabrero/ipm_e2e/issues)[open an issue] for support.


## License

The project is licensed under the LGPL license.


## TODO
