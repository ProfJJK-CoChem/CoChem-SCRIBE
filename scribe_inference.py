#!/usr/bin/env python3
"""
CoChem-SCRIBE: Inference Engine (Stage 6.5)
Enhanced LLM engine for Results & Discussion generation with offline fallback transparency.
Integrates Bayesian SpycFit parameters, kinetic barriers, and final physical constants into
a comprehensive manuscript section generation pipeline.
"""

import sys
import json
import time
import logging
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

logging.basicConfig(filename='cochem_scribe_inference.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ScribeInferenceEngine:
    def __init__(self):
        self.input_payload = Path("scribe_prompt_payload.txt")
        self.output_md = Path("CoChem_User_Guide.md")
        self.results_discussion_file = Path("Results_and_Discussion.md")
        self.spotfit_params_file = Path("spyfit_parameters.json")
        self.h5_file_path = Path("cochem_state.h5")
        
        # The execution environment provides the key at runtime
        self.api_key = "" 
        self.model_name = "gemini-2.5-flash-preview-09-2025"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def load_prompt(self) -> str:
        if not self.input_payload.exists():
            print(f"{Colors.FAIL}[❌] FATAL: Prompt payload '{self.input_payload.name}' missing. Run scribe_payload_builder.py first.{Colors.ENDC}")
            sys.exit(1)
        with open(self.input_payload, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_spotify_parameters(self) -> dict:
        """Extracts Bayesian SpycFit parameters and kinetic barriers from HDF5 if available."""
        params = {}
        try:
            if self.h5_file_path.exists():
                with h5py.File(self.h5_file_path, 'r') as f:
                    # Try to extract key parameters from the HDF5 tensor
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
        print(f"{Colors.OKCYAN}[📄] Generating Results & Discussion prompt with Bayesian parameters...{Colors.ENDC}")
        params = self._extract_spotify_parameters()
        
        # Create parameter summary for the LLM
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

If the pipeline was executed in an air-gapped environment where API access is unavailable, please add a prominent watermark at the beginning of the document:
*This section was generated using offline fallback due to network restrictions. AI interpretation phase was bypassed.*

Begin writing the "Results & Discussion" section now.
"""
        return prompt

    def _fallback_mock_generation(self) -> str:
        """Provides a graceful offline output if the API is unreachable."""
        return """# CoChem Results & Discussion

*Auto-generated via Offline Fallback*

## 1. Computational Results Analysis

This section was generated using offline fallback due to network restrictions. AI interpretation phase was bypassed.

## 2. Bayesian Parameter Analysis

The Bayesian SpycFit parameters were extracted from the HDF5 tensor but the LLM analysis was not performed due to lack of API access.

## 3. Kinetic and Structural Insights

Due to the offline environment, no full analysis of kinetic barriers or structural implications could be completed.

## 4. Discussion

The computational methodology and results are detailed in Methodology.tex and manuscript.bib files.
"""

    def query_api(self, prompt: str) -> str:
        """Executes the POST request with robust exponential backoff."""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        data = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        req = urllib.request.Request(self.api_url, data=data, headers=headers, method='POST')

        delays = [1, 2, 4, 8, 16]
        print(f"Sending payload to {self.model_name}...")

        for attempt, delay in enumerate(delays):
            try:
                with urllib.request.urlopen(req) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    if text:
                        return text
                    else:
                        raise ValueError("Empty text part received from API.")
            except (HTTPError, URLError, ValueError) as e:
                # Log failures silently to file to avoid terminal spam
                logging.error(f"API Request Failed (Attempt {attempt+1}/{len(delays)}): {e}")
                time.sleep(delay)

        # Triggers only if all 5 delays (1s + 2s + 4s + 8s + 16s) are exhausted
        print(f"{Colors.FAIL}[❌] API Error: Failed to generate content after 5 attempts. Falling back to offline mode.{Colors.ENDC}")
        logging.critical("API exhausted. Generating fallback offline document.")
        return self._fallback_mock_generation()

    def generate_document(self):
        prompt = self.load_prompt()
        markdown_content = self.query_api(prompt)

        with open(self.output_md, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"{Colors.OKGREEN}✅ CoChem User Guide successfully generated: {self.output_md.name}{Colors.ENDC}")
        logging.info("SCRIBE inference execution successfully finished.")

    def generate_results_discussion(self):
        """Generates the Results and Discussion section specifically."""
        print(f"{Colors.OKCYAN}[📄] Generating Results & Discussion section...{Colors.ENDC}")
        prompt = self._generate_results_discussion_prompt()
        markdown_content = self.query_api(prompt)

        with open(self.results_discussion_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"{Colors.OKGREEN}✅ Results & Discussion section generated: {self.results_discussion_file.name}{Colors.ENDC}")
        logging.info("SCRIBE results and discussion generation successfully finished.")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: LLM Inference Engine ---{Colors.ENDC}")
    engine = ScribeInferenceEngine()
    engine.generate_document()

if __name__ == "__main__":
    main()