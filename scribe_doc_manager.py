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
import tarfile
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

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_manager.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeDocumentManager:
    def __init__(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.archive_dir = Path(f"Report_Archive/Run_{timestamp}")
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        self.target_artifacts = [
            "CoChem_User_Guide.md",
            "Photochem_Mechanism.tex",
            "Photochem_Mechanism.pdf",
            "cochem_system_config.json",
            "cochem_mint_registry.json",
            "cochem_hpc_registry.json",
            "simulated_ir_spectrum.csv",
            "manuscript_tables.tex"
        ]
        
        self.h5_file_path = Path("cochem_state.h5")
        self.memory_threshold_mb = 500
        self.is_monitoring = False
        self.monitoring_thread = None

    def start_background_daemon(self):
        """Starts the asynchronous monitoring daemon."""
        print(f"{Colors.OKCYAN}[INFO] Starting CoChem-SCRIBE background daemon...{Colors.ENDC}")
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_hdf5_memory, daemon=True)
        self.monitoring_thread.start()
        logging.info("Background daemon started successfully.")

    def _monitor_hdf5_memory(self):
        """
        Monitors HDF5 tensor memory usage.
        Resolves SCRIBE-13: Reduced polling thread overhead with event loop sleep checks.
        """
        print(f"{Colors.OKCYAN}[INFO] Monitoring HDF5 tensor memory usage (event-driven)...{Colors.ENDC}")
        last_mtime = 0
        while self.is_monitoring:
            try:
                if self.h5_file_path.exists():
                    st = self.h5_file_path.stat()
                    if st.st_mtime != last_mtime:
                        last_mtime = st.st_mtime
                        current_size = st.st_size / (1024 * 1024)
                        if current_size >= self.memory_threshold_mb:
                            print(f"{Colors.WARNING}[WARN] Memory threshold exceeded ({current_size:.2f} MB){Colors.ENDC}")
                            self._flush_hdf5_chunks()
                time.sleep(2)
            except Exception as e:
                logging.error(f"Error in HDF5 monitoring: {e}")
                time.sleep(2)

    def _flush_hdf5_chunks(self):
        """Flushes HDF5 data to compressed chunks using Zstandard."""
        try:
            if not self.h5_file_path.exists():
                return

            chunk_dir = self.archive_dir / "hdf5_chunks"
            chunk_dir.mkdir(exist_ok=True)
            
            with h5py.File(self.h5_file_path, 'r') as f:
                datasets = []
                def collect_datasets(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        datasets.append((name, obj))
                
                f.visititems(collect_datasets)
                
                for dataset_name, dataset in datasets:
                    print(f"[INFO] Compressing dataset: {dataset_name}...")
                    chunk_file_path = chunk_dir / f"{Path(dataset_name).name}.tar.zst"
                    self._compress_dataset_chunked(dataset, chunk_file_path)
                    
            logging.info("HDF5 chunks successfully flushed to disk using Zstandard compression.")
            
        except Exception as e:
            logging.error(f"Error flushing HDF5 chunks: {e}")

    def _compress_dataset_chunked(self, dataset, output_path):
        """
        Compresses a large dataset in chunks to avoid RAM saturation.
        Resolves SCRIBE-04: Iterates over HDF5 dataset in slices dataset[i:i+chunk_size]
        and streams slices into Zstandard compressor.
        """
        try:
            cctx = zstd.ZstdCompressor(level=3)
            with open(output_path, 'wb') as f_out:
                with cctx.stream_writer(f_out) as compressor:
                    total_elements = dataset.shape[0] if len(dataset.shape) > 0 else 1
                    slice_size = 10000
                    
                    if len(dataset.shape) == 0:
                        scalar_data = dataset[()]
                        compressor.write(bytes(str(scalar_data), 'utf-8'))
                    else:
                        for start_idx in range(0, total_elements, slice_size):
                            end_idx = min(start_idx + slice_size, total_elements)
                            chunk_slice = dataset[start_idx:end_idx]
                            compressor.write(chunk_slice.tobytes())

            logging.info(f"Chunk-stream compressed dataset {dataset.name} to {output_path.name}")
            
        except Exception as e:
            logging.error(f"Error compressing dataset chunk: {e}")

    def harvest_artifacts(self) -> int:
        """
        Moves targeted generated documents and registries into the archive.
        Resolves SCRIBE-17: Recursive log file harvesting Path(".").rglob("*.log").
        """
        print(f"[INFO] Harvesting artifacts into {self.archive_dir}...")
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

        log_dir = self.archive_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # SCRIBE-17 fix: Recursive glob for logs across nested directories
        work_dir = Path(".")
        for log_file in work_dir.rglob("*.log"):
            if log_file.is_file() and not str(log_file).startswith("Report_Archive"):
                shutil.copy2(log_file, log_dir / log_file.name)
                harvested_count += 1
                
        return harvested_count

    def generate_final_payload(self):
        """
        Generates the final Zstandard-compressed payload with all artifacts.
        Resolves SCRIBE-05: Streams archive creation directly without full in-memory tar buffer.
        """
        print(f"[INFO] Generating final Zstandard-compressed payload...")
        try:
            final_archive = self.archive_dir.with_suffix('.tar.zst')
            
            cctx = zstd.ZstdCompressor(level=6)
            with open(final_archive, 'wb') as f_out:
                with cctx.stream_writer(f_out) as compressor:
                    temp_tar = self.archive_dir / "stream_temp.tar"
                    with tarfile.open(temp_tar, 'w') as tar:
                        for item in self.archive_dir.iterdir():
                            if item.is_file() and item.name != 'cochem_scribe_manager.log':
                                tar.add(item, arcname=item.name)
                            elif item.is_dir():
                                tar.add(item, arcname=item.name)
                                
                    with open(temp_tar, 'rb') as f_in:
                        shutil.copyfileobj(f_in, compressor)
                        
                    if temp_tar.exists():
                        temp_tar.unlink()
                    
            print(f"{Colors.OKGREEN}[OK] Final payload successfully created: {final_archive.name}{Colors.ENDC}")
            logging.info(f"Final payload successfully compressed to {final_archive.name}")
            
        except Exception as e:
            print(f"{Colors.FAIL}[FAIL] Failed to generate final payload: {e}{Colors.ENDC}")
            logging.error(f"Final payload generation error: {e}")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: Asynchronous Document Manager ---{Colors.ENDC}")
    
    manager = ScribeDocumentManager()
    manager.start_background_daemon()
    
    time.sleep(1)
    
    count = manager.harvest_artifacts()
    if count == 0:
        print(f"{Colors.WARNING}Warning: No CoChem artifacts found in root directory.{Colors.ENDC}")
    else:
        print(f"{Colors.OKCYAN}Harvested {count} output files and logs.{Colors.ENDC}")
        manager.generate_final_payload()
        
    manager.is_monitoring = False
    if manager.monitoring_thread:
        manager.monitoring_thread.join(timeout=2)
    
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}   CoChem Pipeline Execution Fully Concluded! {Colors.ENDC}")
    print(f"{Colors.BOLD}======================================================{Colors.ENDC}\n")

# Resolves SCRIBE-06: Clean single main entry point
if __name__ == "__main__":
    main()