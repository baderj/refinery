#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Miscellaneous helper functions.
"""
import datetime
import functools
import inspect
import itertools
import logging
import os
import sys
import io
import warnings

from typing import ByteString, Callable, Generator, Iterable, Optional, Tuple, TypeVar
from math import log
from enum import IntFlag


_T = TypeVar('_T')


def lookahead(iterator: Iterable[_T]) -> Generator[Tuple[bool, _T], None, None]:
    """
    Implements a new iterator from a given one which returns elements
    `(last, item)` where each `item` is taken from the original iterator
    and `last` is a boolean indicating whether this is the last item.
    """
    last = False
    it = iter(iterator)
    try:
        peek = next(it)
    except StopIteration:
        return
    while not last:
        item = peek
        try:
            peek = next(it)
        except StopIteration:
            last = True
        yield last, item


def get_terminal_size(default=0):
    """
    Returns the size of the currently attached terminal. If the environment variable
    `REFINERY_TERMSIZE` is set to an integer value, it takes prescedence. If the width
    of the terminal cannot be determined of if the width is less than 8 characters,
    the function returns zero.
    """
    from refinery.lib.environment import environment
    ev_terminal_size = environment.term_size.value
    if ev_terminal_size > 0:
        return ev_terminal_size
    width = default
    for stream in (sys.stderr, sys.stdout):
        if stream.isatty():
            try:
                width = os.get_terminal_size(stream.fileno()).columns
            except Exception:
                width = default
            else:
                break
    return default if width < 2 else width - 1


def terminalfit(text: str, delta: int = 0, width: int = 0, **kw) -> str:
    """
    Reformats text to fit the given width while not mangling bullet point lists.
    """
    import textwrap
    import re

    width = width or get_terminal_size()
    width = width - delta

    def isol(t): return re.match(R'^\(\d+\)|\d+[.:;]', t)
    def isul(t): return t.startswith('-') or t.startswith('*')
    def issp(t): return t.startswith('  ')

    text = text.replace('\r', '')

    def bulletpoint(line):
        wrapped = textwrap.wrap(line, width - 2, **kw)
        indent = '  ' if isul(line) else '   '
        wrapped[1:] = ['{}{}'.format(indent, line) for line in wrapped[1:]]
        return '\n'.join(wrapped)

    def fitted(paragraphs):
        for k, p in enumerate(paragraphs):
            if p.startswith(' '):
                yield p
                continue
            ol, ul = isol(p), isul(p)
            if ol or ul:
                input_lines = p.splitlines(keepends=False)
                unwrapped_line = input_lines[0].rstrip()
                lines = []
                if (ol and all(isol(t) or issp(t) for t in input_lines) or ul and all(isul(t) or issp(t) for t in input_lines)):
                    for line in input_lines[1:]:
                        if not (ol and isol(line) or ul and isul(line)):
                            unwrapped_line += ' ' + line.strip()
                            continue
                        lines.append(bulletpoint(unwrapped_line))
                        unwrapped_line = line.rstrip()
                    lines.append(bulletpoint(unwrapped_line))
                    yield '\n'.join(lines)
                    continue
            yield '\n'.join(textwrap.wrap(p, width, **kw))

    return '\n\n'.join(fitted(text.split('\n\n')))


def documentation(unit):
    """
    Return the documentation string of a given unit as it should be displayed
    on the command line. Certain pdoc3-specific reference strings are removed.
    """
    import re
    docs = inspect.getdoc(unit)
    docs = re.sub(R'`refinery\.(?:\w+\.)*(\w+)`', R'\1', docs)
    return docs.replace('`', '')


def skipfirst(iterable: Iterable[_T]) -> Generator[_T, None, None]:
    """
    Returns an interable where the first element of the input iterable was
    skipped.
    """
    it = iter(iterable)
    next(it)
    yield from it


def autoinvoke(method: Callable[..., _T], keywords: dict) -> _T:
    """
    For each parameter that `method` expects, this function looks for an entry
    in `keywords` which has the same name as that parameter. `autoinvoke` then
    calls `method` with all matching parameters forwarded in the appropriate
    manner.
    """

    kwdargs = {}
    posargs = []
    varargs = []
    kwdjoin = False

    for p in inspect.signature(method).parameters.values():
        if p.kind is p.VAR_KEYWORD:
            kwdjoin = True
        try:
            value = keywords.pop(p.name)
        except KeyError:
            if p.kind is p.VAR_KEYWORD:
                continue
            value = p.default
            if value is p.empty:
                raise ValueError(F'missing required parameter {p.name}')
        if p.kind is p.POSITIONAL_OR_KEYWORD or p.kind is p.POSITIONAL_ONLY:
            if value == p.default:
                # when equality holds, we force identity
                value = p.default
            posargs.append(value)
        elif p.kind is p.VAR_POSITIONAL:
            varargs = value
        elif p.kind is p.KEYWORD_ONLY:
            kwdargs[p.name] = value

    if kwdjoin:
        kwdargs.update(keywords)

    return method(*posargs, *varargs, **kwdargs)


def entropy_fallback(data: ByteString) -> float:
    if isinstance(data, memoryview):
        def count(b):
            return sum(1 for _b in data if _b == b)
    else:
        count = data.count
    histogram = {b: count(b) for b in range(0x100)}
    S = [histogram[b] / len(data) for b in histogram]
    return 0.0 + -sum(p * log(p, 2) for p in S if p) / 8.0


def entropy(data: ByteString) -> float:
    """
    Computes the entropy of `data` over the alphabet of all bytes.
    """
    if not data: return 0.0

    try:
        import numpy
    except ImportError:
        return entropy_fallback(data)
    _, counts = numpy.unique(memoryview(data), return_counts=True)
    probs = counts / len(data)
    # 8 bits are the maximum number of bits of information in a byte
    return 0.0 + -sum(p * log(p, 2) for p in probs) / 8.0


def index_of_coincidence(data: bytearray) -> float:
    """
    Computes the index of coincidence of `data` over the alphabet of all bytes.
    """
    if not data:
        return 0.0
    N = len(data)
    if N < 2:
        return 0.0
    try:
        import numpy
    except ImportError:
        C = [data.count(b) for b in range(0x100)]
    else:
        C = numpy.histogram(
            numpy.frombuffer(data, dtype=numpy.uint8),
            numpy.arange(0x100))[0]
    d = 1 / N / (N - 1)
    return float(sum(x * (x - 1) * d for x in C))


def isstream(obj) -> bool:
    return hasattr(obj, 'read')


def isbuffer(obj) -> bool:
    """
    Test whether `obj` is an object that supports the buffer API, like a bytes
    or bytearray object.
    """
    try:
        with memoryview(obj):
            return True
    except TypeError:
        return False


def splitchunks(data: ByteString, size: int, truncate=False) -> Iterable[ByteString]:
    if len(data) <= size:
        if not truncate or len(data) == size:
            yield data
        return
    total = len(data)
    if truncate:
        total -= len(data) % size
    for k in range(0, total, size):
        yield data[k:k + size]


def make_buffer_mutable(data: ByteString):
    """
    Returns a mutable version of the input data. Already mutable inputs are returned
    as themselves, i.e. no copy operation occurs in these cases.
    """
    if isinstance(data, bytearray):
        return data
    if isinstance(data, memoryview) and not data.readonly:
        return data
    return bytearray(data)


def infinitize(it):
    if not isinstance(it, (
        itertools.cycle,
        itertools.repeat,
        itertools.count
    )):
        if not hasattr(it, '__iter__') and not hasattr(it, '__next__'):
            it = (it, )
        return itertools.cycle(it)
    return it


try:
    cached_property = functools.cached_property
except AttributeError:
    def cached_property(p):
        return property(functools.lru_cache(maxsize=1)(p))


class NoLogging:
    class Mode(IntFlag):
        STD_OUT = 0b0001
        STD_ERR = 0b0010
        WARNING = 0b0100
        LOGGING = 0b1000
        ALL     = 0b1111 # noqa

    def __init__(self, mode: Mode = Mode.WARNING | Mode.LOGGING):
        self.mode = mode

    def __enter__(self):
        if self.mode & NoLogging.Mode.LOGGING:
            logging.disable(logging.CRITICAL)
        if self.mode & NoLogging.Mode.WARNING:
            self._warning_filters = list(warnings.filters)
            warnings.filterwarnings('ignore')
        if self.mode & NoLogging.Mode.STD_ERR:
            self._stderr = sys.stderr
            sys.stderr = io.TextIOWrapper(open(os.devnull, 'wb'), encoding='latin1')
        if self.mode & NoLogging.Mode.STD_OUT:
            self._stdout = sys.stdout
            sys.stdout = io.TextIOWrapper(open(os.devnull, 'wb'), encoding='latin1')
        return self

    def __exit__(self, *_):
        if self.mode & NoLogging.Mode.LOGGING:
            logging.disable(logging.NOTSET)
        if self.mode & NoLogging.Mode.WARNING:
            warnings.resetwarnings()
            warnings.filters[:] = self._warning_filters
        if self.mode & NoLogging.Mode.STD_ERR:
            sys.stderr.close()
            sys.stderr = self._stderr
        if self.mode & NoLogging.Mode.STD_OUT:
            sys.stdout.close()
            sys.stdout = self._stdout


def one(iterable: Iterable[_T]) -> _T:
    it = iter(iterable)
    try:
        top = next(it)
    except StopIteration:
        raise LookupError
    try:
        next(it)
    except StopIteration:
        return top
    else:
        raise LookupError


def isodate(iso: str) -> Optional[datetime.datetime]:
    if len(iso) not in range(16, 25):
        return None
    iso = iso[:19].replace(' ', 'T', 1)
    try:
        try:
            return datetime.datetime.fromisoformat(iso)
        except AttributeError:
            return datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
