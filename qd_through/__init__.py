# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""HTools Quad Draw Through for Maya 2018 and newer."""
from __future__ import division, unicode_literals
__version__ = '1.0.0'


def show():
    from . import ui
    return ui.show()


def disable():
    from . import interaction
    interaction.disable()
    from . import ui
    ui.sync_state()


def set_enabled(enabled):
    from . import interaction, ui
    if enabled and interaction.ACTIVE is None:
        interaction.enable(status=ui.report_status)
    elif not enabled:
        interaction.disable()
    ui.sync_state()


def toggle():
    from . import interaction
    set_enabled(interaction.ACTIVE is None)
