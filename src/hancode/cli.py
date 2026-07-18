"""Compatibility alias for :mod:`hancode.interfaces.cli`."""

import sys as _sys

from hancode.interfaces import cli as _implementation
from hancode.interfaces.cli import *  # noqa: F403

_sys.modules[__name__] = _implementation
