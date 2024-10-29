from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="cactus-commit",
    version="4.3.0",
    author="@emi",
    author_email="esauvisky@gmail.com",
    description="A tool for streamlined commit messaging using AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/esauvisky/cactus",
    packages=find_packages(),
    install_requires=requirements,
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',  # Choose your license
        'Operating System :: OS Independent',
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "cactus=cactus.cactus:main",
        ],
    },
)
