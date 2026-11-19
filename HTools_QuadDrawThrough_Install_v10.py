# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Drag this complete package's installer into any supported Maya viewport."""
from __future__ import division, unicode_literals
import io
import os
import sys
import tempfile
import traceback


def _path_text(value):
    if isinstance(value,type(u'')):
        return value
    for encoding in (sys.getfilesystemencoding() or 'utf-8','utf-8'):
        try:
            candidate=value.decode(encoding)
            if os.path.exists(candidate):
                return candidate
        except UnicodeError:
            continue
    return value.decode(sys.getfilesystemencoding() or 'utf-8')


def _load_installer(source):
    filename=os.path.join(source,'install.py')
    namespace={'__file__':filename,'__name__':'qdt_install_implementation'}
    with open(filename,'rb') as stream:
        diagnostic_name=filename.encode('utf-8') if sys.version_info[0]==2 else filename
        code=compile(stream.read(),diagnostic_name,'exec')
    # Python 2 runpy temporary modules clear the function globals after return.
    # An explicit namespace keeps this installer's imports and functions alive.
    eval(code,namespace)
    return namespace


def onMayaDroppedPythonFile(*args):
    from maya import cmds
    logfile=os.path.join(_path_text(tempfile.gettempdir()),'HTools_QuadDrawThrough_install.log')
    try:
        source=os.path.dirname(os.path.abspath(_path_text(__file__)))
        entry=_load_installer(source)
        destination=entry['install'](source)
        with io.open(logfile,'w',encoding='utf-8') as stream:
            stream.write('SUCCESS\nInstalled: '+destination+'\n')
        cmds.confirmDialog(title='HTools_QuadDrawThrough 1.0 安装成功',
            message='已安装到：\n'+destination+'\n\n'
                '工具架：单击开关，双击设置。\n安装后可移动或删除解压目录。',button=['确定'])
        return True
    except Exception:
        details=traceback.format_exc()
        print(details)
        try:
            if not isinstance(details,type(u'')):
                details=details.decode('utf-8','replace')
            with io.open(logfile,'w',encoding='utf-8') as stream:
                stream.write(details)
        except (OSError,IOError):
            pass
        cmds.confirmDialog(title='HTools_QuadDrawThrough 安装失败',
            message='请查看脚本编辑器中的报错。\n日志：'+logfile+'\n\n'+details.splitlines()[-1],
            button=['确定'])
        return False


if __name__=='__main__':
    onMayaDroppedPythonFile()
