from typing import List, Optional, Generator

import os
import sys
import tempfile
import subprocess
from contextlib import contextmanager


def python_process(
        args: List[str],
        script_name: Optional[str]=None,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        **kwargs
) -> subprocess.Popen:
    """
    Run a `sys.executable` in a subprocess with `args`.

    Parameters
    ----------
    args: List[str]
        A list of arguments for the python interpreter (e.g. `['-m', 'pip' ]`)
    script_name : Optional[str]
        If supplied the `script_name` replaces 'python' as the first argument
        of `exec?` call.
    kwargs:
        Passed to subproces.Popen

    Return
    ------
    process : subprocess.Popen

    Examples
    --------
    >>> p = python_process(['--version'])
    >>> p.communicate()[0]
    'Python ...
    >>> p = python_process(['-c', 'print("hello")'])
    >>> p.communicate()[0].rstrip()
    'hello'
    """
    executable = sys.executable
    if os.name == "nt" and os.path.basename(executable) == "pythonw.exe":
        # Don't run the script with a 'gui' (detached) process.
        dirname = os.path.dirname(executable)
        executable = os.path.join(dirname, "python.exe")

    if script_name is not None:
        progname = script_name
    else:
        progname = executable
    return create_process(
        [progname] + args,
        executable=executable, stderr=stderr, stdout=stdout, **kwargs
    )


def create_process(
        args: List[str],
        executable: Optional[str] = None,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        **kwargs
) -> subprocess.Popen:
    """
    Create and return a `subprocess.Popen` instance.

    This is a thin wrapper around the `subprocess.Popen`. It only thing it
    does is it ensures that a console window does not open by default on
    Windows.
    """
    if os.name == "nt":
        # do not open a new console window for command on windows.
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW  # Python 3.7
        else:
            CREATE_NO_WINDOW = 0x08000000
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)

    return subprocess.Popen(
        args,
        executable=executable,
        stderr=stderr,
        stdout=stdout,
        universal_newlines=universal_newlines,
        **kwargs
    )


@contextmanager
def temp_named_file(
        content: str, encoding="utf-8",
        suffix: Optional[str] = None,
        prefix: Optional[str] = None,
        dir: Optional[str] = None,
) -> Generator[str, None, None]:
    """
    Create a named temporary file initialized with `contents` and yield
    its name.

    Parameters
    ----------
    content: str
        The contents to write into the temp file
    encoding: str
        Encoding
    suffix: Optional[str]
        Filename suffix
    prefix: Optional[str]
        Filename prefix
    dir: Optional[str]
        Directory where the file will be created. If None then $TEMP is used.

    Returns
    -------
    context: ContextManager
        A context manager that deletes the file on exit.

    See Also
    --------
    tempfile.mkstemp
    """
    fd, name = tempfile.mkstemp(suffix, prefix, dir=dir, text=True)
    file = os.fdopen(fd, mode="wt", encoding=encoding,)
    file.write(content)
    file.close()
    try:
        yield name
    finally:
        os.remove(name)
