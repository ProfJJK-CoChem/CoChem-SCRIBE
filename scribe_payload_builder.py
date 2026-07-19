#!/usr/bin/env python3
"""
CoChem-SCRIBE: Payload Builder
Dynamically parses the CoChem system registries to build a highly constrained,
context-aware prompt for automated User Guide generation. Prevents LLM hallucinations
by hardcoding the exact active modules and hardware limitations into the prompt string.
"""

import json
import logging
from pathlib import Path

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

logging.basicConfig(filename='cochem_scribe_payload.log', level=logging.INFO)

class ScribePayloadBuilder:
    def __init__(self):
        self.config_path = Path("cochem_system_config.json")
        self.manifest_path = Path("cochem_deployment_manifest.json")
        
    def _load_json_safe(self, filepath: Path) -> dict:
        if not filepath.exists():
            logging.warning(f"{filepath.name} missing. Returning empty state.")
            return {}
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.error(f"Corrupted JSON detected in {filepath.name}.")
            return {}

    def construct_user_guide_prompt(self) -> str:
        """Compiles the authoritative LLM Prompt for the User Guide."""
        system_config = self._load_json_safe(self.config_path)
        manifest = self._load_json_safe(self.manifest_path)
        
        # Extract Hardware Limitations (Fallback safely if missing)
        phase2 = system_config.get("phase_2_data", {})
        ram_gb = phase2.get("ram_gb", "Unknown")
        cpu_cores = phase2.get("cpu_cores", "Unknown")
        gpu_profile = phase2.get("gpu_profile", "None Detected")
        
        # Extract Routing Limitations
        routing = system_config.get("adaptive_routing", {})
        classification = routing.get("classification", "Unclassified")
        mace_batch = routing.get("mace_batch_size", "Dynamic")
        
        # Extract Active Modules
        active_modules = manifest.get("active_modules", ["CoChem-CORE (Default)"])
        module_list_str = "\n".join([f"- {mod}" for mod in active_modules])
        
        # Construct the deeply constrained prompt
        prompt = f"""You are the principal technical documentation architect for the CoChem pipeline.
Your task is to generate the official `CoChem_User_Guide.md` for this specific deployment.

CRITICAL INSTRUCTIONS:
1. DO NOT hallucinate features. Only document the modules explicitly listed as active below.
2. Format the output in strict, professional Markdown.
3. Include a "Hardware & Limitations" section using the exact telemetry provided below.

=========================================
ACTIVE DEPLOYMENT TELEMETRY
=========================================
SYSTEM HARDWARE:
- Classification Tier: {classification}
- CPU Cores Available: {cpu_cores}
- Physical RAM (GB): {ram_gb}
- GPU Profile: {gpu_profile}

ROUTING CONSTRAINTS:
- Max MACE-OFF23 Batch Size: {mace_batch}

PROVISIONED MODULES:
{module_list_str}
=========================================

REQUIRED DOCUMENT STRUCTURE:
# CoChem User Guide
## 1. Pipeline Overview
(Briefly explain the capabilities of the installed modules.)
## 2. Hardware Limitations & Expected Performance
(Detail the constraints based on the provided System Hardware and Routing Constraints.)
## 3. Module Execution Guide
(Provide a 1-paragraph summary of how to trigger the active modules via Jupyter.)

Begin the markdown generation now.
"""
        return prompt

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: User Guide Payload Builder ---{Colors.ENDC}")
    builder = ScribePayloadBuilder()
    
    print(f"{Colors.OKCYAN}▶ Harvesting system registries for LLM context...{Colors.ENDC}")
    final_prompt = builder.construct_user_guide_prompt()
    
    # Save prompt to disk for the inference engine to pick up
    out_path = Path("scribe_prompt_payload.txt")
    with open(out_path, "w") as f:
        f.write(final_prompt)
        
    print(f"{Colors.OKGREEN}✅ Master Prompt successfully compiled to {out_path.name}{Colors.ENDC}")
    logging.info(f"Generated user guide prompt constraint payload (Length: {len(final_prompt)} chars).")

if __name__ == "__main__":
    main()