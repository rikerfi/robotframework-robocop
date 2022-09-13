import contextlib
import io
import os
import sys
from pathlib import Path

import pytest
from packaging.specifiers import Specifier

from robocop import Robocop
from robocop.config import Config
from robocop.utils.misc import ROBOT_VERSION


@contextlib.contextmanager
def isolated_output():
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    bytes_output = io.BytesIO()
    sys.stdout = io.TextIOWrapper(bytes_output, encoding="utf-8")
    sys.stderr = sys.stdout
    yield bytes_output
    sys.stdout = old_stdout
    sys.stderr = old_stderr


def convert_to_output(stdout_bytes):
    return stdout_bytes.decode("utf-8", "replace").replace("\r\n", "\n")


def get_result(encoded_output):
    stdout = convert_to_output(encoded_output.getvalue())
    return stdout.splitlines()


def normalize_result(result, test_data):
    """Remove test data directory path from paths and sort the lines."""
    test_data_str = f"{test_data}{os.path.sep}"
    return sorted([line.replace(test_data_str, "") for line in result])


def load_expected_file(test_data, expected_file):
    expected = test_data / expected_file
    with open(expected, encoding="utf-8") as f:
        return sorted([line.rstrip("\n").replace(r"${/}", os.path.sep) for line in f])


def configure_robocop_with_rule(args, runner, rule, path, src_files):
    runner.from_cli = True
    config = Config()
    if src_files is None:
        paths = [str(path)]
    else:
        paths = [str(path / src_file) for src_file in src_files]
    if args is None:
        args = []
    elif isinstance(args, str):
        args = args.split()
    arguments = ["--include", ",".join(rule)]
    arguments.extend(
        [
            "--format",
            "{source}:{line}:{col} [{severity}] {rule_id} {desc}",
            "--configure",
            "return_status:quality_gate:E=0:W=0:I=0",
            *args,
            *paths,
        ]
    )
    config.parse_opts(arguments)
    runner.config = config
    return runner


class RuleAcceptance:
    SRC_FILE = "."
    EXPECTED_OUTPUT = "expected_output.txt"

    def check_rule(self, expected_file, config=None, rule=None, src_files=None, target_version=None):
        if not self.enabled_in_version(target_version):
            pytest.skip(f"Test enabled only for RF {target_version}")
        test_data = self.test_class_dir
        expected = load_expected_file(test_data, expected_file)
        if rule is None:
            rule = [self.rule_name]
        robocop_instance = Robocop(from_cli=False)
        robocop_instance = configure_robocop_with_rule(config, robocop_instance, rule, test_data, src_files)
        with isolated_output() as output, pytest.raises(SystemExit):
            try:
                robocop_instance.run()
            finally:
                sys.stdout.flush()
                result = get_result(output)
        actual = normalize_result(result, test_data)
        assert actual == expected, f"{actual} != {expected}"

    @property
    def test_class_dir(self):
        return Path(sys.modules[self.__class__.__module__].__file__).parent

    @property
    def rule_name(self):
        return self.test_class_dir.stem.replace("_", "-")

    def rule_is_enabled(self, robocop_rules):
        return robocop_rules[self.rule_name].enabled_in_version

    @staticmethod
    def enabled_in_version(target_version):
        if target_version is None:
            return True
        return ROBOT_VERSION in Specifier(target_version)
