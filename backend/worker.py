#!/usr/bin/env python
"""Arq Worker Entrypoint — Background job processor for SoloPrac AI.

Runs the email queue and other async tasks via Redis + arq.

Usage:
    # Development
    arq app.services.email_queue.WorkerSettings

    # Production (with watchdog)
    arq app.services.email_queue.WorkerSettings --watch
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.email_queue import WorkerSettings

if __name__ == "__main__":
    from arq.worker import run_worker

    run_worker(WorkerSettings)
