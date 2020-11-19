import argparse
import logging
import os
import sys
import subprocess

from typing import Sequence, Optional

import orangecanvas.utils.shtools as sh


def run_after_exit(
        command: Sequence[str] = (), log: Optional[str] = None
) -> None:
    """
    Run the `command` after this process exits.
    """
    # pass read end of a pipe to subprocess. It blocks to read from it
    # and will not succeed until the write end is closed which will happen at
    # this process's exit (assuming `w` is not leaked in a fork).
    command = ["--arg=" + c for c in command]
    if log is not None:
        command.append("--log=" + log)
    command = ["-m", __name__, *command]
    r, w = os.pipe()
    p = sh.python_process(
        command,
        stdin=r, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # close the read end of the pipe
    os.close(r)
    # Popen warns in __del__ if child did not complete yet (should
    # double fork to do this right, but since we exit immediately anyways).
    run_after_exit.processes.append(p)


run_after_exit.processes = []


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", default=0, type=int)
    ap.add_argument("-a", "--arg", action='append', default=[])
    ap.add_argument("--log", help="Log file", type=argparse.FileType("w"))
    ns, rest = ap.parse_known_args(argv)

    if ns.log is not None:
        logging.basicConfig(level=logging.INFO, stream=ns.log)
    log = logging.getLogger(__name__)

    if ns.f is not None:
        readfd = int(ns.f)
    else:
        readfd = 0

    # read form readfd (an os.pipe read end) until EOF indicating parent
    # closed the pipe (i.e. did exit)
    log.info("Blocking on read from fd: %d", readfd)
    c = os.read(readfd, 1)
    if c != b"":
        log.error("Unexpected content %r from parent", c)
    else:
        log.info("Parent closed fd; %d")

    if ns.arg:
        log.info("Starting new process with cmd: %r", ns.arg)
        kwargs = {}
        p = sh.create_process(ns.arg, **kwargs)
        main.p = p
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
