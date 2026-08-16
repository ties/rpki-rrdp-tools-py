import logging

import pytest

from rrdp_tools.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_logging():
    root = logging.getLogger()
    tools = logging.getLogger("rrdp_tools")
    handlers, root_level, tools_level = root.handlers[:], root.level, tools.level
    yield
    for handler in root.handlers[:]:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(root_level)
    tools.setLevel(tools_level)


def levels() -> tuple[int, int]:
    return (
        logging.getLogger("rrdp_tools").getEffectiveLevel(),
        logging.getLogger().getEffectiveLevel(),
    )


class TestLevels:
    def test_default_keeps_third_party_quiet(self):
        configure_logging()
        assert levels() == (logging.INFO, logging.WARNING)

    def test_single_v_is_debug_for_our_package_only(self):
        configure_logging(verbose=1)
        assert levels() == (logging.DEBUG, logging.WARNING)

    def test_double_v_includes_third_party(self):
        configure_logging(verbose=2)
        assert levels() == (logging.DEBUG, logging.DEBUG)

    def test_log_level_overrides_verbose(self):
        configure_logging(verbose=2, log_level="warning")
        assert levels() == (logging.WARNING, logging.WARNING)

    def test_unknown_log_level(self):
        with pytest.raises(ValueError, match="Unknown log level"):
            configure_logging(log_level="LOUD")


class TestStreams:
    def test_info_goes_to_stdout(self, capsys):
        configure_logging()
        logging.getLogger("rrdp_tools.test").info("status")

        captured = capsys.readouterr()
        assert "status" in captured.out
        assert captured.err == ""

    def test_warning_goes_to_stderr(self, capsys):
        configure_logging()
        logging.getLogger("rrdp_tools.test").warning("problem")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "problem" in captured.err


class TestLogFile:
    def test_creates_missing_directories(self, tmp_path):
        log_file = tmp_path / "2026" / "08" / "20260816.log"
        configure_logging(log_file=log_file)
        logging.getLogger("rrdp_tools.test").info("first")

        assert "first" in log_file.read_text()

    def test_appends_rather_than_truncating(self, tmp_path):
        log_file = tmp_path / "20260816.log"

        configure_logging(log_file=log_file)
        logging.getLogger("rrdp_tools.test").info("first")
        for handler in logging.getLogger().handlers:
            handler.close()

        configure_logging(log_file=log_file)
        logging.getLogger("rrdp_tools.test").info("second")

        contents = log_file.read_text()
        assert "first" in contents
        assert "second" in contents

    def test_records_below_the_level_are_not_written(self, tmp_path):
        log_file = tmp_path / "20260816.log"
        configure_logging(log_file=log_file)
        logging.getLogger("rrdp_tools.test").debug("hidden")
        logging.getLogger("aiohttp.test").info("third party")

        assert log_file.read_text() == ""

    def test_no_file_handler_without_a_log_file(self):
        configure_logging()
        assert not [
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.FileHandler)
        ]
