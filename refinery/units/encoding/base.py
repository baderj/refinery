#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import math

from refinery.units import Arg, Unit
from refinery.lib.argformats import numseq


_DEFAULT_ALPH_STR = R'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
_DEFAULT_ALPHABET = B'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
_LARGER_ALPHABETS = {
    64: b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',
    85: b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~'
}


class base(Unit):
    """
    Encodes and decodes integers in arbitrary base.
    """
    def __init__(
        self,
        base: Arg(type=numseq, metavar='base|alphabet', help=(
            R'Either the base to be used or an alphabet. If an explicit alphabet is given, its length '
            R'determines the base. The default base 0 treats the input as a Python integer literal. If '
            F'a numeric base is given, digits from the alphabet "{_DEFAULT_ALPH_STR}" are used. ')) = 0,
        strip_padding: Arg.Switch('-s', help='Do not add leading zeros to the output.') = False,
        little_endian: Arg.Switch('-e', help='Use little endian byte order instead of big endian.') = False,
        strict_digits: Arg.Switch('-d', help='Check that all input digits are part of the alphabet.') = False,
    ):
        super().__init__(
            base=base,
            strip_padding=strip_padding,
            little_endian=little_endian,
            strict_digits=strict_digits,
        )

    @property
    def _args(self):
        base = self.args.base
        if isinstance(base, int):
            if not base:
                return 0, B''
            if base in _LARGER_ALPHABETS:
                return base, _LARGER_ALPHABETS[base]
            if base not in range(2, len(_DEFAULT_ALPHABET) + 1):
                raise ValueError(F'base may only be an integer between 2 and {len(_DEFAULT_ALPHABET)}')
            return base, _DEFAULT_ALPHABET[:base]
        if len(set(base)) != len(base):
            raise ValueError('the given alphabet contains duplicate letters')
        return len(base), bytearray(base)

    @property
    def byteorder(self):
        return 'little' if self.args.little_endian else 'big'

    def reverse(self, data):
        base, alphabet = self._args
        self.log_info('using byte order', self.byteorder)
        number = int.from_bytes(data, byteorder=self.byteorder)

        if base == 0:
            return B'0x%X' % number
        if base > len(alphabet):
            raise ValueError(F'Only {len(alphabet)} available; not enough to encode base {base}')

        data_bits = len(data) * 8
        base_bits = math.log2(base)
        result = bytearray()

        while data_bits >= 1:
            number, k = divmod(number, base)
            result.append(alphabet[k])
            if not number and self.args.strip_padding:
                break
            data_bits -= base_bits

        result.reverse()
        return result

    def process(self, data: bytearray):
        base, alphabet = self._args
        if base and base != 64 and not self.args.strict_digits:
            check = set(alphabet)
            index = 0
            it = iter(data)
            for b in it:
                if b not in check:
                    break
                index += 1
            for b in it:
                if b in check:
                    data[index] = b
                    index += 1
            self.log_info(F'stripped {len(data)-index} invalid digits from input data')
            del data[index:]
        if len(alphabet) <= len(_DEFAULT_ALPHABET):
            defaults = _DEFAULT_ALPHABET[:base]
            if alphabet != defaults:
                self.log_info('translating input data to a default alphabet for faster conversion')
                data = data.translate(bytes.maketrans(alphabet, defaults))
            result = int(data, self.args.base)
        elif len(alphabet) == 64:
            import base64
            _b64_alphabet = _LARGER_ALPHABETS[64]
            if alphabet != _b64_alphabet:
                data = data.translate(bytes.maketrans(alphabet, _b64_alphabet))
            return base64.b64decode(data + b'===', validate=self.args.strict_digits)
        elif len(alphabet) == 85:
            import base64
            _b85_alphabet = _LARGER_ALPHABETS[85]
            if alphabet != _b85_alphabet:
                data = data.translate(bytes.maketrans(alphabet, _b85_alphabet))
            return base64.b85decode(data)
        else:
            self.log_warn('very long alphabet, unable to use built-ins; reverting to (slow) fallback.')
            result = 0
            lookup = {digit: k for k, digit in enumerate(alphabet)}
            for digit in data:
                result *= base
                result += lookup[digit]
        if not base or self.args.strip_padding:
            size, rest = divmod(result.bit_length(), 8)
            size += int(bool(rest))
        else:
            size = (len(data) - 1 + alphabet.index(data[0]) / base) * math.log2(base) / 8
            size = math.ceil(size)
        return result.to_bytes(size, byteorder=self.byteorder)
