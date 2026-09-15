#!/bin/bash

nuitka --standalone --onefile --static-libpython=yes --output-dir=. --output-filename=agent main.py