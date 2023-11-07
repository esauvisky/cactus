# Cactus: Streamlined Commit Messaging

## About Cactus

Cactus is a developer's assistant that modernizes the commit process by automating commit message generation. It leverages OpenAI's cutting-edge language models to analyze staged code changes and formulate meaningful commit messages that adhere to Conventional Commits standards. Cactus simplifies version control documentation, making it more maintainable and understandable.

## What's New in Cactus

- **Interactive Changelog Creation**: Compile detailed changelogs from your commit history, styled for public release notes.
- **Advanced Diff Grouping**: Improved algorithms for segmenting changeset hunks mean smarter, more relevant commit message suggestions.
- **Enhanced Rename Detection**: Redesigned to account for file and directory renames to maintain a transparent, traceable commit history.

## Watch Cactus in Action

![Demo](demo.mp4)

*Click the image above to see how Cactus transforms your commit process.*

## Getting Started

Follow the step-by-step instructions below to install and configure Cactus.
For system-specific setup guidelines, skip to the corresponding section after completing the general steps.

### General Setup Instructions

1. Clone the Cactus repository and move to its directory:
   ```sh
   git clone https://github.com/your-username/Cactus.git
   cd Cactus
   ```
2. Create and activate a virtual environment:
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install Python dependencies:
   ```sh
   pip install -r requirements.txt
   ```
4. Configure Cactus with your OpenAI token by running:
   ```sh
   cactus setup
   ```
5. Use the `cactus` command followed by a subcommand to start automating your commit messages.

## Detailed Command Guide

- `cactus generate`: Invokes AI-powered analysis to generate commit messages. Optional options:
  - `NUM`: Number of commits to generate.
  - `-a AFFINITY`: Affinity for message grouping (0.0 - 1.0).
- `cactus changelog`: Builds a changelog from a specified commit hash to the current HEAD.
  - `SHA`: Starting commit for changelog generation.
  - `-p PATHSPEC`: Consider changes solely within the given paths.
- `cactus setup`: Sets the OpenAI token for utilizing the AI model services.

Remember to check the `--help` option for each subcommand to learn more about its functionalities and options.

## Installation

Follow these steps to install Cactus on your system:

1.  Change to the directory where Cactus is located using the command `cd /path/to/Cactus/`.
1.  Create a virtual environment using the command `python3 -m venv .venv`.
1.  Activate the virtual environment using the command `source .venv/bin/activate`.
1.  Install the required libraries using pip with the command `pip install -r requirements.txt`.
1.  Create a shell script at `/usr/bin` that runs the Cactus script within the virtual environment:

    ```sh
    #!/usr/bin/env bash
    MAIN_DIR=/path/to/Cactus/

    cd "$PWD"
    source "$MAIN_DIR/".venv/bin/activate
    python3 "$MAIN_DIR/cactus.py" "$@"
    ```
    > Don't forget to edit `MAIN_DIR` above!
1.  Set execute permissions for the shell script using the command `chmod +x /usr/bin/cactus`.
1.  Run `cactus` once and enter your OpenAPI token.
1.  You're all set!
1.  Yeah, yeah, I'll make it a pip package one day.

## Installation for Windows Users

Follow these steps to install Cactus on your system:

1. Change to the directory where Cactus is located using the command `cd /path/to/Cactus/`.
2. Create a virtual environment using the command `python -m venv .venv`.
3. Activate the virtual environment using the command `.venv\Scripts\activate.bat`.
4. Install the required libraries using pip with the command `pip install -r requirements.txt`.
5. Create a batch script at `%USERPROFILE%\AppData\Local\Microsoft\WindowsApps` that runs the Cactus script within the virtual environment:

```batch
@echo off
set MAIN_DIR=/path/to/Cactus/

cd "%CD%"
call "%MAIN_DIR%\.venv\Scripts\activate.bat"
python "%MAIN_DIR%\cactus.py" %*
```
> Don't forget to edit `MAIN_DIR` above!
6. Rename the batch script to `cactus.bat`.
7. Run `cactus` once and enter your OpenAPI token.
8. You're all set!

## Contribute

Cactus is an open-source project, and contributions are warmly welcomed. Whether it's through reporting bugs, suggesting improvements, or adding new features, your input is valuable and appreciated. Join us in enhancing Cactus by submitting pull requests and sharing your ideas through issues on our GitHub repository.
