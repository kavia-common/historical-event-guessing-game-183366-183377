#!/bin/bash
cd /home/kavia/workspace/code-generation/historical-event-guessing-game-183366-183377/backend
source venv/bin/activate
flake8 .
LINT_EXIT_CODE=$?
if [ $LINT_EXIT_CODE -ne 0 ]; then
  exit 1
fi

