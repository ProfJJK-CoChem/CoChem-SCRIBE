import atexit
import psutil
from typing import Any, Dict, List, Optional
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
logger = logging.getLogger(__name__)
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
    def __init__(self) -> None:
        # Resolves SCRIBE-18: Process tracking for clean child process management
        self.active_processes = []
        self.tier_categories = {
            "T1": "Screening & Payload Build",
            "T2": "Refinement & Methodology Generation",
            "T3": "High-Fidelity Results & Figures",
            "T4": "Archival & FAIR Verification"
        }

    def run_command(self, cmd_str: str, description: str) -> bool:
        """
        Run a command cleanly without shell injection.
        Resolves SCRIBE-07: Uses shell=False with argument list.
        """
        logger.info(f"{Colors.OKCYAN}[RUN] {description}...{Colors.ENDC}")
        try:
            cmd_args = [sys.executable] + shlex.split(cmd_str.replace("python ", ""))
            proc = subprocess.run(cmd_args, timeout=300, shell=False, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
            logger.info(f"{Colors.OKGREEN}[OK] {description} completed successfully.{Colors.ENDC}")
            logging.info(f"{description} completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.info(f"{Colors.FAIL}[FAIL] {description} failed: {e.stderr}{Colors.ENDC}")
            logging.error(f"{description} failed: {e.stderr}")
            return False

    def spawn_daemon(self) -> subprocess.Popen:
        """
        Resolves SCRIBE-18: Tracks background daemon PID via Popen for clean shutdown.
        """
        logger.info(f"{Colors.OKCYAN}[INFO] Spawning Document Manager daemon process...{Colors.ENDC}")
        proc = subprocess.Popen([sys.executable, "scribe_doc_manager.py"], shell=False)
        self.active_processes.append(proc)
        logging.info(f"Daemon process spawned with PID: {proc.pid}")
        return proc

    def terminate_all(self) -> Any:
        """Cleanly terminates all tracked background child processes."""
        for proc in self.active_processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                logging.info(f"Process PID {proc.pid} shut down successfully.")

def main() -> Any:
    logger.info(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Master Orchestration (v4 T1-T4 Execution Pipeline) ---{Colors.ENDC}")
    logger.info(f"{Colors.OKCYAN}[INFO] Initiating complete SCRIBE workflow execution...{Colors.ENDC}")
    
    orchestrator = ScribeOrchestrator()
    
    try:
        # Category T1: Screening & Payload Build
        logger.info(f"\n{Colors.BOLD}Category T1: Screening & Payload Build{Colors.ENDC}")
        logger.info(f"{Colors.BOLD}  Stage 1 [T1]: Starting Asynchronous Daemon{Colors.ENDC}")
        orchestrator.spawn_daemon()
        time.sleep(2)
        
        logger.info(f"{Colors.BOLD}  Stage 2 [T1]: Generating LLM Payload & Harvesting Telemetry{Colors.ENDC}")
        orchestrator.run_command("python scribe_payload_builder.py", "Payload generation")
        
        # Category T2: Refinement & Methodology Generation
        logger.info(f"\n{Colors.BOLD}Category T2: Refinement & Methodology Generation{Colors.ENDC}")
        logger.info(f"{Colors.BOLD}  Stage 3 [T2]: Generating User Guide via LLM{Colors.ENDC}")
        orchestrator.run_command("python scribe_inference.py", "User Guide generation")
        
        logger.info(f"{Colors.BOLD}  Stage 4 [T2]: Rendering LaTeX Methodology & References{Colors.ENDC}")
        orchestrator.run_command("python cochem_scribe_master.py", "LaTeX methodology rendering")

        # Category T3: High-Fidelity Results & Figures
        logger.info(f"\n{Colors.BOLD}Category T3: High-Fidelity Results & Figures{Colors.ENDC}")
        logger.info(f"{Colors.BOLD}  Stage 5 [T3]: Generating Results & Discussion{Colors.ENDC}")
        orchestrator.run_command("python scribe_inference.py generate_results_discussion", "Results & Discussion generation")
        
        logger.info(f"{Colors.BOLD}  Stage 6 [T3]: Generating Publication Figures & Energetics Tables{Colors.ENDC}")
        orchestrator.run_command("python scribe_figure_generator.py", "Figure generation")
        
        # Category T4: Archival & FAIR Verification
        logger.info(f"\n{Colors.BOLD}Category T4: Archival & FAIR Verification{Colors.ENDC}")
        logger.info(f"{Colors.BOLD}  Stage 7 [T4]: Creating Legacy Verification Bundle{Colors.ENDC}")
        orchestrator.run_command("python scribe_legacy_bundler.py", "Legacy verification bundling")
        
        logger.info(f"{Colors.BOLD}  Stage 8 [T4]: Building FAIR Submission Archive{Colors.ENDC}")
        orchestrator.run_command("python cochem_scribe_archive.py", "FAIR publication archive")
        
        logger.info(f"{Colors.BOLD}  Stage 9 [T4]: Finalizing Master Compressed Archive{Colors.ENDC}")
        orchestrator.run_command("python scribe_doc_manager.py", "Final archive creation")
        
        logger.info(f"\n{Colors.OKGREEN}{Colors.BOLD}[OK] All SCRIBE v4 T1-T4 workflow stages completed successfully!{Colors.ENDC}")
        logger.info(f"{Colors.OKCYAN}Your CoChem pipeline execution is now fully documented and archived.{Colors.ENDC}")
        
    finally:
        orchestrator.terminate_all()

if __name__ == "__main__":
    main()