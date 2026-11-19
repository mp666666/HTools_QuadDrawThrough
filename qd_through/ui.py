# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
from __future__ import division, unicode_literals
from maya import cmds
import maya.OpenMayaUI as omui
from .compat import QtCore, QtWidgets, wrapInstance, isValid, MAYA_YEAR, as_text
from . import interaction

WINDOW = None
LAST_STATUS = '已关闭；开启后自动识别当前 Live 高模和 Quad Draw 低模。'


def report_status(text):
    global LAST_STATUS
    LAST_STATUS = text
    if WINDOW and isValid(WINDOW):
        WINDOW.status.setText(text)


def sync_state():
    enabled = interaction.ACTIVE is not None
    if WINDOW and isValid(WINDOW):
        WINDOW.switch.blockSignals(True)
        WINDOW.switch.setChecked(enabled)
        WINDOW.switch.setText('辅助已开启（点击关闭）' if enabled else '辅助已关闭（点击开启）')
        WINDOW.switch.blockSignals(False)
    for button in cmds.lsUI(type='shelfButton') or []:
        try:
            if cmds.shelfButton(button,q=True,annotation=True).startswith(('Quad Draw Through','HTools_QuadDrawThrough')):
                cmds.shelfButton(button,e=True,imageOverlayLabel='QD ON' if enabled else 'QD OFF',
                    enableBackground=enabled,backgroundColor=(0.13,0.42,0.32))
        except RuntimeError:
            continue


class Window(QtWidgets.QDialog):
    def __init__(self):
        parent = wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
        super(Window,self).__init__(parent)
        self.setWindowTitle('HTools_QuadDrawThrough 1.0 — Maya %s'%MAYA_YEAR)
        self.setMinimumWidth(450)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel('按原来的流程 Make Live → 选择低模 → Quad Draw。\n'
            '只需开启辅助，自动跟随高模、低模，不需要绑定。')
        layout.addWidget(intro)
        self.switch = QtWidgets.QPushButton('辅助已关闭（点击开启）')
        self.switch.setCheckable(True)
        self.switch.toggled.connect(self.set_enabled)
        layout.addWidget(self.switch)
        self.relax_enabled=QtWidgets.QCheckBox('辅助松弛（关闭后使用 Maya 原生松弛）')
        self.relax_enabled.setChecked(interaction.SETTINGS['relax_enabled'])
        self.relax_enabled.setToolTip('只控制 Shift 左键辅助松弛；关闭后辅助拖点仍然可用。')
        layout.addWidget(self.relax_enabled)
        layout.addWidget(QtWidgets.QLabel('对称、Auto-weld 开关和容差：直接使用 Maya 原有设置。'))
        form = QtWidgets.QFormLayout()
        self.pick = QtWidgets.QSpinBox()
        self.pick.setRange(3, 30)
        self.pick.setValue(int(interaction.SETTINGS['pick_radius']))
        self.radius = QtWidgets.QSpinBox()
        self.radius.setRange(10, 250)
        self.radius.setValue(int(interaction.SETTINGS['brush_radius']))
        self.strength = QtWidgets.QDoubleSpinBox()
        self.strength.setRange(0.01, 0.8)
        self.strength.setSingleStep(0.05)
        self.strength.setValue(interaction.SETTINGS['strength'])
        self.offset = QtWidgets.QDoubleSpinBox()
        self.offset.setDecimals(4)
        self.offset.setRange(-100, 100)
        self.offset.setSingleStep(0.001)
        self.offset.setValue(interaction.SETTINGS['offset'])
        self.border = QtWidgets.QCheckBox('额外锁住边界点（优先于原生松弛设置）')
        self.border.setChecked(interaction.SETTINGS['lock_border'])
        self.relax_mode=QtWidgets.QComboBox()
        self.relax_mode.addItems(['局部曲面（保持附近曲面）','视角最前层（旧方式）'])
        self.relax_mode.setCurrentIndex(1 if interaction.SETTINGS['smooth_mode']=='view' else 0)
        form.addRow('点拾取范围（屏幕像素）', self.pick)
        form.addRow('松弛半径（屏幕像素）', self.radius)
        form.addRow('松弛强度', self.strength)
        form.addRow('松弛贴合',self.relax_mode)
        form.addRow('贴合偏移（API 单位：厘米）', self.offset)
        form.addRow(self.border)
        layout.addLayout(form)
        for control in (self.pick, self.radius, self.strength, self.offset):
            control.valueChanged.connect(self.settings)
        self.border.toggled.connect(self.settings)
        self.relax_mode.currentIndexChanged.connect(self.settings)
        self.relax_enabled.toggled.connect(self.settings)
        self.sync_relax_controls()
        note = QtWidgets.QLabel('拖点：贴到当前视角最前面的 Live 表面。\n'
            '默认松弛：沿附近局部曲面调整，限制深度跳变和翻面。\n'
            '辅助松弛读取原生 Auto-Lock / 内部 / 边界 / 全部设置。\n'
            '已贴错层时先拖点纠正；局部模式不自动寻找最外层。\n'
            'Esc 取消当前笔画；Ctrl+Z 撤销整笔。\n'
            '黄色指针：松开焊接。小圆指针不代表松弛范围。\n'
            '支持 Object / World X、Y、Z 对称。\n'
            '工具架：单击开关，双击设置；关闭窗口不改变开关。\n'
            '支持 Topology 对称：先在低模中线边上初始化原生拓扑对称。\n'
            '支持原生软选择：B 开关 / 调范围，读取原生衰减。\n'
            '忽略背面和低模自身遮挡；对称另一侧仍按对称设置编辑。\n'
            '快捷键编辑器搜索 HTools_QuadDrawThroughToggle 自行绑定。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QtWidgets.QLabel(LAST_STATUS)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def set_enabled(self, enabled):
        try:
            from . import set_enabled
            set_enabled(enabled)
            self.settings()
        except Exception as exc:
            report_status(as_text(exc))
            sync_state()
            cmds.warning(as_text(exc))

    def settings(self, *unused):
        interaction.configure(pick_radius=self.pick.value(),brush_radius=self.radius.value(),
            strength=self.strength.value(),offset=self.offset.value(),lock_border=self.border.isChecked(),
            smooth_mode='view' if self.relax_mode.currentIndex()==1 else 'local',
            relax_enabled=self.relax_enabled.isChecked())
        self.sync_relax_controls()

    def sync_relax_controls(self):
        for control in (self.radius,self.strength,self.relax_mode,self.border):
            control.setEnabled(self.relax_enabled.isChecked())


def show():
    global WINDOW
    if WINDOW and isValid(WINDOW):
        WINDOW.show()
        WINDOW.raise_()
        WINDOW.activateWindow()
        return WINDOW
    WINDOW = Window()
    WINDOW.show()
    sync_state()
    return WINDOW
