#!/usr/bin/env python3

"""
Setup script for AI Shell.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the contents of README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

# Read requirements
requirements = []
if (this_directory / "requirements.txt").exists():
    with open(this_directory / "requirements.txt") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="ai-shell",
    version="1.0.0",
    author="AI Shell Team",
    author_email="ai-shell@example.com",
    description="A natural language command line interface utility",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/ai-shell",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Shells",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "ai-shell=ai_shell:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["config.yaml", "*.md"],
    },
    keywords="ai, shell, command-line, natural-language, llm, automation",
    project_urls={
        "Bug Reports": "https://github.com/example/ai-shell/issues",
        "Source": "https://github.com/example/ai-shell",
        "Documentation": "https://github.com/example/ai-shell/blob/main/README.md",
    },
)