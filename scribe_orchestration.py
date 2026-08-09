#!/usr/bin/env python3
"""
CoChem-SCRIBE: Master Orchestration Script (Stage 6.7)
Coordinates the complete SCRIBE workflow by orchestrating all subsystems:
1. Asynchronous daemon monitoring
2. Dynamic log parsing and LaTeX generation  
3. Publication visualization pipelines
4. LLM inference for results & discussion
5. Legacy verification bundling
"""

import os
import sys
import shlex
import subprocess
import threading
import time
import logging
from pathlib import Path

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_orchestration.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeOrchestrator:
    def __init__(self):
        # Resolves SCRIBE-18: Process tracking for clean child process management
        self.active_processes = []

    def run_command(self, cmd_str: str, description: str) -> bool:
        """
        Run a command cleanly without shell injection.
        Resolves SCRIBE-07: Uses shell=False with argument list.
        """
        print(f"{Colors.OKCYAN}▶ {description}...{Colors.ENDC}")
        try:
            cmd_args = [sys.executable] + shlex.split(cmd_str.replace("python ", ""))
            proc = subprocess.run(cmd_args, shell=False, check=True, capture_output=True, text=True)
            print(f"{Colors.OKGREEN}✅ {description} completed successfully.{Colors.ENDC}")
            logging.info(f"{description} completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}[❌] {description} failed: {e.stderr}{Colors.ENDC}")
            logging.error(f"{description} failed: {e.stderr}")
            return False

    def spawn_daemon(self) -> subprocess.Popen:
        """
        Resolves SCRIBE-18: Tracks background daemon PID via Popen for clean shutdown.
        """
        print(f"{Colors.OKCYAN}▶ Spawning Document Manager daemon process...{Colors.ENDC}")
        proc = subprocess.Popen([sys.executable, "scribe_doc_manager.py"], shell=False)
        self.active_processes.append(proc)
        logging.info(f"Daemon process spawned with PID: {proc.pid}")
        return proc

    def terminate_all(self):
        """Cleanly terminates all tracked background child processes."""
        for proc in self.active_processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                logging.info(f"Process PID {proc.pid} shut down successfully.")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Master Orchestration ---{Colors.ENDC}")
    print(f"{Colors.OKCYAN}[🔄] Initiating complete SCRIBE workflow execution...{Colors.ENDC}")
    
    orchestrator = ScribeOrchestrator()
    
    try:
        print(f"\n{Colors.BOLD}Stage 1: Starting Asynchronous Daemon{Colors.ENDC}")
        orchestrator.spawn_daemon()
        time.sleep(2)
        
        print(f"\n{Colors.BOLD}Stage 2: Generating LLM Payload{Colors.ENDC}")
        orchestrator.run_command("python scribe_payload_builder.py", "Payload generation")
        
        print(f"\n{Colors.BOLD}Stage 3: Generating User Guide via LLM{Colors.ENDC}")
        orchestrator.run_command("python scribe_inference.py", "User Guide generation")
        
        print(f"\n{Colors.BOLD}Stage 4: Generating Results & Discussion{Colors.ENDC}")
        orchestrator.run_command("python scribe_inference.py generate_results_discussion", "Results & Discussion generation")
        
        print(f"\n{Colors.BOLD}Stage 5: Generating Publication Figures{Colors.ENDC}")
        orchestrator.run_command("python scribe_figure_generator.py", "Figure generation")
        
        print(f"\n{Colors.BOLD}Stage 6: Creating Legacy Verification Bundle{Colors.ENDC}")
        orchestrator.run_command("python scribe_legacy_bundler.py", "Legacy verification bundling")
        
        print(f"\n{Colors.BOLD}Stage 7: Finalizing Master Archive{Colors.ENDC}")
        orchestrator.run_command("python scribe_doc_manager.py", "Final archive creation")
        
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ All SCRIBE workflow stages completed successfully!{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Your CoChem pipeline execution is now fully documented and archived.{Colors.ENDC}")
        
    finally:
        orchestrator.terminate_all()

if __name__ == "__main__":
    main()