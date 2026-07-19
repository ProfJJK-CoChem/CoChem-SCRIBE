#!/usr/bin/env python3
"""
CoChem-SCRIBE: Inference Engine
Consumes the tightly constrained User Guide prompt, safely triggers the LLM
via the Gemini REST API, and writes the output to CoChem_User_Guide.md.
Implements strict exponential backoff to prevent network failure crashes.
"""

import sys
import json
import time
import logging
import urllib.request
from urllib.error import URLError, HTTPError
from pathlib import Path

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
        
        # The execution environment provides the key at runtime
        self.api_key = "" 
        self.model_name = "gemini-2.5-flash-preview-09-2025"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    def load_prompt(self) -> str:
        if not self.input_payload.exists():
            print(f"{Colors.FAIL}❌ FATAL: Prompt payload '{self.input_payload.name}' missing. Run scribe_payload_builder.py first.{Colors.ENDC}")
            sys.exit(1)
        with open(self.input_payload, "r", encoding="utf-8") as f:
            return f.read()

    def _fallback_mock_generation(self) -> str:
        """Provides a graceful offline output if the API is unreachable."""
        return """# CoChem User Guide

*Auto-generated via Offline Fallback*

## 1. Pipeline Overview
CoChem is running in an offline or air-gapped configuration. The active modules have been initialized successfully.

## 2. Hardware Limitations & Expected Performance
Please refer to `cochem_system_config.json` directly to review your system's hardware allocations and GPU tiering constraints.

## 3. Module Execution Guide
To proceed, run the Stage 1.0 Master Ingestion node via your local Jupyter Notebook.
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
        print(f"📡 Transmitting payload to {self.model_name}...")

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
        print(f"{Colors.FAIL}❌ API Error: Failed to generate content after 5 attempts. Falling back to offline mode.{Colors.ENDC}")
        logging.critical("API exhausted. Generating fallback offline document.")
        return self._fallback_mock_generation()

    def generate_document(self):
        prompt = self.load_prompt()
        markdown_content = self.query_api(prompt)

        with open(self.output_md, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"{Colors.OKGREEN}✅ CoChem User Guide successfully generated: {self.output_md.name}{Colors.ENDC}")
        logging.info("SCRIBE inference execution successfully finished.")

def main():
    print(f"\n{Colors.BOLD}--- CoChem-SCRIBE: LLM Inference Engine ---{Colors.ENDC}")
    engine = ScribeInferenceEngine()
    engine.generate_document()

if __name__ == "__main__":
    main()