import os
import subprocess
import sys
import tempfile
from loguru import logger
from unidiff import PatchSet, UnidiffParseError
from .utils import run


def get_git_diff(context_size):
    if run("git diff --cached --quiet --exit-code").returncode == 0:
        logger.error("No staged changes found, please stage the desired changes.")
        sys.exit(1)

    result = run(
        f"git diff --inter-hunk-context={context_size} --unified={context_size} --minimal -p --staged --binary",
        capture_output=True)
    if result.returncode != 0:
        logger.error(f"Failed to get git diff: {result.stderr.decode('utf-8', errors='ignore')}")
        sys.exit(1)

    if b"CRLF" in result.stderr:
        logger.warning("Warning: Line endings (CRLF vs LF) may cause issues. Consider configuring Git properly.")

    return result.stdout # Return binary data


def restore_changes(full_diff):
    with open("/tmp/cactus.diff", "wb") as f:
        f.write(full_diff)
        run("git apply --cached --unidiff-zero --ignore-whitespace --whitespace=fix /tmp/cactus.diff")


def parse_diff(git_diff):
    for _ in range(5):
        try:
            return PatchSet.from_string(git_diff)
        except UnidiffParseError:
            git_diff += os.linesep
    raise Exception("Failed to parse diff")


def stage_changes(hunks):
    with tempfile.NamedTemporaryFile(mode='wb', prefix='.tmp_patch_', delete=False) as fd:
        filename = fd.name

    for hunk in hunks:
        with open(filename, 'ab') as fd:
            fd.write(hunk)
            fd.write(b'\n')

    result = subprocess.run(
        f'git apply --cached --unidiff-zero --ignore-whitespace --whitespace=fix {filename}',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    if result.returncode != 0:
        logger.error(f"Failed to apply patch: {result.stdout.decode('utf-8', errors='ignore')}\n{result.stderr.decode('utf-8', errors='ignore')}")
        raise Exception("Failed to apply patch")
