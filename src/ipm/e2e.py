"""Functions to perform interactions with graphical user interfaces on
behalf of regular users.

This library offers a functional api to perform programmatically common
interactions with the graphical interface. In order to do its job,
this library uses the at-spi api, so the corresponding service must be
available and the applications must implement the api.

If you rather like it, think of this library as an abstraction of the
at-spi api. This abstraction is intended to ease the use of the api.

Examples
--------

Implementation of Gerkhin steps::

    # GIVEN I started the application
    process, app = e2e.run("./contador.py")
    ## ok ?
    if app is None:
        process and process.kill()
        assert False, f"There is no aplication {path} in the desktop"
    do, shows = e2e.perform_on(app)

    # WHEN I click the button 'Contar'
    do('click', role= 'push button', name= 'Contar')

    # THEN I see the text "Has pulsado 1 vez"
    assert shows(role= "label", text= "Has pulsado 1 vez")

    ## Before leaving, clean up your mesh
    process and process.kill()
"""

from __future__ import annotations

from pathlib import Path
import random
import re
import subprocess
import time
from typing import Any, Callable, Iterable, Iterator, NamedTuple, Optional, TypeVar, Union

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

__all__ = [
    'perform_on',
    'perform_on_all',
    'find_obj',
    'find_all_objs',
    'obj_get_attr',
    'obj_children',
    'tree_walk',
    'run',
    'is_error',
    'fail_on_error',
    'Either',
    'UserDo',
]


class NotFoundError(Exception): pass


T = TypeVar('T')
Either= Union[Exception, T]
"""The classic Either type, i.e. a value of type T or an error.

*N.B.:* The typing and implementation of the functions using this type
is quite relaxed.

"""


def is_error(x: Any) -> bool:
    """Checks whether any python object represents an error.
    
    This function is intended to be used with values of type ``Either``.

    Parameters
    ----------
    x
        The object to check

    Returns
    -------
    bool
        whether it's an error

    """
    return isinstance(x, Exception)


def fail_on_error(x: Any) -> None:
    """Raises an exception when the python object represents an error.

    Parameters
    ----------
    x
        The object to check

    Returns
    -------
    Any
        The python object when it is not an error

    Raises
    ------
    Exception
        The exception that corresponds to the error
    """
    
    if is_error(x):
        raise x
    return x

    
def _pprint(obj: Atspi.Object) -> str:
    role = obj.get_role_name()
    name = obj.get_name() or ""
    return f"{role} ({name})"


def _get_action_idx(obj: Atspi.Object, name: str) -> Optional[int]:
    for i in range(obj.get_n_actions()):
        if obj.get_action_name(i) == name:
            return i
    return None


def _get_actions_names(obj: Atspi.Object) -> list[str]:
    return [ obj.get_action_name(i) for i in range(obj.get_n_actions()) ]


def obj_get_attr(obj: Atspi.Object, name:str) -> Either[str]:
    """Returns the value of an at-spi object's attribute.

    Some attributes are not actual attributes in at-spi, and must be
    retrieved using an at-spi function like `get_text()`. This
    function can chooice the right way to access attributes.

    Parameters
    ----------
    obj : Atspi.Object
        The object from which to retrieve the value of the attriute
    name : str
        The name of the attribute

    Returns
    -------
    str
        The value of the attribute
    AttributeError
        When the object has no such attribute
    """
    
    if name == 'role':
        return obj.get_role_name()
    elif name == 'name':
        return getattr(obj, 'name') or ""
    elif name == 'text':
        return obj.get_text(0, -1)
    elif hasattr(obj, name):
        return getattr(obj, name)
    elif hasattr(obj, f"get_{name}"):
        return getattr(obj, f"get_{name}")()
    else:
        return AttributeError(f"{_pprint(obj)} has no attribute {name}")
    

