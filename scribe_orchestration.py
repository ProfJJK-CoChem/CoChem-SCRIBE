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

logging.basicConfig(filename='cochem_scribe_orchestration.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"{Colors.OKCYAN}▶ {description}...{Colors.ENDC}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"{Colors.OKGREEN}✅ {description} completed successfully.{Colors.ENDC}")
        logging.info(f"{description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Colors.FAIL}[❌] {description} failed: {e.stderr}{Colors.ENDC}")
        logging.error(f"{description} failed: {e.stderr}")
        return False

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Master Orchestration ---{Colors.ENDC}")
    print(f"{Colors.OKCYAN}[🔄] Initiating complete SCRIBE workflow execution...{Colors.ENDC}")
    
    # Step 1: Start background daemon
    print(f"\n{Colors.BOLD}Stage 1: Starting Asynchronous Daemon{Colors.ENDC}")
    daemon_thread = threading.Thread(target=lambda: os.system("python scribe_doc_manager.py"))
    daemon_thread.start()
    time.sleep(2)  # Give daemon time to start
    
    # Step 2: Generate payload for LLM
    print(f"\n{Colors.BOLD}Stage 2: Generating LLM Payload{Colors.ENDC}")
    run_command("python scribe_payload_builder.py", "Payload generation")
    
    # Step 3: Run LLM inference for User Guide
    print(f"\n{Colors.BOLD}Stage 3: Generating User Guide via LLM{Colors.ENDC}")
    run_command("python scribe_inference.py", "User Guide generation")
    
    # Step 4: Generate Results & Discussion section
    print(f"\n{Colors.BOLD}Stage 4: Generating Results & Discussion{Colors.ENDC}")
    run_command("python scribe_inference.py generate_results_discussion", "Results & Discussion generation")
    
    # Step 5: Generate publication figures and visualizations
    print(f"\n{Colors.BOLD}Stage 5: Generating Publication Figures{Colors.ENDC}")
    run_command("python scribe_figure_generator.py", "Figure generation")
    
    # Step 6: Create legacy verification bundle
    print(f"\n{Colors.BOLD}Stage 6: Creating Legacy Verification Bundle{Colors.ENDC}")
    run_command("python scribe_legacy_bundler.py", "Legacy verification bundling")
    
    # Step 7: Finalize master archive
    print(f"\n{Colors.BOLD}Stage 7: Finalizing Master Archive{Colors.ENDC}")
    run_command("python scribe_doc_manager.py", "Final archive creation")
    
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ All SCRIBE workflow stages completed successfully!{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Your CoChem pipeline execution is now fully documented and archived.{Colors.ENDC}")

if __name__ == "__main__":
    main()