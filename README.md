# Cactus Automates Commits Through Uncomplicated Suggestions

## Demo
<video width="100%" height="100%" controls>
  <source src="https://github.com/esauvisky/cactus/blob/4efccd3cbedc409a1190a935f96c57f9d81af088/.video.mp4" type="video/mp4">
</video>

## About

Cactus is a tool that automates the commit process by automatically generating commit messages suggestions based on the staged changes. It uses the OpenAPI CLI to generate the suggestions.

___

## Usage

1. Stage your changes:

       $ git add [...]
1. Run `cactus`:

       $ cactus
1. Celebrate for lazyness.

___

## Requirements

-   Python 3.6 or higher
-   OpenAPI CLI
-   A bunch of pip packages

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
