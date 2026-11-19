# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Portable, per-user Maya installer. Supports Python 2.7 and Python 3."""
from __future__ import division, unicode_literals
import io
import json
import os
import shutil
import sys
import tempfile
import uuid

PRODUCT = 'HTools_QuadDrawThrough'
VERSION = '1.0.0'


def path_text(value):
    try:
        text_type = unicode
    except NameError:
        text_type = str
    if isinstance(value,text_type):
        return value
    for encoding in (sys.getfilesystemencoding() or 'utf-8','utf-8'):
        try:
            candidate=value.decode(encoding)
            if os.path.exists(candidate):
                return candidate
        except UnicodeError:
            continue
    return value.decode(sys.getfilesystemencoding() or 'utf-8')


def read_manifest(source):
    with io.open(os.path.join(source,'package_manifest.json'),'r',encoding='utf-8') as stream:
        manifest=json.load(stream)
    if manifest.get('product')!=PRODUCT or manifest.get('version')!=VERSION:
        raise RuntimeError('安装包信息不匹配，请完整解压 1.0 安装包。')
    return manifest


def validate_runtime(manifest,maya_year,python_major):
    maximum=manifest.get('maya_max')
    if maya_year<manifest['maya_min'] or (maximum and maya_year>maximum):
        raise RuntimeError('此安装包不适用于 Maya %s，请使用对应版本包或通用包。'%maya_year)
    if manifest.get('python_major') not in (None,python_major):
        raise RuntimeError('当前 Maya 使用 Python %s，请改用通用包或对应的 Python 版本包。'%python_major)
    qt_major=6 if maya_year>=2025 else 5
    if manifest.get('qt_major') not in (None,qt_major):
        raise RuntimeError('当前 Maya 的 Qt 版本与安装包不匹配，请使用通用包。')


def child_path(root,name):
    """Validate generated move/delete targets under the chosen script dir."""
    root=os.path.realpath(os.path.abspath(root))
    path=os.path.realpath(os.path.abspath(os.path.join(root,name)))
    if os.path.dirname(path)!=root or path==root:
        raise RuntimeError('安装目标路径不合法。')
    return path


def stage_payload(source,scripts):
    package=os.path.join(source,'qd_through')
    required=('__init__.py','compat.py','interaction.py','ui.py','surface_query.py','undo_plugin.py')
    if not all(os.path.isfile(os.path.join(package,name)) for name in required):
        raise RuntimeError('缺少插件文件。请完整解压，保持安装脚本和 qd_through 文件夹在一起。')
    if not os.path.isfile(os.path.join(source,'LICENSE')):
        raise RuntimeError('Missing LICENSE. Please use the complete source or universal installer.')
    stage=tempfile.mkdtemp(prefix='.'+PRODUCT+'-stage-',dir=scripts)
    stage=child_path(scripts,os.path.basename(stage))
    try:
        destination=os.path.join(stage,'qd_through')
        os.makedirs(destination)
        for name in sorted(os.listdir(package)):
            if name.endswith('.py') and os.path.isfile(os.path.join(package,name)):
                shutil.copy2(os.path.join(package,name),os.path.join(destination,name))
        shutil.copy2(os.path.join(source,'package_manifest.json'),os.path.join(stage,'package_manifest.json'))
        shutil.copy2(os.path.join(source,'LICENSE'),os.path.join(stage,'LICENSE'))
    except Exception:
        shutil.rmtree(child_path(scripts,os.path.basename(stage)))
        raise
    return stage


def stop_loaded():
    module=sys.modules.get('qd_through')
    if module:
        module.disable()
    interaction=sys.modules.get('qd_through.interaction')
    if interaction and hasattr(interaction,'clear_cache'):
        interaction.clear_cache()
    ui=sys.modules.get('qd_through.ui')
    if ui and ui.WINDOW:
        try:
            ui.WINDOW.close()
            ui.WINDOW.deleteLater()
        except RuntimeError:
            pass


