# SPDX-FileCopyrightText: 2026 InOrbit, Inc.
# SPDX-License-Identifier: MIT

from inorbit_connector import metrics as m


def test_module_exposes_framework_meter():
    assert hasattr(m, "meter")


def test_module_exposes_counter_instruments():
    assert hasattr(m, "execution_loop_ticks")
    assert hasattr(m, "execution_loop_errors")


def test_counters_accept_add():
    m.execution_loop_ticks.add(1)
    m.execution_loop_errors.add(1)