# Cuando buscamos todos los valores son strings aunque el tipo del
# atributo sea un Enum.
# Podríamos intentar usar el valor, p.e.:
# ```python
# from e2e import role
# do('click', role= role.BUTTON, name= _('Count'))
# ```
#
# Eso nos obligaría a cargar las definiciones de los Enums al cargar
# el módulo, o hacerlo _on-the-fly_ con una cache.
#
# Ahora mismo, cuando una búsqueda falla. Revisamos los valores de los
# attributos que en realidad son de tipo Enum para ver si no está en
# la lista y poder dar un mensaje de error más útil.
#
# TODO: decidir si implementar la primera opción.
# TODO: añadir más casos a la función
def _help_not_found(kwargs) -> str:
    msg = ""
    role = kwargs.get('role', None)
    if role and role.upper() not in Atspi.Role.__dict__:
        msg = f"{msg}\n{role} is not a role name"
    return msg

        
# TODO: Parámetro `path` el valor puede incluir patrones. Hay que ver
# qué lenguaje usamos. Tiene que machear con el path desde el root
# hasta el widget.  ¿ Nos interesa incluir otros atributos además de
# la posición dentro de los siblings ?
def _match(obj: Atspi.Object, path: TreePath, name: str, value: Any) -> bool:
    if name == 'path':
        TODO
    elif name == 'nth':
        nth_of = path[-1]
        idx = value if value >= 0 else nth_of.n + value
        return idx == nth_of.i
    elif type(value) == str:
        return obj_get_attr(obj, name) == value
    elif type(value) == re.Pattern:
        attr_value = obj_get_attr(obj, name)
        if is_error(attr_value):
            return False
        return value.fullmatch(attr_value) is not None
    elif name == 'pred':
        return value(obj, path)
    else:
        TODO


def _find_all_descendants(root: Atspi.Object, kwargs) -> Iterable[Atspi.Object]:
    if len(kwargs) == 0:
        descendants = (obj for _path, obj in tree_walk(root))
    else:
        descendants = (obj for path, obj in tree_walk(root)
                       if all(_match(obj, path, name, value) for name, value in kwargs.items()))
    return descendants

    
def find_obj(root: Atspi.Object, **kwargs) -> Either[Atspi.Object]:
    """Searchs for the first at-spi object that matches the arguments.

    This functions searchs the given `root` object and its descendants
    (inorder), looking for the first object that matches the arguments
    `kwargs`.

    In order to match `kwargs`, an object must satisfy all named
    arguments of the list. Each argument is interpreted as follows:

    - `pred`. When the name of the argument is `pred`, its value must
      be a function `xxx(obj: Atspi.Object, path: PathTree) -> bool`.
      This function must implement some kind of check on the given
      object.

    - `nth`. The position of the object among its siblings must be the
      given value. As usual positions start at 0, and negative indexes
      start at the the end of the list.

    - Otherwise. The name of the argument denotes the attribute of the
      object to be checked. And the value can be:

      - A string. The object's attribute value must be identical to
        the given string.

      - An `re.Pattern` object. The whole object's attribute value
        will be checked against the regular expression pattern
        (i.e. `fullmatch`).

    When `kwargs` is empty, the `root` object is selected.

    Parameters
    ----------
    root : Atspi.Object
        The object to start the search from
    **kwargs
        The patterns the object must match (as previosuly explained)

    Returns
    -------
    Atspi.Object
        The first descendant (inorder) that matches the arguments
    NotFoundError
        When no object matches the arguments

    """
    
    if len(kwargs) == 0:
        return root
    else:
        obj = next(_find_all_descendants(root, kwargs), None)
        if obj is None:
            help_msg = _help_not_found(kwargs)
            return NotFoundError(f"no widget from {_pprint(root)} with {kwargs} {help_msg}") 
        else:
            return obj

    
