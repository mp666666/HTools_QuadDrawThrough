# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
from __future__ import division, unicode_literals
import io
import ast
import base64
import json
import os
import runpy
import shutil
import gc
import sys
import tempfile
import unittest
import zipfile

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT=os.environ.get('HTOOLS_TEST_OUTPUT',os.path.join(ROOT,'tests','_output'))
if not os.path.isdir(OUTPUT):os.makedirs(OUTPUT)
BOOT={'__name__':'installer_test','__file__':os.path.join(ROOT,'HTools_QuadDrawThrough_Install_v10.py')}
with open(BOOT['__file__'],'rb') as stream:
    eval(compile(stream.read(),BOOT['__file__'],'exec'),BOOT)
INSTALL=BOOT['_load_installer'](ROOT)


class InstallationTests(unittest.TestCase):
    def test_standalone_mel_contains_current_complete_python_payload(self):
        filename=os.path.join(ROOT,'HTools_QuadDrawThrough_v1.0_Install.mel')
        with io.open(filename,'r',encoding='ascii') as stream:
            lines=[line.strip() for line in stream]
        code=''.join(json.loads(line[2:] if line.startswith('+ ') else line)
                     for line in lines if line.startswith(('"','+ "')))
        compile(code,'standalone_installer','exec')
        tree=ast.parse(code)
        value=next(ast.literal_eval(node.value.args[0]) for node in ast.walk(tree)
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_ht_payload' for t in node.targets))
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(value))) as archive:
            self.assertIsNone(archive.testzip())
            for name in archive.namelist():
                self.assertNotIn('..',name.split('/'))
                self.assertFalse(os.path.isabs(name))
                if name.endswith('.py'):
                    data=archive.read(name)
                    compile(data,name,'exec')
                    with open(os.path.join(ROOT,name),'rb') as stream:
                        self.assertEqual(data,stream.read())
            self.assertEqual(json.loads(archive.read('package_manifest.json'))['installer_revision'],2)
            with open(os.path.join(ROOT,'LICENSE'),'rb') as stream:
                self.assertEqual(archive.read('LICENSE'),stream.read())

    def test_drop_loader_can_import_entry_from_unicode_folder(self):
        folder=tempfile.mkdtemp(prefix='install_import_',dir=OUTPUT)
        source=os.path.join(folder,'中文 安装包');os.makedirs(source)
        entry='HTools_QuadDrawThrough_Install_v10'
        for name in (entry+'.py','install.py','package_manifest.json'):
            shutil.copy2(os.path.join(ROOT,name),os.path.join(source,name))
        if sys.version_info[0]==2:
            import imp
            handle,pathname,description=imp.find_module(entry,[source])
            try:module=imp.load_module('qdt_installer_import_test',handle,pathname,description)
            finally:handle.close()
        else:
            import importlib.util
            spec=importlib.util.spec_from_file_location('qdt_installer_import_test',os.path.join(source,entry+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        actual=module._path_text(module.__file__)
        self.assertEqual(os.path.realpath(os.path.dirname(actual)),os.path.realpath(source))
        self.assertEqual(module._load_installer(source)['read_manifest'](source)['version'],'1.0.0')

    def test_python2_installer_namespace_survives_unicode_path_and_garbage_collection(self):
        folder=tempfile.mkdtemp(prefix='install_namespace_',dir=OUTPUT)
        source=os.path.join(folder,'中文 安装包');os.makedirs(source)
        for name in ('install.py','package_manifest.json'):
            shutil.copy2(os.path.join(ROOT,name),os.path.join(source,name))
        namespace=BOOT['_load_installer'](source)
        gc.collect()
        self.assertEqual(namespace['read_manifest'](source)['version'],'1.0.0')

    def test_universal_and_specific_runtime_packages(self):
        universal=INSTALL['read_manifest'](ROOT)
        for year,python in ((2018,2),(2019,2),(2020,2),(2022,2),(2022,3),
                            (2023,3),(2024,3),(2025,3),(2026,3),(2027,3)):
            INSTALL['validate_runtime'](universal,year,python)
        with self.assertRaises(RuntimeError):INSTALL['validate_runtime'](universal,2017,2)
        legacy=dict(universal,python_major=2,qt_major=5,maya_max=2022)
        with self.assertRaises(RuntimeError):INSTALL['validate_runtime'](legacy,2022,3)
        qt5=dict(universal,python_major=3,qt_major=5,maya_min=2022,maya_max=2024)
        INSTALL['validate_runtime'](qt5,2024,3)
        with self.assertRaises(RuntimeError):INSTALL['validate_runtime'](qt5,2025,3)

    def test_payload_stages_into_unicode_user_directory_and_compiles(self):
        folder=tempfile.mkdtemp(prefix='install_contract_',dir=OUTPUT)
        scripts=os.path.join(folder,'用户 脚本目录')
        os.makedirs(scripts)
        stage=INSTALL['stage_payload'](ROOT,scripts)
        self.assertEqual(os.path.dirname(stage),os.path.realpath(scripts))
        package=os.path.join(stage,'qd_through')
        self.assertTrue(os.path.isfile(os.path.join(package,'__init__.py')))
        for name in os.listdir(package):
            self.assertTrue(name.endswith('.py'))
            with open(os.path.join(package,name),'rb') as stream:
                compile(stream.read(),name,'exec')
        for name in ('install.py','HTools_QuadDrawThrough_Install_v10.py'):
            with open(os.path.join(ROOT,name),'rb') as stream:
                compile(stream.read(),name,'exec')
        self.assertEqual(INSTALL['read_manifest'](stage)['version'],'1.0.0')
        with open(os.path.join(ROOT,'LICENSE'),'rb') as expected:
            with open(os.path.join(stage,'LICENSE'),'rb') as installed:
                self.assertEqual(installed.read(),expected.read())

    def test_generated_paths_cannot_escape_script_directory(self):
        folder=tempfile.mkdtemp(prefix='install_guard_',dir=OUTPUT)
        for name in ('.','..',os.path.join('..','another-directory')):
            with self.assertRaises(RuntimeError):INSTALL['child_path'](folder,name)
        self.assertEqual(os.path.dirname(INSTALL['child_path'](folder,'HTools_QuadDrawThrough')),
                         os.path.realpath(folder))

    def test_incomplete_package_rejected_before_changing_destination(self):
        folder=tempfile.mkdtemp(prefix='install_incomplete_',dir=OUTPUT)
        source=os.path.join(folder,'source');scripts=os.path.join(folder,'scripts')
        os.makedirs(source);os.makedirs(scripts)
        before=os.listdir(scripts)
        with self.assertRaises(RuntimeError):INSTALL['stage_payload'](source,scripts)
        self.assertEqual(os.listdir(scripts),before)


if __name__=='__main__':unittest.main(verbosity=2)