def load_installed(destination):
    previous=sys.modules.get('qd_through')
    if previous:
        old_root=os.path.dirname(os.path.dirname(os.path.abspath(path_text(previous.__file__))))
        while old_root in sys.path:
            sys.path.remove(old_root)
    retired=[]
    for name in list(sys.modules):
        if name=='qd_through' or name.startswith('qd_through.'):
            retired.append(sys.modules.pop(name))
    if sys.version_info[0]==2:
        # Python 2 clears a retired module's globals even when old Undo command
        # instances still reference its classes. Keep those module objects
        # alive for this session; do not flush the user's Undo history.
        keep=getattr(sys,'_htools_qdt_retired_modules',None)
        if keep is None:
            keep=[]
            sys._htools_qdt_retired_modules=keep
        keep.extend(retired)
    while destination in sys.path:
        sys.path.remove(destination)
    sys.path.insert(0,destination)
    import qd_through
    return qd_through


def setup_shelf():
    from maya import cmds,mel
    from qd_through.commands import command_prefix
    prefix=command_prefix()
    buttons=[]
    for button in cmds.lsUI(type='shelfButton') or []:
        annotation=cmds.shelfButton(button,q=True,annotation=True) or ''
        if annotation.startswith(('Quad Draw Through',PRODUCT)):
            buttons.append(button)
    if not buttons:
        top=mel.eval('$qdtShelfTop=$gShelfTopLevel')
        shelf=cmds.tabLayout(top,q=True,selectTab=True)
        buttons=[cmds.shelfButton(parent=shelf)]
    parents=set()
    for button in buttons:
        cmds.shelfButton(button,e=True,label=PRODUCT,imageOverlayLabel='QD OFF',
            image='quadDraw_NEX32.png',annotation=PRODUCT+' 1.0 - single click toggle; double click settings',
            sourceType='python',command=prefix+'qd_through.toggle()',
            doubleClickCommand=prefix+'qd_through.show()')
        parents.add(cmds.shelfButton(button,q=True,parent=True))
        settings_items=[]
        for menu in cmds.shelfButton(button,q=True,popupMenuArray=True) or []:
            for item in cmds.popupMenu(menu,q=True,itemArray=True) or []:
                if cmds.menuItem(item,q=True,label=True)==PRODUCT+' 设置':
                    settings_items.append(item)
        if not settings_items:
            menu=cmds.popupMenu(parent=button,button=3)
            settings_items=[cmds.menuItem(parent=menu,label=PRODUCT+' 设置')]
        for item in settings_items:
            cmds.menuItem(item,e=True,sourceType='python',command=prefix+'qd_through.show()')
    for shelf in parents:
        filename='shelf_'+shelf.split('|')[-1]
        cmds.saveShelf(shelf,os.path.join(path_text(cmds.internalVar(userShelfDir=True)),filename))
    return buttons


def install(source=None):
    from maya import cmds
    source=os.path.realpath(os.path.abspath(path_text(source or os.path.dirname(__file__))))
    manifest=read_manifest(source)
    validate_runtime(manifest,int(cmds.about(apiVersion=True))//10000,sys.version_info[0])
    if cmds.about(batch=True):
        raise RuntimeError('请在 Maya 图形界面中拖入安装脚本。')
    scripts=os.path.realpath(os.path.abspath(path_text(cmds.internalVar(userScriptDir=True))))
    if not os.path.isdir(scripts):
        os.makedirs(scripts)
    destination=child_path(scripts,PRODUCT)
    stage=stage_payload(source,scripts)
    backup=None
    try:
        stop_loaded()
        if os.path.exists(destination):
            backup=child_path(scripts,'.'+PRODUCT+'-backup-'+uuid.uuid4().hex[:12])
            os.rename(destination,backup)
        try:
            os.rename(stage,destination)
            stage=None
        except Exception:
            if backup:
                os.rename(backup,destination)
            raise
        module=load_installed(destination)
        from qd_through import commands
        commands.register()
        setup_shelf()
        module.show()
        module.ui.sync_state()
    finally:
        if stage and os.path.isdir(stage):
            shutil.rmtree(child_path(scripts,os.path.basename(stage)))
    # Retain the previous installation, including any user-added files.
    print(PRODUCT+' '+VERSION+' installed: '+destination)
    return destination


def onMayaDroppedPythonFile(*args):
    install()
    return True


if __name__=='__main__':
    onMayaDroppedPythonFile()
