"""GuiCommands package.

Composes the four feature mixins (employee / consolidation / rsch /
reconciliation) plus the shared :class:`CommandContext`. The original
monolith was 734 lines; each feature is now a separate module so they
can evolve independently.

Layout:
    gui_commands/
        __init__.py        - this file, public surface
        _base.py           - CommandContext, finish() helper
        _employee.py       - refresh + employee table actions
        _consolidation.py  - 3 consolidation commands
        _rsch.py           - RSCH commands + helpers
        _reconciliation.py - reconciliation commands
"""
from core.ui.gui_commands._base import CommandContext
from core.ui.gui_commands._consolidation import ConsolidationCommandsMixin
from core.ui.gui_commands._employee import EmployeeCommandsMixin
from core.ui.gui_commands._reconciliation import ReconciliationCommandsMixin
from core.ui.gui_commands._rsch import RschCommandsMixin


class GuiCommands(
    EmployeeCommandsMixin,
    ConsolidationCommandsMixin,
    ReconciliationCommandsMixin,
):
    # ReconciliationCommandsMixin transitively provides RschCommandsMixin
    # (it inherits from it for the source-file resolution helpers), so
    # we don't list RschCommandsMixin here. Adding it would create a
    # diamond that Python refuses to linearise.
    pass
    """Single dispatch surface for the GUI.

    The class holds no real behaviour of its own — it stitches the
    four feature mixins together and exposes ``_record_dashboard_result``
    so each mixin's ``finish()`` call can update the dashboard tab.
    Public methods are reachable from ``GuiMaster`` via plain attribute
    access (e.g. ``self.commands.run_consolidation()``).
    """

    def __init__(
        self,
        root,
        config_controller,
        app_controller,
        employee_vm,
        consolidation_vm,
        sidebar,
        employee_table,
        stats_panel,
        dashboard_tabs=None,
        operation_state=None,
        toasts=None,
    ):
        self.ctx = CommandContext(
            root=root,
            config_controller=config_controller,
            app_controller=app_controller,
            employee_vm=employee_vm,
            consolidation_vm=consolidation_vm,
            sidebar=sidebar,
            employee_table=employee_table,
            stats_panel=stats_panel,
            dashboard_tabs=dashboard_tabs,
            operation_state=operation_state,
            toasts=toasts,
        )
        # Compatibility shim: the original code stored the operation
        # state on both ``self`` and ``self.ctx``. New code should
        # read ``self.ctx.operation_state``; old tests may still poke
        # ``self.operation_state``. Both point at the same object.
        self.operation_state = self.ctx.operation_state
        self.toasts = self.ctx.toasts
        self._apply_saved_rsch_mode()

    def _record_dashboard_result(self, label, ok, msg, path) -> None:
        if self.ctx.dashboard_tabs is not None:
            self.ctx.dashboard_tabs.record_result(label, ok, msg, path)


__all__ = ["GuiCommands", "CommandContext"]
