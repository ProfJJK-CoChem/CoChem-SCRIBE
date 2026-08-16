import hashlib
from typing import Any, Dict, List, Optional
#!/usr/bin/env python3
"""
CoChem-SCRIBE: Inference Engine (Stage 6.5)
Enhanced LLM engine for Results & Discussion generation with offline fallback transparency.
Integrates Bayesian SpycFit parameters, kinetic barriers, and final physical constants into
a comprehensive manuscript section generation pipeline.
"""

import os
import sys
import json
import time
import logging
logger = logging.getLogger(__name__)
import urllib.request
from urllib.error import URLError, HTTPError
from pathlib import Path
import h5py

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

artifact_dir = Path(os.environ.get("COCHEM_ARTIFACT_DIR", "."))
artifact_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(artifact_dir / 'cochem_scribe_inference.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeInferenceEngine:
    def __init__(self) -> None:
        self.input_payload = Path("scribe_prompt_payload.txt")
        self.output_md = Path("CoChem_User_Guide.md")
        self.results_discussion_file = Path("Results_and_Discussion.md")
        self.spotfit_params_file = Path("spyfit_parameters.json")
        self.h5_file_path = Path("cochem_state.h5")
        
        self.api_key = os.environ.get("GEMINI_API_KEY", "") 
        self.model_name = "gemini-2.5-flash-preview-09-2025"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def load_prompt(self) -> str:
        if not self.input_payload.exists():
            logger.info(f"{Colors.WARNING}[WARN] Prompt payload '{self.input_payload.name}' missing. Generating default payload...{Colors.ENDC}")
            return "Generate CoChem User Guide documentation."
        with open(self.input_payload, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_spotify_parameters(self) -> dict:
        """Extracts Bayesian SpycFit parameters and kinetic barriers from HDF5 if available."""
        params = {}
        try:
            h5_candidates = [self.h5_file_path, Path("landscape.h5")]
            for h5_p in h5_candidates:
                if h5_p.exists():
                    with h5py.File(h5_p, 'r') as f:
                        if 'spyfit_parameters' in f.attrs:
                            params['spyfit_params'] = f.attrs['spyfit_parameters']
                        if 'kinetic_barriers' in f.attrs:
                            params['kinetic_barriers'] = f.attrs['kinetic_barriers']
                        if 'rotational_constants' in f.attrs:
                            params['rotational_constants'] = f.attrs['rotational_constants']
                        if 'global_minimum' in f.attrs:
                            params['global_minimum'] = f.attrs['global_minimum']
        except Exception as e:
            logging.error(f"Error extracting SpycFit parameters: {e}")
            
        return params

    def _generate_results_discussion_prompt(self) -> str:
        """Generates a prompt specifically for Results and Discussion section."""
        logger.info(f"{Colors.OKCYAN}[INFO] Generating Results & Discussion prompt with Bayesian parameters...{Colors.ENDC}")
        params = self._extract_spotify_parameters()
        
        param_summary = "No specific parameters extracted from HDF5.\n"
        if params:
            param_summary = "Extracted parameters:\n"
            for key, value in params.items():
                param_summary += f"- {key}: {value}\n"
                
        prompt = f"""You are an expert computational chemist and manuscript writer. Your task is to write the "Results & Discussion" section for a CoChem pipeline execution report, based on the Bayesian SpycFit parameters and other computational results provided below.

CRITICAL INSTRUCTIONS:
    1. Write in formal scientific tone appropriate for a journal article
2. Reference specific computational methods from Methodology.tex
3. Use the actual parameter values from the HDF5 tensor when available
4. If running in offline mode, explicitly include a watermark stating that AI interpretation was bypassed

PARAMETER SUMMARY FROM PIPELINE EXECUTION:
    {param_summary}

SPECIFIC REQUIREMENTS FOR THIS SECTION:
    1. Analyze the computational results in the context of the methodology used
2. Discuss the significance of the identified global minimum
3. Explain any kinetic barriers found in the reaction pathway
4. Interpret the rotational constants and their implications
5. Provide discussion on the quality of the Bayesian fitting process

Begin writing the "Results & Discussion" section now.
"""
        return prompt

    def _fallback_offline_jinja_rendering(self, prompt_context: str = "") -> str:
        """
        Resolves SCRIBE-09: Offline fallback engine rendering static Jinja2 manuscript templates
        when external LLM endpoints are unreachable or unconfigured.
        """
        logger.info(f"{Colors.WARNING}[WARN] Utilizing offline Jinja2 fallback template renderer for document generation.{Colors.ENDC}")
        logging.info("Offline Jinja2 fallback engine activated.")

        params = self._extract_spotify_parameters()
        
        template_str = """# CoChem Pipeline Results & Discussion

*Notice: Generated via Offline Fallback Engine (LLM Endpoint Unreachable/Air-Gapped).*

## 1. Computational Methodology Summary
The quantum chemical calculations were conducted utilizing DFT functionals and mass-weighted Hessians. 
All vibrational and rotational spectra were processed via the Colbert-Miller Sinc-DVR and Watson S-reduced Hamiltonian formulations.

## 2. Spectroscopic Constants & Fitting
{% if params.rotational_constants %}
- **Rotational Constants**: {{ params.rotational_constants }}
{% else %}
- **Rotational Constants**: N/A
{% endif %}

{% if params.kinetic_barriers %}
- **Reaction Kinetic Barrier**: {{ params.kinetic_barriers }}
{% else %}
- **Reaction Kinetic Barrier**: N/A
{% endif %}

## 3. Global Minimum Analysis
The structural global minimum was validated through full Hessian matrix diagonalization and 3D Principal Axis alignment.

## 4. References & Provenance
Detailed methodology equations and BibTeX citations have been compiled into `Methodology.tex` and `manuscript.bib`.
"""
        try:
            from jinja2 import Template
            rendered = Template(template_str).render(params=params)
            return rendered
        except Exception as e:
            logging.error(f"Fallback Jinja2 render error: {e}")
            return template_str

    def query_api(self, prompt: str) -> str:
        """Executes the POST request with robust exponential backoff and offline Jinja2 fallback."""
        if not self.api_key:
            logger.info(f"{Colors.WARNING}[WARN] GEMINI_API_KEY not configured. Triggering offline Jinja2 fallback.{Colors.ENDC}")
            return self._fallback_offline_jinja_rendering(prompt)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        data = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        req = urllib.request.Request(self.api_url, data=data, headers=headers, method='POST')

        delays = [1, 2, 4]
        logger.info(f"Sending payload to {self.model_name}...")

        for attempt, delay in enumerate(delays):
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    if text:
                        return text
            except Exception as e:
                logging.error(f"API Request Failed (Attempt {attempt+1}/{len(delays)}): {e}")
                time.sleep(delay)

        logger.info(f"{Colors.FAIL}[FAIL] API Error: Failed to generate content. Triggering Jinja2 offline engine.{Colors.ENDC}")
        return self._fallback_offline_jinja_rendering(prompt)

    def generate_document(self) -> Any:
        prompt = self.load_prompt()
        markdown_content = self.query_api(prompt)

        with open(self.output_md, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"{Colors.OKGREEN}[OK] CoChem User Guide successfully generated: {self.output_md.name}{Colors.ENDC}")
        logging.info("SCRIBE inference execution successfully finished.")

    def generate_results_discussion(self) -> Any:
        """Generates the Results and Discussion section specifically."""
        logger.info(f"{Colors.OKCYAN}[INFO] Generating Results & Discussion section...{Colors.ENDC}")
        prompt = self._generate_results_discussion_prompt()
        markdown_content = self.query_api(prompt)

        with open(self.results_discussion_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"{Colors.OKGREEN}[OK] Results & Discussion section generated: {self.results_discussion_file.name}{Colors.ENDC}")
        logging.info("SCRIBE results and discussion generation successfully finished.")

def main() -> Any:
    logger.info(f"\n{Colors.BOLD}--- CoChem-SCRIBE: LLM Inference Engine ---{Colors.ENDC}")
    engine = ScribeInferenceEngine()
    if len(sys.argv) > 1 and sys.argv[1] == "generate_results_discussion":
        engine.generate_results_discussion()
    else:
        engine.generate_document()

if __name__ == "__main__":
    main()
def calculate_artifact_sha256(filepath: str | Path) -> str:
    """Calculates SHA-256 hash of a computational artifact."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"Artifact file not found: {filepath}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()