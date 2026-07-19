#!/usr/bin/env python3
"""
CoChem-SCRIBE: Document Manager (Stage 6.3)
Aggregates generated Markdown, LaTeX, JSON registries, and runtime logs into a 
finalized, version-controlled Report_Archive directory. Generates a compressed 
payload for easy exfiltration from headless computational nodes.
"""

import os
import sys
import shutil
import logging
import zipfile
from datetime import datetime
from pathlib import Path

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

logging.basicConfig(filename='cochem_scribe_manager.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeDocumentManager:
    def __init__(self):
        # Create a timestamped archive folder to prevent overwriting previous runs
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.archive_dir = Path(f"Report_Archive/Run_{timestamp}")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Target files to harvest from the active workspace
        self.target_artifacts = [
            "CoChem_User_Guide.md",
            "Photochem_Mechanism.tex",
            "Photochem_Mechanism.pdf",
            "cochem_system_config.json",
            "cochem_mint_registry.json",
            "cochem_hpc_registry.json",
            "simulated_ir_spectrum.csv"
        ]
        
        # Wildcard log targeting
        self.log_pattern = "*.log"

    def harvest_artifacts(self) -> int:
        """Moves targeted generated documents and registries into the archive."""
        print(f"🗂️  Harvesting artifacts into {self.archive_dir}...")
        harvested_count = 0
        
        for file_name in self.target_artifacts:
            src = Path(file_name)
            if src.exists():
                dst = self.archive_dir / src.name
                shutil.copy2(src, dst)
                harvested_count += 1
                logging.info(f"Harvested artifact: {src.name}")
            else:
                logging.warning(f"Expected artifact not found (skipped): {src.name}")

        # Harvest logs into a subfolder
        log_dir = self.archive_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        work_dir = Path(".")
        for log_file in work_dir.glob(self.log_pattern):
            if log_file.is_file():
                shutil.copy2(log_file, log_dir / log_file.name)
                harvested_count += 1
                
        return harvested_count

    def generate_payload(self):
        """Zips the directory for headless node exfiltration."""
        zip_name = self.archive_dir.with_suffix('.zip')
        print(f"📦 Compressing finalized archive to {zip_name.name}...")
        
        try:
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(self.archive_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.archive_dir.parent)
                        zipf.write(file_path, arcname)
                        
            print(f"{Colors.OKGREEN}✅ Master Payload Packaged Successfully.{Colors.ENDC}")
            logging.info(f"Archive successfully compressed to {zip_name}")
            
        except Exception as e:
            print(f"{Colors.FAIL}❌ Failed to compress archive: {e}{Colors.ENDC}")
            logging.error(f"Compression error: {e}")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Final Document Assembler ---{Colors.ENDC}")
    
    manager = ScribeDocumentManager()
    
    count = manager.harvest_artifacts()
    if count == 0:
        print(f"{Colors.WARNING}⚠️ No CoChem artifacts found in root directory. Was the pipeline executed?{Colors.ENDC}")
    else:
        print(f"{Colors.OKCYAN}↳ Harvested {count} output files and logs.{Colors.ENDC}")
        manager.generate_payload()
        
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}   CoChem Pipeline Execution Fully Concluded! {Colors.ENDC}")
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}\n")

if __name__ == "__main__":
    main()