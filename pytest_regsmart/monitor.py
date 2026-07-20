from __future__ import annotations

from _pytest.reports import TestReport


class Monitor:
    """Coleta resultados de execução dos testes."""

    def __init__(self) -> None:
        self.test_reports: list[TestReport] = []

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        if not report.skipped and report.when == "call":
            self.test_reports.append(report)
