"""Shared test fixtures for Code_Organism tests."""
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Alias for pytest's built-in tmp_path fixture."""
    return tmp_path


@pytest.fixture
def sample_python_file(tmp_dir):
    """A simple Python file for parsing tests."""
    p = tmp_dir / "sample.py"
    p.write_text('''\
"""Sample module for testing."""

import os
from pathlib import Path


TIMEOUT = 30


class FileProcessor:
    """Processes files."""

    def __init__(self, root: Path):
        self.root = root
        self._cache: dict = {}

    def process(self, filename: str) -> dict:
        """Process a single file."""
        path = self.root / filename
        if not path.exists():
            raise FileNotFoundError(filename)
        content = path.read_text()
        self._cache[filename] = content
        return {"name": filename, "size": len(content)}

    @property
    def cached_count(self) -> int:
        return len(self._cache)


def helper(x: int, y: int) -> int:
    """Add two numbers."""
    if x < 0:
        x = 0
    return x + y
''')
    return p


@pytest.fixture
def sample_js_file(tmp_dir):
    """A simple JavaScript file for tree-sitter tests."""
    p = tmp_dir / "sample.js"
    p.write_text('''\
import { readFile } from 'fs/promises';

const TIMEOUT = 30;

class FileProcessor {
    constructor(root) {
        this.root = root;
        this._cache = {};
    }

    async process(filename) {
        const content = await readFile(`${this.root}/${filename}`, 'utf8');
        this._cache[filename] = content;
        return { name: filename, size: content.length };
    }

    get cachedCount() {
        return Object.keys(this._cache).length;
    }
}

function helper(x, y) {
    if (x < 0) x = 0;
    return x + y;
}

export { FileProcessor, helper };
''')
    return p


@pytest.fixture
def sample_rust_file(tmp_dir):
    """A simple Rust file for tree-sitter tests."""
    p = tmp_dir / "sample.rs"
    p.write_text('''\
use std::collections::HashMap;

struct Config {
    name: String,
    value: i32,
}

impl Config {
    fn new(name: String) -> Self {
        Config { name, value: 0 }
    }

    fn process(&self) -> String {
        format!("{}: {}", self.name, self.value)
    }
}

enum Color {
    Red,
    Green,
    Blue,
}

fn helper(x: i32) -> i32 {
    x + 1
}
''')
    return p


@pytest.fixture
def sample_go_file(tmp_dir):
    """A simple Go file for tree-sitter tests."""
    p = tmp_dir / "sample.go"
    p.write_text('''\
package main

import "fmt"

type Config struct {
    Name string
}

func (c *Config) Process() string {
    return c.Name
}

func helper(x int) int {
    fmt.Println(x)
    return x + 1
}
''')
    return p


@pytest.fixture
def sample_java_file(tmp_dir):
    """A simple Java file for tree-sitter tests."""
    p = tmp_dir / "sample.java"
    p.write_text('''\
package com.example;

import java.util.List;

public class Config {
    private String name;

    public Config(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }
}
''')
    return p


@pytest.fixture
def sample_c_file(tmp_dir):
    """A simple C file for tree-sitter tests."""
    p = tmp_dir / "sample.c"
    p.write_text('''\
#include <stdio.h>

struct Config {
    char* name;
    int value;
};

void process(struct Config* c) {
    printf("%s", c->name);
}

int main() {
    return 0;
}
''')
    return p


@pytest.fixture
def sample_project(tmp_dir, sample_python_file):
    """A small multi-file Python project."""
    (tmp_dir / "utils.py").write_text('''\
"""Utility functions."""

def validate(value: str) -> bool:
    return len(value) > 0

def format_output(data: dict) -> str:
    return str(data)
''')
    (tmp_dir / "main.py").write_text('''\
"""Entry point."""
from sample import FileProcessor, helper
from utils import validate, format_output

def main():
    proc = FileProcessor(".")
    result = proc.process("test.txt")
    if validate(result["name"]):
        print(format_output(result))
    total = helper(1, 2)
    return total
''')
    return tmp_dir


@pytest.fixture
def cross_file_js_project(tmp_dir):
    """A multi-file JavaScript project where file A calls functions from file B.

    utils.js defines ``formatName`` and ``calculateTotal``.
    app.js calls both of those functions.
    After single-file parsing, app.js's calls will point to BUILTIN nodes.
    After cross-file resolution, they should retarget to the real definitions.
    """
    (tmp_dir / "utils.js").write_text('''\
function formatName(first, last) {
    return first + " " + last;
}

function calculateTotal(items) {
    let sum = 0;
    for (const item of items) {
        sum += item.price;
    }
    return sum;
}

export { formatName, calculateTotal };
''')
    (tmp_dir / "app.js").write_text('''\
import { formatName, calculateTotal } from './utils';

function main() {
    const name = formatName("Alice", "Smith");
    const total = calculateTotal([{ price: 10 }, { price: 20 }]);
    console.log(name, total);
}

export { main };
''')
    return tmp_dir


@pytest.fixture
def cross_file_python_project(tmp_dir):
    """A multi-file Python project where one file calls functions from another.

    helpers.py defines ``compute`` and ``transform``.
    runner.py calls both of those functions.
    """
    (tmp_dir / "helpers.py").write_text('''\
"""Helper functions."""

def compute(x, y):
    return x * y + 1

def transform(data):
    return [d * 2 for d in data]
''')
    (tmp_dir / "runner.py").write_text('''\
"""Runner module."""
from helpers import compute, transform

def run():
    result = compute(3, 4)
    items = transform([1, 2, 3])
    return result, items
''')
    return tmp_dir
