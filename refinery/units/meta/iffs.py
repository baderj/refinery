#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from refinery.units.meta import Arg, ConditionalUnit


class iffs(ConditionalUnit):
    """
    Filter incoming chunks depending on whether they contain a given binary substring.
    """
    def __init__(
        self,
        needle: Arg(help='the string to search for'),
        negate=False,
        backup=False,
        single=False,
    ):
        super().__init__(
            needle=needle,
            negate=negate,
            backup=backup,
            single=single,
        )

    def match(self, chunk):
        return self.args.needle in chunk