def find_all_objs(roots: Union[Atspi.Object, Iterable[Atspi.Object]], **kwargs) -> list[Atspi.Object]:
    """Searchs for all the at-spi objects that matches the arguments.

    This function is similar to `find_obj`. The meaning of the
    `kwargs` arguments is the same. But it presents the following
    differences:

    - Instead of a root object to start the search from, it's possible
      to specify a collection of objects to start from every one of
      them.

    - Instead of returning the first object that matches the
      arguments, it returns a list containing all of them.

    Parameters
    ----------
    roots: Union[Atspi.Object, Iterable[Atspi.Object]]
        The object/s to start the search from
    **kwargs
        The patterns the object must match (as previosuly explained)

    Returns
    -------
    list[Atspi.Object]
        The list of all descendants that matches the arguments
    """
    
    if isinstance(roots, Atspi.Object):
        roots = [roots]
    result = []
    if len(kwargs) == 0:
        for root in roots:
            result.extend(obj for _path, obj in tree_walk(root))
    else:
        for root in roots:
            result.extend(_find_all_descendants(root, kwargs))
    return result


def obj_children(obj: Atspi.Object) -> list[Atspi.Object]:
    """Obtains the list of children of an at-spi object.

    Parameters
    ----------
    obj : Atspi.Object
        The object whose children will be queried.

    Returns
    -------
    list[Atspi.Object]
        The list of object's children.
    """
    
    return [ obj.get_child_at_index(i) for i in range(obj.get_child_count()) ]


class NthOf(NamedTuple):
    i : int
    n : int

    def is_last(self) -> bool:
        return self.i == self.n - 1
    
    def __str__(self) -> str:
        return f"{self.i}/{self.n}"


TreePath = tuple[NthOf, ...]


ROOT_TREE_PATH = (NthOf(0, 1),)


def tree_walk(root: Atspi.Object, path: TreePath= ROOT_TREE_PATH) -> Iterator[tuple[TreePath, Atspi.Object]]:
    """Creates a tree traversal.

    This function performs an inorder tree traversal, starting at the
    given _root_ (at-spi object). Foreach visited node, it yields the
    path from the root to the node, and the node itself.

    The path includes the position and the number of siblings of each
    node.

    Parameters
    ----------
    root : Atspi.Object
        The root node where to start the traversal.

    path : TreePath, optional
        A prefix for the paths yielded.

    Yields
    ------
    (TreePath, Atspi.Object)
        A tuple containing the path to the node and the node itself

    """
    
    yield path, root
    children = obj_children(root)
    n_children = len(children)
    for i, child in enumerate(children):
        yield from tree_walk(child, path= path + (NthOf(i,n_children),))


# Función do
#
# El nombre de la acción es un parámetro porque hay acciones con
# espacios en el nombre. No intentamos que sea un atributo que
# contiene un objeto callable, o cualquier opción que implique que el
# nombre tiene que ser un _python name_.
UserDo = Callable[[str,...], None]
"""Performs an action on the first descendant at-spi object that
matches the patterns.
    
    Parameters
    ----------
    action_name : str
        The name of the action
    \*\*kwargs
        The patterns the object must match (as previosuly explained)

    Raises
    ------
    NotFoundError
        If no object matches the patterns in kwargs
        If the matching object doesn't provide the given action
"""

UIShows = Callable[[...], bool]
"""Checks whether the UI shows the information given by the patterns.

Note that the pattern can specify both the information to be shown and
the at-spi object that contains that information.

    Parameters
    ----------
    **kwargs
        The patterns the object must match (as previosuly explained)

    Returns
    -------
    bool
        Whether any object matches the patterns.
"""

UIInteraction = tuple[UserDo, UIShows]

UserDoAll = Callable[[str,...], None]
"""For each root object performs an action on the first descendant
at-spi object that matches the patterns.

    Parameters
    ----------
    action_name : str
        The name of the action
    **kwargs
        The patterns the object must match (as previosuly explained)

    Raises
    ------
    NotFoundError
        If no object matches the patterns in kwargs
        If the matching object doesn't provide the given action

"""
UIShowsAll = Callable[[...], Iterator[bool]]
"""For each root object checks wheter the UI shows the information
given by the patterns.

Note that the pattern can specify both the information to be shown and
the at-spi object that contains that information.

Note that the result is an iterator which data can be aggregated using
the builtins ``any`` or ``all``.

    Parameters
    ----------
    **kwargs
        The patterns the object must match (as previosuly explained)

    Returns
    -------
    Iterator[bool]
        A collection of boolean indicating whether any object matches
        the patterns for each root object.

"""
UIMultipleInteraction = tuple[UserDoAll, UIShowsAll]


