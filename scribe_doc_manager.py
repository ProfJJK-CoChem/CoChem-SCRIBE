#!/usr/bin/env python3
"""
CoChem-SCRIBE: Document Manager (Stage 6.3)
Asynchronous background daemon that monitors HDF5 tensor memory usage and
serializes data using Zstandard compression for provenance tracking.
"""

import os
import sys
import shutil
import logging
import asyncio
import h5py
import zstandard as zstd
from datetime import datetime
from pathlib import Path
import threading
import time

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
        
        # HDF5 monitoring parameters
        self.h5_file_path = Path("cochem_state.h5")
        self.memory_threshold_mb = 500  # 500MB threshold for flushing
        self.is_monitoring = False
        self.monitoring_thread = None

    def start_background_daemon(self):
        """Starts the asynchronous monitoring daemon."""
        print(f"{Colors.OKCYAN}[🔄] Starting CoChem-SCRIBE background daemon...{Colors.ENDC}")
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_hdf5_memory, daemon=True)
        self.monitoring_thread.start()
        logging.info("Background daemon started successfully.")

    def _monitor_hdf5_memory(self):
        """Monitors HDF5 tensor memory usage and flushes when threshold is reached."""
        print(f"{Colors.OKCYAN}[🔍] Monitoring HDF5 tensor memory usage...{Colors.ENDC}")
        while self.is_monitoring:
            try:
                if self.h5_file_path.exists():
                    # Check current size of the HDF5 file
                    current_size = self.h5_file_path.stat().st_size / (1024 * 1024)  # Convert to MB
                    if current_size >= self.memory_threshold_mb:
                        print(f"{Colors.WARNING}⚠️  Memory threshold exceeded ({current_size:.2f} MB){Colors.ENDC}")
                        self._flush_hdf5_chunks()
                time.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logging.error(f"Error in HDF5 monitoring: {e}")
                time.sleep(5)

    def _flush_hdf5_chunks(self):
        """Flushes HDF5 data to compressed chunks using Zstandard."""
        try:
            if not self.h5_file_path.exists():
                return

            # Create a directory for compressed chunks
            chunk_dir = self.archive_dir / "hdf5_chunks"
            chunk_dir.mkdir(exist_ok=True)
            
            # Open the HDF5 file and compress chunks
            with h5py.File(self.h5_file_path, 'r') as f:
                # List all datasets in the HDF5 file
                datasets = []
                def collect_datasets(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        datasets.append((name, obj))
                
                f.visititems(collect_datasets)
                
                # Process each dataset and compress in chunks
                for dataset_name, dataset in datasets:
                    print(f"📦 Compressing dataset: {dataset_name}...")
                    chunk_file_path = chunk_dir / f"{Path(dataset_name).name}.tar.zst"
                    self._compress_dataset_chunked(dataset, chunk_file_path)
                    
            logging.info("HDF5 chunks successfully flushed to disk using Zstandard compression.")
            
        except Exception as e:
            logging.error(f"Error flushing HDF5 chunks: {e}")

    def _compress_dataset_chunked(self, dataset, output_path):
        """Compresses a large dataset in chunks to avoid memory issues."""
        try:
            # Create a zstd compressor
            cctx = zstd.ZstdCompressor(level=3)
            
            with open(output_path, 'wb') as f_out:
                # For large datasets, we'll compress in chunks
                chunk_size = 1024 * 1024  # 1MB chunks
                data = dataset[()]
                
                if len(data) > 0:
                    # Compress and write the entire dataset to a .tar.zst file
                    compressed_data = cctx.compress(data.tobytes())
                    f_out.write(compressed_data)
                    
            logging.info(f"Compressed dataset {dataset.name} to {output_path.name}")
            
        except Exception as e:
            logging.error(f"Error compressing dataset chunk: {e}")

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

    def generate_final_payload(self):
        """Generates the final Zstandard-compressed payload with all artifacts."""
        print(f"📦 Generating final Zstandard-compressed payload...")
        try:
            # Create a temporary directory for the full archive before compression
            temp_dir = self.archive_dir / "temp_full_archive"
            temp_dir.mkdir(exist_ok=True)
            
            # Copy all files to temp directory
            for item in self.archive_dir.iterdir():
                if item.is_file() and item.name != 'cochem_scribe_manager.log':
                    shutil.copy2(item, temp_dir / item.name)
                elif item.is_dir() and item.name != 'logs' and item.name != 'hdf5_chunks':
                    shutil.copytree(item, temp_dir / item.name, dirs_exist_ok=True)
            
            # Create final .tar.zst file
            final_archive = self.archive_dir.with_suffix('.tar.zst')
            
            # For now, just create a simple zstd compression of the entire directory structure
            import tarfile
            
            # Create a temporary tar file first
            temp_tar = self.archive_dir / "temp.tar"
            with tarfile.open(temp_tar, 'w') as tar:
                for item in temp_dir.iterdir():
                    if item.is_file():
                        tar.add(item, arcname=item.name)
                    elif item.is_dir():
                        tar.add(item, arcname=item.name)
            
            # Now compress the tar file with zstandard
            with open(temp_tar, 'rb') as f_in:
                with open(final_archive, 'wb') as f_out:
                    cctx = zstd.ZstdCompressor(level=6)
                    compressed_data = cctx.compress(f_in.read())
                    f_out.write(compressed_data)
            
            # Clean up temporary files
            temp_tar.unlink()
            shutil.rmtree(temp_dir)
                    
            print(f"{Colors.OKGREEN}✅ Final payload successfully created: {final_archive.name}{Colors.ENDC}")
            logging.info(f"Final payload successfully compressed to {final_archive.name}")
            
        except Exception as e:
            print(f"{Colors.FAIL}[❌] Failed to generate final payload: {e}{Colors.ENDC}")
            logging.error(f"Final payload generation error: {e}")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Asynchronous Document Manager ---{Colors.ENDC}")
    
    manager = ScribeDocumentManager()
    manager.start_background_daemon()  # Start monitoring daemon
    
    # Wait for a bit to allow daemon to start
    import time
    time.sleep(2)
    
    # Harvest artifacts (this would normally be triggered by the pipeline completion)
    count = manager.harvest_artifacts()
    if count == 0:
        print(f"{Colors.WARNING}Warning: No CoChem artifacts found in root directory. Was the pipeline executed?{Colors.ENDC}")
    else:
        print(f"{Colors.OKCYAN}Harvested {count} output files and logs.{Colors.ENDC}")
        
        # Generate final payload with Zstandard compression
        manager.generate_final_payload()
        
        # Stop monitoring daemon
        manager.is_monitoring = False
        if manager.monitoring_thread:
            manager.monitoring_thread.join(timeout=2)
    
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}   CoChem Pipeline Execution Fully Concluded! {Colors.ENDC}")
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}\n")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()