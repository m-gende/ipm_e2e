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

Implementation of Gherkin steps::

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

    ## Before leaving, clean up your mess
    process and process.kill()


"""

from __future__ import annotations

from collections.abc import ByteString
from pathlib import Path
import random
import re
import subprocess
import time
from typing import Any, AnyStr, Callable, Iterable, Iterator, NamedTuple, Optional, Protocol, TypeVar, Union

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi

__all__ = [
    'perform_on',
    'perform_on_each',
    'find_obj',
    'find_all_objs',
    'obj_get_attr',
    'obj_children',
    'tree_walk',
    'run',
    'is_error',
    'fail_on_error',
    'Either',
    'MatchArgs',
]


class NotFoundError(Exception): pass


T = TypeVar('T')
Either = Union[Exception, T]
"""The classic Either type, i.e. a value of type T or an error.

*N.B.:* The typing and implementation of the functions using this type
is quite relaxed (unorthodox).

"""


def is_error(x: Either[Any]) -> bool:
    """Checks whether any python object represents an error.
    
    This function is intended to be used with values of type ``Either``.

    Parameters
    ----------
    x : Either[T]
        The object to check

    Returns
    -------
    bool
        whether it's an error

    """
    return isinstance(x, Exception)


def fail_on_error(x: Either[Any]) -> Any:
    """Raises an exception on error.

    Raiese an exception when the python object represents an error,
    otherwise returns the object itself.

    Parameters
    ----------
    x : Either[T]
        The object to check

    Returns
    -------
    T
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


MatchPattern = Union[AnyStr,
                     re.Pattern,
                     Callable[[Atspi.Object],bool],
                     Callable[[Any],bool]]

#MatchAargs = dict[str, MatchPattern]
from typing import Dict
MatchArgs = Dict[str, MatchPattern]
"""A dict containing a list of patterns an at-spi object should match.

An object matches the list of patterns if and only if it matches all
the patterns in the list. 

Each pair ``name: value`` is interpreted as follows:

    **name = 'when':** Predicate on the object.

        The value is a function ``Atspi.Object -> bool``. This
        function returns whether or not the at-spi objects matches
        this pattern.

    **name = 'nth':** Position of the object.

        The value must be the position of the at-spi object among its
        siblings. As usual the positions start at 0, and negative
        indexes are refered to the end of the list.

    **name = 'path':** TODO

    **name = '...':** Otherwise, one of the object's atrributes.

        The name is interpreted as the name of one object's attribute,
        and the value is interpreted as follows:

            **value = str | bytes:** String or bytes.

                The value must equal to the value of the object's
                attribute.

            **value = re.Pattern:** A regular expression.

                The object's attribute value must match the given re.

            **value = function(Any -> bool):** A predicate on the attribute's value.

                The function must return True when called with the
                object's attribute value as argument.

"""

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
    
    elif name == 'when':
        return value(obj, path)
    
    # From now on, the name is the name of an object's attribute
    elif type(value) == str or isinstance(value, ByteString):
        return obj_get_attr(obj, name) == value
    
    elif type(value) == re.Pattern:
        attr_value = obj_get_attr(obj, name)
        if is_error(attr_value):
            return False
        return value.fullmatch(attr_value) is not None
    
    elif callable(value):
        return value(obj_get_attr(obj, name))
    
    # It looks like an error
    else:
        TODO


def _find_all_descendants(root: Atspi.Object, kwargs: MatchArgs) -> Iterable[Atspi.Object]:
    if len(kwargs) == 0:
        descendants = (obj for _path, obj in tree_walk(root))
    else:
        descendants = (obj for path, obj in tree_walk(root)
                       if all(_match(obj, path, name, value) for name, value in kwargs.items()))
    return descendants

    
