#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions

Usage:

"""
__author__ = "emi"
__version__ = "0.1.0"
__license__ = "MIT"

from loguru import logger
import sys
import argparse
import os
import openai

def setup_logging(level="DEBUG", show_module=False):
    """
    Setups better log format for loguru
    """
    logger.remove(0)    # Remove the default logger
    log_level = level
    log_fmt = u"<green>["
    log_fmt += u"{file:10.10}…:{line:<3} | " if show_module else ""
    log_fmt += u"{time:HH:mm:ss.SSS}]</green> <level>{level: <8}</level> | <level>{message}</level>"
    logger.add(sys.stderr, level=log_level, format=log_fmt, colorize=True, backtrace=True, diagnose=True)

setup_logging("INFO")

def setup_openai_token():
    openai_token = input("Enter your OpenAI token: ")
    config_dir = os.path.expanduser("~/.config/cactus")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "openai_token"), "w") as f:
        f.write(openai_token)
    logger.success("OpenAI token saved.")


def load_openai_token():
    config_dir = os.path.expanduser("~/.config/cactus")
    try:
        with open(os.path.join(config_dir, "openai_token"), "r") as f:
            openai_token = f.read().strip()
        return openai_token
    except FileNotFoundError:
        return None


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = PARSER.add_mutually_exclusive_group()
    group.add_argument("setup", nargs='?', help="Initial setup of your OpenAI token")
    group_model = group.add_mutually_exclusive_group()
    group_model.add_argument("gen", nargs='?', help="Generates a commit message for staged changes and commits it")
    group_model.add_argument("pick", nargs='?', help="Generates five commit messages for staged changes and lets you choose one")
    group_model.add_argument("-m", "--model", default="text-davinci-003", choices=[
        "text-curie-001", "text-babbage-001", "text-davinci-003", "text-ada-001"], help="OpenAI model to use")
    group_model.add_argument("-a", "--all", action="store_true", help="Use all non staged changes instead of only staged changes")

    args = PARSER.parse_args()

    if args.setup:
        setup_openai_token()
        sys.exit(0)

    openai_token = load_openai_token()
    if openai_token is None:
        logger.error("OpenAI token not found. Please run `cactus setup` first.")
        sys.exit(1)

    openai.api_key = openai_token

    if args.gen:
        openai.Model.retrieve(args.model)
        # Generate a commit message for staged changes or all non staged changes
        if args.all:
            logger.info("Generating commit message for all non staged changes using model", args.model)
        else:
            logger.info("Generating commit message for staged changes using model", args.model)
    else:
        openai.Model.retrieve(args.model)
        # Generate five commit messages for staged changes or all non staged changes and let the user choose one
        if args.all:
            logger.info("Generating five commit messages for all non staged changes using model", args.model)
        else:
            logger.info("Generating five commit messages for staged changes using model", args.model)