Obj_S = Union[Atspi.Object | Iterable[Atspi.Object]]


def _as_iterable(objs: Obj_S) -> Iterable[Atspi.Object]:
    return (objs,) if isinstance(objs, Atspi.Object) else objs
    
               
def _do(obj: Atspi.Object, action_name: str) -> None:
    idx = _get_action_idx(obj, action_name)
    if idx is None:
        names = _get_actions_names(obj)
        raise NotFoundError(f"widget {_pprint(obj)} has no action named '{name}', got: {','.join(names)}")
    obj.do_action(idx)

    
def perform_on(roots: Obj_S, **kwargs) -> UIInteraction:
    """Constructs functions that interact with parts of the user interface.

    For each at-spi object in roots, this function looks for the first
    descendant of that root that matches the patterns in `kwargs`. The
    `kwargs` arguments are interpreted exactyly as in the function
    `find_obj`.

    Then, it constructs the functions that interact, using at-spi,
    with the subtrees rooted at the at-spi objects found. These
    functions implements two basic interactions, intended to replace
    the users' interaction. See :py:data:`UserDo` and
    :py:data:`UIShows` for a description of these functions.

    Parameters
    ----------
    roots : Atspi.Object | Iterable[Atspi.Object]
        The at-spi object/s to start the search from

    **kwargs
        The patterns the object must match (as previously explained)

    Returns
    -------
    UIInteraction
        A tuple with the two functions: ``UserDo`` and ``UIShows``

    Raises
    ------
    NotFoundError
        If no object matches the patterns in `kwargs`

    """

    on_objs = [ fail_on_error(find_obj(root, **kwargs))
                for root in _as_iterable(roots) ]

    def do(
    on_obj = find_obj(root, **kwargs)
    fail_on_error(on_obj)
    
    def do(action_name: str, **kwargs) -> None:
        obj = find_obj(on_obj, **kwargs)
        fail_on_error(obj)
        _do(obj, action_name)
        
    def shows(**kwargs) -> bool:
        if len(kwargs) == 0:
            raise TypeError("shows must have at least one argument, got 0")
        return not is_error(find_obj(on_obj, **kwargs))
                   
    return (do, shows)


def perform_on_all(roots: Union[Atspi.Object, Iterable[Atspi.Object]], **kwargs) -> UIMultipleInteraction:
    """Constructs functions that interact with some parts of the user interface.

    This function is mostly equal to :py:func:`perform_on`, but
    instead of working on the first at-spi object that matches the
    kwargs, it works on every object that matches them. So the
    difference is that the functions ``do`` and ``shows`` will perform
    the interaction on every descendant that matches kwargs.  See
    :py:data:`UserDoAll` and :py:data:`UIShowsAll` for a description
    of these functions.

    Parameters
    ----------
    roots : Union[Atspi.Object, Iterable[Atspi.Object]]
        The object/s to start the search from

    **kwargs
        The patterns the object must match (as previously explained)

    Returns
    -------
    UIInteraction
        A tuple with the two functions: `do(str, ...) -> None` and `shows(...) -> Iterator[bool]`

    Raises
    ------
    NotFoundError
        If no object matches the patterns in `kwargs`

    """
    
    on_all_objs = find_all_objs(roots, **kwargs)
    if len(on_all_objs) == 0:
        raise NotFoundError(f"no widget from {_pprint(root)} with {kwargs}") 
    
    def do(action_name: str, **kwargs) -> None:
        for on_obj in on_all_objs:
            obj = find_obj(on_obj, **kwargs)
            fail_on_error(obj)
            _do(obj, action_name)

    def shows(**kwargs) -> Iterator[bool]:
        if len(kwargs) == 0:
            raise TypeError("shows must have at least one argument, got 0")
        for on_obj in on_all_objs:
            yield next(_find_all_descendants(on_obj, kwargs), None) is not None

    return (do, shows)


###########################################################################
def _wait_for_app(name: str, timeout: Optional[float]= None) -> Optional[Atspi.Object]:
    desktop = Atspi.get_desktop(0)
    start = time.time()
    app = None
    timeout = timeout or 5
    while app is None and (time.time() - start) < timeout:
        gen = (child for child in obj_children(desktop)
               if child and child.get_name() == name)
        app = next(gen, None)
        if app is None:
            time.sleep(0.6)
    return app


App = tuple[subprocess.Popen, Optional[Atspi.Object]]

def run(path: Union[str, Path],
        name: Optional[str]= None,
        timeout: Optional[float]= None) -> App:
    """Runs the command in a new os process. Waits for application to
    appear in desktop.

    Starts a new os process and runs the given command in it. The
    command should start an application that implements the at-spi and
    provides a user interface.

    After running the command, the function will wait until the
    corresponding application appears in the desktop and it is
    accessible through the at-spi.

    Finally it will return the Popen object that controls the process
    and the at-spi object that controls the accessible application.

    When, after a given timeout, it cannot find the application, it
    will stop waiting and return None instead of the at-spi object.

    Parameters
    ----------
    path : str | pathlib.Path
       The file path of the command

    name : str, optional
       The application's name that will be shown in the desktop.
       When no name is given, the function will forge one.

    Returns
    -------
    (subprocess.Popen, Atspi.Object)
       Popen object that is in charge of running the command in a new process.
       The Atspi object that represents the application in the desktop, or None
       if it couldn't find the application after a given timeout.


    :param path: str | pathlib.Path The file path of the command

    """
    
    name = name or f"{path}-test-{str(random.randint(0, 100000000))}"
    process = subprocess.Popen([path, '--name', name])
    app = _wait_for_app(name, timeout)
    return (process, app)


def dump_desktop() -> None:
    """Prints the list of applications in desktop.

    *NB:* This function is not usefull for writing test. It maybe be
    useful for debuging purposes.

    """

    desktop = Atspi.get_desktop(0)
    for app in obj_children(desktop):
        print(app.get_name())


def _draw_branches(path: TreePath) -> str:
    return f"{draw_1}{draw_2}"


def dump_app(name: str) -> None:
    """Prints the tree of at-spi objects of an application.

    *NB:* This function is not usefull for writing test. It maybe be
    useful for debuging purposes.

    Parameters
    ----------
    name : str
        The name of the application.

    """
    
    desktop = Atspi.get_desktop(0)
    apps = [app for app in obj_children(desktop) if app and app.get_name() == name]
    if len(apps) == 0:
        print(f"App {name} not found in desktop")
        print(f"Try running {__file__} without args to get the list of apps")
        sys.exit(0)
    app = apps[0]
    for path, node in tree_walk(app):
        interfaces = node.get_interfaces()
        try:
            idx = interfaces.index('Action')
            n = node.get_n_actions()
            actions = [node.get_action_name(i) for i in range(n)]
            interfaces[idx] = f"Action({','.join(actions)})"
        except ValueError:
            pass
        role_name = node.get_role_name()
        name = node.get_name() or ""
        draw_1 = "".join("  " if nth_of.is_last() else "│ " for nth_of in path[:-1])
        draw_2 = "└ " if path[-1].is_last() else "├ "
        print(f"{draw_1}{draw_2}{role_name}({name}) {interfaces}")


def main() -> None:
    """As a script calls dump functions. Usage:
    
    {filename}         Dumps the list of applications running in the desktop

    {filename} name    Dumps the tree of at-spi objects of the application {name}
    """
    import sys
    
    if len(sys.argv) == 1:
        dump_desktop()
    else:
        dump_app(sys.argv[1])

    
if __name__ ==  '__main__':
    main()
