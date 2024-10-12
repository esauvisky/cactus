import os
import subprocess
import sys
import tempfile
from loguru import logger
from unidiff import PatchSet, UnidiffParseError
from utils import run

def get_git_diff(context_size):
    result = run("git diff --cached --quiet --exit-code")
    if result.returncode == 0:
        logger.error("No staged changes found, please stage the desired changes.")
        sys.exit(1)

    cmd = f"git diff --inter-hunk-context={context_size} --unified={context_size} --minimal -p --staged --binary"
    result = run(cmd)
    if result.returncode != 0:
        logger.error(f"Failed to get git diff: {result.stderr}")
        sys.exit(1)

    if "CRLF" in result.stderr:
        logger.warning("Warning: Line endings (CRLF vs LF) may cause issues. Consider configuring Git properly.")

    return result.stdout

def restore_changes(full_diff):
    with open("/tmp/cactus.diff", "wb") as f:
        f.write(full_diff.encode('utf-8'))
    run("git apply --cached --unidiff-zero --ignore-whitespace /tmp/cactus.diff")

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
            fd.write(str(hunk).encode('utf-8'))
            fd.write(b'\n')

    result = subprocess.run(
        f'git apply --cached --unidiff-zero --ignore-whitespace {filename}',
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')

    if result.returncode != 0:
        logger.error(f"Failed to apply patch: {result.stderr}")
        raise Exception("Failed to apply patch")

    os.unlink(filename)
