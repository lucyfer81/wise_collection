#!/usr/bin/env python3
"""
Script to run the complete Reddit content collection and analysis pipeline
based on the instructions in CLAUDE.md.

This script executes the pipeline phases in order:
1. Collection (reddit_collection.py)
2. Curation (curate.py)
3. Analysis (analyze_topics.py)

It uses the Python virtual environment located in .venv/bin/.
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Run a shell command and handle errors."""
    print(f"[INFO] {description}")
    print(f"[CMD] {' '.join(command)}")
    
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True
        )
        print(f"[SUCCESS] {description} completed successfully.")
        if result.stdout:
            print(f"[STDOUT] {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed with exit code {e.returncode}.")
        if e.stdout:
            print(f"[STDOUT] {e.stdout}")
        if e.stderr:
            print(f"[STDERR] {e.stderr}")
        return False

def main():
    # Define the virtual environment Python path
    venv_python = os.path.join(os.path.dirname(__file__), '.venv', 'bin', 'python')
    
    # Check if the virtual environment Python exists
    if not os.path.exists(venv_python):
        print(f"[ERROR] Virtual environment Python not found at {venv_python}")
        print("Please create a virtual environment in .venv/ first.")
        sys.exit(1)
    
    # Define pipeline steps
    steps = [
        ([venv_python, 'reddit_collection.py'], "Running Collection Phase"),
        ([venv_python, 'curate.py'], "Running Curation Phase"),
        ([venv_python, 'analyze_topics.py'], "Running Analysis Phase")
    ]
    
    # Execute each step
    for command, description in steps:
        success = run_command(command, description)
        if not success:
            print("[ERROR] Pipeline stopped due to previous error.")
            sys.exit(1)
    
    print("[INFO] All pipeline phases completed successfully.")

if __name__ == "__main__":
    main()