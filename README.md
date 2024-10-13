# Cactus: AI-Powered Commit Message Generator

Cactus is an command-line tool that leverages AI to automate and enhance the process of creating Git commit messages. By analyzing staged changes, **Cactus Automates Commits Through Uncomplicated Suggestions**.

## Demo

https://github.com/user-attachments/assets/bb3553db-78d5-42b1-888c-9e9e6a4edb77

## Features

- **AI-Powered Commit Generation**: Utilizes OpenAI's GPT models or Google's Gemini models to analyze code changes and generate appropriate commit messages.
- **Customizable Commit Grouping**: Allows specifying the number of commits to generate, intelligently grouping related changes.
- **Interactive Changelog Creation**: Generates comprehensive changelogs between specified Git commits.
- **Multi-Model Support**: Compatible with various AI models, including GPT-3.5, GPT-4, and Gemini.
- **Conventional Commits**: Adheres to the Conventional Commits standard for consistent, readable commit histories.

## Installation

Install Cactus using pip:

```shell
$ pip install cactus-commit
```

Set up your API key(s):

```shell
$ cactus setup OpenAI  # For OpenAI API
# or
$ cactus setup Gemini  # For Google Gemini API
```

## Usage

### Generate Commit Messages

Add the files you want to create commits for to the staging area:

```shell
$ git add myfile1.py myfile2.py
```
> Anything left unstaged will be ignored when generating commit messages.

Run `cactus` to generate commit messages:

```shell
$ cactus
```

If you want to force a specific number of commits, pass the number as an argument:

```shell
cactus 3 # Will generate 3 commits
```


### Create a Changelog

```sh
cactus changelog [SHA] [-p PATHSPEC]
```
- `SHA`: The starting commit hash for the changelog.

### Additional Options

- `-d, --debug`: Enable debug logging.
- `-c, --context-size`: Set the context size for git diff (default: 1).
- `-m, --model`: Specify the AI model to use (e.g., "gpt-4", "gemini-1.5-pro").

## How It Works

1. Cactus analyzes staged Git changes.
2. It uses AI to understand the context and significance of the changes.
3. Based on the analysis, it generates commit messages or changelogs.
4. Users can interactively accept, regenerate, or adjust the number of commits.
