from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.ui.gui_commands import GuiCommands


@pytest.fixture
def commands_fixture():
    root = MagicMock()
    root.after.side_effect = lambda _ms, fn: fn()

    sidebar = MagicMock()
    sidebar.get_date.return_value = datetime(2026, 4, 13)
    sidebar.get_rsch_mode.return_value = "combined"

    cmd = GuiCommands(
        root=root,
        config_controller=MagicMock(),
        app_controller=MagicMock(),
        employee_vm=MagicMock(),
        consolidation_vm=MagicMock(),
        sidebar=sidebar,
        employee_table=MagicMock(),
        stats_panel=MagicMock(),
    )
    cmd.config_controller.config = {}
    return cmd, root, sidebar


def test_run_rsch_report_happy_path(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/in.xlsx",),
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_called_once_with("disabled")
    cmd.app_controller.run_rsch_report.assert_called_once()

    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [Path("C:/in.xlsx")]
    assert args[1] == Path("C:/out.xlsx")
    assert args[2] == datetime(2026, 4, 13)
    assert callable(args[3])

    assert [
        Path(p) for p in cmd.config_controller.config["rsch"]["recent_sources"]
    ] == [Path("C:/in.xlsx")]
    assert Path(cmd.config_controller.config["rsch"]["last_output_dir"]) == Path("C:/")
    cmd.config_controller.save_config.assert_called_once()
    assert cmd.config_controller.config["rsch"]["mode"] == "combined"


def test_run_rsch_report_cancel_on_source(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.filedialog.askopenfilenames", return_value=()):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_not_called()
    cmd.app_controller.run_rsch_report.assert_not_called()


def test_run_rsch_report_cancel_on_output(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/in.xlsx",),
        ),
        patch("core.ui.gui_commands.filedialog.asksaveasfilename", return_value=""),
    ):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_not_called()
    cmd.app_controller.run_rsch_report.assert_not_called()


def test_run_rsch_report_uses_saved_sources_when_confirmed(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    cmd.config_controller.config = {
        "rsch": {
            "recent_sources": ["C:/saved1.xlsx", "C:/saved2.xlsx"],
            "last_output_dir": "C:/reports",
        }
    }

    with (
        patch("core.ui.gui_commands.Path.exists", return_value=True),
        patch("core.ui.gui_commands.messagebox.askyesnocancel", return_value=True),
        patch("core.ui.gui_commands.filedialog.askopenfilenames") as ask_many,
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/reports/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    ask_many.assert_not_called()
    sidebar.set_rsch_state.assert_called_once_with("disabled")
    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [Path("C:/saved1.xlsx"), Path("C:/saved2.xlsx")]


def test_run_rsch_report_resolves_relative_saved_sources(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    app_root = Path("C:/Project/APP")
    cmd.config_controller.config = {
        "rsch": {
            "recent_sources": ["../рсч всех/РСЧ Моника.xlsx"],
            "last_output_dir": "../РСЧ",
        }
    }
    cmd.config_controller.resolve_path.side_effect = lambda p: app_root / p

    with (
        patch("core.ui.gui_commands.Path.exists", return_value=True),
        patch("core.ui.gui_commands.messagebox.askyesnocancel", return_value=True),
        patch("core.ui.gui_commands.filedialog.askopenfilenames") as ask_many,
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/Project/РСЧ/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    ask_many.assert_not_called()
    sidebar.set_rsch_state.assert_called_once_with("disabled")
    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [app_root / "../рсч всех/РСЧ Моника.xlsx"]


def test_run_rsch_report_collects_sources_from_multiple_dirs(commands_fixture):
    cmd, _root, _sidebar = commands_fixture

    with (
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            side_effect=[("C:/a/in1.xlsx",), ("D:/b/in2.xlsx",), ()],
        ),
        patch("core.ui.gui_commands.messagebox.askyesno", side_effect=[True, False]),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [Path("C:/a/in1.xlsx"), Path("D:/b/in2.xlsx")]


def test_run_rsch_report_accepts_five_selected_files(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=(
                "C:/in1.xlsx",
                "C:/in2.xlsx",
                "C:/in3.xlsx",
                "C:/in4.xlsx",
                "C:/in5.xlsx",
            ),
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_called_once_with("disabled")
    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [
        Path("C:/in1.xlsx"),
        Path("C:/in2.xlsx"),
        Path("C:/in3.xlsx"),
        Path("C:/in4.xlsx"),
        Path("C:/in5.xlsx"),
    ]


def test_run_rsch_report_legacy_per_file_mode_uses_combined_file(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    sidebar.get_rsch_mode.return_value = "per_file"

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/in1.xlsx", "C:/in2.xlsx"),
        ),
        patch(
            "core.ui.gui_commands.filedialog.askdirectory",
            return_value="C:/outdir",
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    cmd.app_controller.run_rsch_report_batch.assert_not_called()
    cmd.app_controller.run_rsch_report.assert_called_once()
    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == [Path("C:/in1.xlsx"), Path("C:/in2.xlsx")]
    assert args[1] == Path("C:/out.xlsx")
    assert cmd.config_controller.config["rsch"]["mode"] == "combined"


def test_run_rsch_report_no_longer_asks_for_output_directory(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    sidebar.get_rsch_mode.return_value = "per_file"

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/team_a/report.xlsx", "D:/team_b/report.xlsx"),
        ),
        patch("core.ui.gui_commands.filedialog.askdirectory") as ask_dir,
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    ask_dir.assert_not_called()
    cmd.app_controller.run_rsch_report_batch.assert_not_called()


def test_run_rsch_report_month_uses_selected_period(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    start = datetime(2026, 4, 1)
    end = datetime(2026, 4, 30)
    sidebar.get_month_range.return_value = (start, end)

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/in.xlsx",),
        ),
        patch(
            "core.ui.gui_commands.filedialog.askdirectory",
            return_value="C:/outdir",
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/rsch_period.xlsx",
        ),
    ):
        cmd.run_rsch_report_month()

    sidebar.set_rsch_state.assert_called_once_with("disabled")
    cmd.app_controller.run_rsch_report_period.assert_called_once()
    args = cmd.app_controller.run_rsch_report_period.call_args[0]
    assert args[0] == [Path("C:/in.xlsx")]
    assert args[1] == Path("C:/rsch_period.xlsx")
    assert args[2] == start
    assert args[3] == end
    assert callable(args[4])


def test_run_rsch_report_month_legacy_per_file_mode_uses_combined_period_file(
    commands_fixture,
):
    cmd, _root, sidebar = commands_fixture
    start = datetime(2026, 4, 1)
    end = datetime(2026, 4, 30)
    sidebar.get_month_range.return_value = (start, end)
    sidebar.get_rsch_mode.return_value = "per_file"

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=False),
        patch(
            "core.ui.gui_commands.filedialog.askopenfilenames",
            return_value=("C:/in.xlsx",),
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/rsch_period.xlsx",
        ),
    ):
        cmd.run_rsch_report_month()

    sidebar.set_rsch_state.assert_called_once_with("disabled")
    cmd.app_controller.run_rsch_report_period_batch.assert_not_called()
    cmd.app_controller.run_rsch_report_period.assert_called_once()
    args = cmd.app_controller.run_rsch_report_period.call_args[0]
    assert args[0] == [Path("C:/in.xlsx")]
    assert args[1] == Path("C:/rsch_period.xlsx")
    assert args[2] == start
    assert args[3] == end
    assert callable(args[4])
    assert cmd.config_controller.config["rsch"]["mode"] == "combined"


def test_apply_saved_rsch_mode_on_init(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    cmd.config_controller.config = {"rsch": {"mode": "per_file"}}

    cmd._apply_saved_rsch_mode()
    sidebar.set_rsch_mode.assert_called_with("combined")
    assert cmd.config_controller.config["rsch"]["mode"] == "combined"


def test_on_rsch_complete_success(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=True),
        patch("core.ui.gui_commands.open_path") as open_path,
    ):
        cmd._on_rsch_complete(True, "ok", Path("C:/out.xlsx"))

    sidebar.set_rsch_state.assert_called_once_with("normal")
    open_path.assert_called_once()
    assert open_path.call_args[0][0].endswith("out.xlsx")


def test_on_rsch_complete_error(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.messagebox.showerror") as showerror:
        cmd._on_rsch_complete(False, "fail", None)

    sidebar.set_rsch_state.assert_called_once_with("normal")
    showerror.assert_called_once_with("Ошибка", "fail")


def test_on_reconciliation_complete_success_opens_file(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=True),
        patch("core.ui.gui_commands.open_path") as open_path,
    ):
        cmd._on_reconciliation_complete(True, "ok", Path("C:/out.xlsx"))

    sidebar.set_reconciliation_state.assert_called_once_with("normal")
    open_path.assert_called_once()
    assert open_path.call_args[0][0].endswith("out.xlsx")


def test_on_reconciliation_complete_error(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.messagebox.showerror") as showerror:
        cmd._on_reconciliation_complete(False, "fail", None)

    sidebar.set_reconciliation_state.assert_called_once_with("normal")
    showerror.assert_called_once_with("Ошибка", "fail")


def test_run_reconciliation_report_uses_selected_master_and_selected_rsch_file(
    commands_fixture,
):
    cmd, _root, sidebar = commands_fixture
    sidebar.get_date.return_value = datetime(2026, 4, 21)
    cmd.employee_vm.get_master_path.return_value = Path("C:/Master_Report.xlsx")

    with (
        patch(
            "core.ui.gui_commands.filedialog.askopenfilename",
            side_effect=[
                "C:/chosen_master.xlsx",
                "C:/boris.xlsx",
                "C:/ivan.xlsx",
                "C:/rsch.xlsx",
            ],
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out/reconciliation.xlsx",
        ),
    ):
        cmd.run_reconciliation_report()

    sidebar.set_reconciliation_state.assert_called_once_with("disabled")
    cmd.app_controller.run_reconciliation_report.assert_called_once_with(
        {
            "Общий": Path("C:/chosen_master.xlsx"),
            "Борис": Path("C:/boris.xlsx"),
            "Иван": Path("C:/ivan.xlsx"),
        },
        Path("C:/rsch.xlsx"),
        Path("C:/out/reconciliation.xlsx"),
        datetime(2026, 4, 21),
        cmd._on_reconciliation_complete,
    )


def test_run_reconciliation_report_cancel_on_master_file(commands_fixture):
    cmd, _root, sidebar = commands_fixture
    cmd.employee_vm.get_master_path.return_value = Path("C:/Master_Report.xlsx")

    with (
        patch("core.ui.gui_commands.filedialog.askopenfilename", return_value=""),
    ):
        cmd.run_reconciliation_report()

    sidebar.set_reconciliation_state.assert_not_called()
    cmd.app_controller.run_reconciliation_report.assert_not_called()


def test_run_auto_reconciliation_day_uses_saved_sources_and_output(
    commands_fixture,
):
    cmd, _root, sidebar = commands_fixture
    sidebar.get_date.return_value = datetime(2026, 4, 21)
    source = Path("C:/rsch/source.xlsx")
    cmd.config_controller.config = {
        "rsch": {
            "recent_sources": [str(source)],
            "last_output_dir": "C:/out",
            "mode": "combined",
        }
    }

    with (
        patch.object(Path, "exists", return_value=True),
        patch("core.ui.gui_commands.messagebox.askyesnocancel", return_value=True),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out/Отчет_расхождений_21.04.2026.xlsx",
        ),
    ):
        cmd.run_auto_reconciliation_day()

    sidebar.set_reconciliation_state.assert_called_once_with("disabled")
    cmd.app_controller.run_auto_reconciliation_day.assert_called_once_with(
        [source],
        Path("C:/out/Отчет_расхождений_21.04.2026.xlsx"),
        datetime(2026, 4, 21),
        cmd._on_auto_reconciliation_complete,
    )


def test_on_rsch_complete_batch_success_opens_folder(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=True),
        patch("core.ui.gui_commands.open_path") as open_path,
    ):
        cmd._on_rsch_complete_batch(True, "ok", Path("C:/outdir"))

    sidebar.set_rsch_state.assert_called_once_with("normal")
    open_path.assert_called_once()
    assert Path(open_path.call_args[0][0]) == Path("C:/outdir")


def test_on_rsch_complete_batch_error(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.messagebox.showerror") as showerror:
        cmd._on_rsch_complete_batch(False, "fail", None)

    sidebar.set_rsch_state.assert_called_once_with("normal")
    showerror.assert_called_once_with("Ошибка", "fail")


def test_refresh_status_shows_error_popup(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    def fake_refresh(_app_controller, _date, _on_progress, curator=None, on_error=None):
        if on_error:
            on_error("lock error")

    cmd.employee_vm.refresh.side_effect = fake_refresh

    with patch("core.ui.gui_commands.messagebox.showerror") as showerror:
        cmd.refresh_status()

    sidebar.set_refresh_state.assert_called_once_with("disabled")
    cmd.employee_table.clear_tree.assert_called_once()
    cmd.stats_panel.set_progress.assert_called_once_with(0)
    showerror.assert_called_once_with("Ошибка", "lock error")