def find_obj(root: Atspi.Object, **kwargs: MatchArgs) -> Either[Atspi.Object]:
    """Searchs for the first at-spi object that matches the arguments.

    This functions searchs the given `root` object and its descendants
    (inorder), looking for the first object that matches the patterns
    in `kwargs`.

    When `kwargs` is empty, the `root` object is selected.

    Parameters
    ----------
    root : Atspi.Object
        The object to start the search from
    **kwargs
        See :py:data:`MatchArgs`

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

    
def find_all_objs(roots: Union[Atspi.Object, Iterable[Atspi.Object]], **kwargs: MatchArgs) -> list[Atspi.Object]:
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
        See :py:data:`MatchArgs`

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


# El nombre de la acción es un parámetro porque hay acciones con
# espacios en el nombre. No intentamos que sea un atributo que
# contiene un objeto callable, o cualquier opción que implique que el
# nombre tiene que ser un _python name_.
#
# Usamos un Protocol porque no hay otra forma de definir el callable con
# **kwargss :_(
# https://mypy.readthedocs.io/en/stable/protocols.html#callback-protocols
class UserDo(Protocol):
    def __call__(name: str, **kwargs: MatchArgs) -> None: ...
UIShows = Callable[..., bool]
UIInteraction = tuple[UserDo, UIShows]

class UserForeachDo(Protocol):
    def __call__(name: str, **kwargs: MatchArgs) -> None: ...
UIEachShows = Callable[..., Iterator[bool]]
UIMultipleInteraction = tuple[UserForeachDo, UIEachShows]


def _as_iterable(objs: Obj_S) -> Iterable[Atspi.Object]:
    return (objs,) if isinstance(objs, Atspi.Object) else objs
    
               
def _do(obj: Atspi.Object, action_name: str) -> None:
    idx = _get_action_idx(obj, action_name)
    if idx is None:
        names = _get_actions_names(obj)
        raise NotFoundError(f"widget {_pprint(obj)} has no action named '{name}', got: {','.join(names)}")
    obj.do_action(idx)

    
def perform_on(root: Atspi.Object, **kwargs: MatchArgs) -> UIInteraction:
    """Constructs functions that interact with one part of the user interface.

    For the given at-spi object, this function finds the first
    descendant that matches the patterns in `kwargs`. Then, it selects
    the part of the UI given by the subtree which root is the found
    object and constructs the following functions that performs
    actions on that subtree:

    .. function:: do(action_name : str, **kwargs: MatchArgs) -> None

       Performs an action on the first descendant at-spi object that
       matches the patterns.

       :param str action_name: The name of the action
       :param \*\*kwargs: See :py:data:`MatchArgs`
       :raises NotFoundError: if no object mathces the patterns in kwargs
       :raises NotFoundError: if the matching object doesn't provide the give action

    .. function:: shows(**kwargs: MatchArgs) -> bool

       Checks whether the UI shows the information given by the patterns.

       Note that the pattern should specify both the information to be
       shown and the at-spi object that contains that information.

       :param \*\*kwargs: See :py:data:`MatchArgs`
       :return: Whether any object matches the patterns
       :rtype: bool

    These functions interact, using at-spi, with the subtree rooted at
    the at-spi object found. They implement two basic interactions,
    intended to replace the users' interaction.

    Parameters
    ----------
    root : Atspi.Object
        The at-spi object to start the search from

    **kwargs
        See :py:data:`MatchArgs`

    Returns
    -------
    UIInteraction
        A tuple with the two functions: :py:func:`do` and :py:func:`shows`

    Raises
    ------
    NotFoundError
        If no object matches the patterns in `kwargs`

    """
        
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


def perform_on_each(roots: Iterable[Atspi.Object], **kwargs: MatchArgs) -> UIMultipleInteraction:
    """Constructs functions that interact with some parts of the user interface.

    This function is similar to :py:func:`perform_on`, but instead of
    selecting one part (subtree) of the UI, it selects a collection of
    them.

    For each object in `roots`, it selects a subtree that starts at
    the first descendant that matches the patterns in `kwargs`. Then
    it constructs the following functions that performs actions on
    that collections of subtrees:

    .. function:: foreach_do(action_name : str, **kwargs: MatchArgs) -> None

       For each subtree performs an action on the first descendant
       that matches the patterns.

       :param str action_name: The name of the action
       :param \*\*kwargs: See :py:data:`MatchArgs`
       :raises NotFoundError: If no object matches the patterns in kwargs
       :raises NotFountError: If the matching object doesn't provide the given action

    .. function:: each_shows(**kwargs: MatchArgs) -> Iterator[bool]

       For each subtree checks wheter the UI shows the information
       given by the patterns.

       Note that the pattern should specify both the information to be
       shown and the at-spi object that contains that information.

       Note that the result is an iterator which data can be
       aggregated using the builtins ``any`` or ``all``.

       :param \*\*kwargs: See :py:data:`MatchArgs`
       :return: A collection of booleans indicating whether any object matches the patterns for each root object
       :rtype: Iterator[bool]

    These functions will perform the interaction on every subtree. As
    in :py:func:`perform_on`, they implement, using at-spi, two basic
    interactions, intended to replace the users' interaction.

    Parameters
    ----------
    roots : Union[Atspi.Object, Iterable[Atspi.Object]]
        The object/s to start the search from

    **kwargs
        See :py:data:`MatchArgs`

    Returns
    -------
    UIMultipleInteraction
        A tuple with the two functions: :py:func:`foreach_do` and :py:func:`each_shows`

    Raises
    ------
    NotFoundError
        If no object matches the patterns in `kwargs`

    """

    on_objs = [ fail_on_error(find_obj(root, **kwargs))
                for root in roots ]

    def do(action_name: str, **kwargs) -> None:
        for on_obj in on_objs:
            _do(fail_on_error(find_obj(on_obj, **kwargs)),
                action_name)

    def shows(**kwargs) -> Iterator[bool]:
        if len(kwargs) == 0:
            raise TypeError("shows must have at least one argument, got 0")
        return (not is_error(find_obj(on_obj, **kwargs)) for on_obj in on_objs)

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
    """As a script calls dump functions.

    Usage:
   
    .. program:: atspi-dump
 
    Without args, dumps the list of applications running in the desktop

    .. option:: <name>

       Dumps the tree of at-spi objects of the application {name}
    """
    import sys
    
    if len(sys.argv) == 1:
        dump_desktop()
    else:
        dump_app(sys.argv[1])

    
if __name__ ==  '__main__':
    main()
