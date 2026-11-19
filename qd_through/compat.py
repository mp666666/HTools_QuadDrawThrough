# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Small Python 2/3 and Maya Qt 5/6 compatibility layer."""
from __future__ import division, unicode_literals
import sys
import time
import weakref
from maya import cmds

MAYA_YEAR = int(cmds.about(apiVersion=True)) // 10000
if MAYA_YEAR < 2018:
    raise RuntimeError('HTools_QuadDrawThrough requires Maya 2018 or newer.')

if MAYA_YEAR >= 2025:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance, isValid
    QT_BINDING = 'PySide6'
else:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance, isValid
    QT_BINDING = 'PySide2'

try:
    string_types = (basestring,)
    text_type = unicode
except NameError:
    string_types = (str,)
    text_type = str

monotonic = getattr(time, 'monotonic', time.time)


def as_text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        for encoding in ('utf-8', sys.getfilesystemencoding() or 'utf-8'):
            try:
                return value.decode(encoding)
            except UnicodeError:
                pass
        return value.decode('utf-8', 'replace')
    try:
        return text_type(value)
    except UnicodeError:
        return as_text(str(value))


def global_position(event):
    if hasattr(event, 'globalPosition'):
        return event.globalPosition().toPoint()
    return event.globalPos()


def touch(cache, key):
    # OrderedDict.move_to_end is unavailable in Python 2.7.
    value = cache.pop(key)
    cache[key] = value


_FINALIZERS = set()


def finalize(obj, callback, *args):
    if hasattr(weakref, 'finalize'):
        return weakref.finalize(obj, callback, *args)
    # Keep the weak reference alive without retaining the target object.
    def collected(reference):
        _FINALIZERS.discard(reference)
        callback(*args)
    reference = weakref.ref(obj, collected)
    _FINALIZERS.add(reference)
    return reference
