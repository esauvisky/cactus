import subprocess
from loguru import logger


def setup_logging(log_lvl="DEBUG", options={}):
    file = options.get("file", False)
    function = options.get("function", False)
    process = options.get("process", False)
    thread = options.get("thread", False)

    log_fmt = (u"<n><d><level>{time:HH:mm:ss.SSS} | " + f"{'{file:>15.15}' if file else ''}" + f"{'{function:>15.15}' if function else ''}" + f"{':{line:<4} | ' if file or function else ''}"
               + f"{'{process.name:>12.12} | ' if process else ''}" + f"{'{thread.name:<11.11} | ' if thread else ''}" + u"{level:1.1} | </level></d></n><level>{message}</level>")

    logger.configure(
        handlers=[{
            "sink": lambda x: print(x, end=""),
            "level": log_lvl,
            "format": log_fmt,
            "colorize": True,
            "backtrace": True,
            "diagnose": True
        }],
        levels=[
            {"name": "TRACE", "color": "<white><dim>"},
            {"name": "DEBUG", "color": "<cyan><dim>"},
            {"name": "INFO", "color": "<white>"}
        ]
    )  # type: ignore # yapf: disable

def run(cmd, capture_output=False):
    try:
        logger.debug(f"Running command: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        if capture_output:
            logger.debug(f"Command output: {result.stdout}")
            logger.debug(f"Command error: {result.stderr}")
    except Exception as e:
        logger.error(f"Failed to run command: {cmd}")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout=b'', stderr=str(e).encode())
    return result
