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

### Dependencies (virtual environment)

If you're using a virtual environment, probably you'll prefer not to
manually install/compile the non-python libraries, neither use the
`system-site-packages` option. Instead of that, it's easier to install
`vext`:

```
$ pip install vext vext.gi
```

, or `pygobject`:

```
$ pip install pygobject
```

## Documentation

The documentation is available at [readthedocs](https://ipm-e2e.readthedocs.io/en/latest/).


## Support

Please [open an issue](https://github.com/cabrero/ipm_e2e/issues) for support.


## License

The project is licensed under the LGPL license.
