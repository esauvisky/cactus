Installing Cactus
=================

Follow these steps to install Cactus on your system:

1.  Change to the directory where Cactus is located using the command `cd /path/to/Cactus/`.
2.  Create a virtual environment using the command `python3 -m venv .venv`.
3.  Activate the virtual environment using the command `source .venv/bin/activate`.
4.  Install the required libraries using pip with the command `pip install -r requirements.txt`.
5.  Create a shell script at `/usr/bin` that runs the Cactus script within the virtual environment:

```sh
#!/usr/bin/env bash
MAIN_DIR=/path/to/Cactus/

cd "$PWD"
source "$MAIN_DIR/".venv/bin/activate
python3 "$MAIN_DIR/cactus.py" "$@"
```

6.  Set execute permissions for the shell script using the command `chmod +x /usr/bin/cactus`.
7.  Run `cactus` once and enter your OpenAPI token.
8.  You're all set!

Using Cactus
============

1.  Go to your repository.
2.  Stage the desired changes.
3.  Run `cactus`.
4.  Choose your preferred option and press enter.

For further customization, check `cactus --help`.
