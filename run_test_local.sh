#!/bin/bash

uv sync
uv run pytest -xv "$@"
