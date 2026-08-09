#!/usr/bin/env python3
"""
CoChem-SCRIBE: Legacy Verification Bundler (Stage 6.6)
Isolates Pickett .lin, .cat, and .fit files from SpycFit for legacy spectroscopist validation.
Creates a Legacy_Verification.zip bundle that allows classical validation using SPFIT/SPCAT.
"""

import os
import zipfile
import logging
from pathlib import Path

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

logging.basicConfig(filename='cochem_scribe_legacy.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class LegacyVerificationBundler:
    def __init__(self):
        self.legacy_files = []
        self.target_extensions = ['.lin', '.cat', '.fit']
        self.output_zip = Path("Legacy_Verification.zip")
        
    def find_legacy_files(self):
        """Finds all Pickett .lin, .cat, and .fit files in the working directory."""
        print(f"{Colors.OKCYAN}[🔍] Searching for legacy spectroscopy files...{Colors.ENDC}")
        
        work_dir = Path(".")
        found_files = []
        
        for ext in self.target_extensions:
            for file_path in work_dir.glob(f"*{ext}"):
                if file_path.is_file():
                    found_files.append(file_path)
                    self.legacy_files.append(file_path)
                    
        print(f"{Colors.OKGREEN}✅ Found {len(found_files)} legacy files.{Colors.ENDC}")
        logging.info(f"Found {len(found_files)} legacy files: {[f.name for f in found_files]}")
        
    def create_legacy_bundle(self):
        """Creates the Legacy_Verification.zip bundle with Pickett files."""
        print(f"{Colors.OKCYAN}📦 Creating Legacy Verification bundle...{Colors.ENDC}")
        
        if not self.legacy_files:
            print(f"{Colors.WARNING}⚠️ No legacy files found to include in bundle.{Colors.ENDC}")
            return
            
        try:
            with zipfile.ZipFile(self.output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in self.legacy_files:
                    # Add file to zip with just the filename (no full path)
                    zipf.write(file_path, arcname=file_path.name)
                    
            print(f"{Colors.OKGREEN}✅ Legacy Verification bundle created: {self.output_zip.name}{Colors.ENDC}")
            logging.info(f"Legacy verification bundle created successfully")
            
        except Exception as e:
            print(f"{Colors.FAIL}[❌] Failed to create legacy bundle: {e}{Colors.ENDC}")
            logging.error(f"Failed to create legacy bundle: {e}")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Legacy Verification Bundler ---{Colors.ENDC}")
    
    bundler = LegacyVerificationBundler()
    bundler.find_legacy_files()
    bundler.create_legacy_bundle()

if __name__ == "__main__":
    main()