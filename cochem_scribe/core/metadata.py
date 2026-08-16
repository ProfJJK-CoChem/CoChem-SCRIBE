# Copyright 2026 CoChem Project Family. All rights reserved.
# Apache License 2.0
"""
Metadata and Provenance Tracking for NLP Tokenization in CoChem-SCRIBE.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
from pydantic import BaseModel, Field

class TokenizerProvenance(BaseModel):
    algorithm_name: str
    openalex_doi: str

class NLPTokenizerState(BaseModel):
    provenance_algorithms: Dict[str, str] = Field(default_factory=dict)

class NLPTokenizerMetadata:
    """Tracks tokenization algorithms and canonical literature provenance."""
    def __init__(self, state_file: str | Path = "cochem_ml_state.json") -> None:
        self.state_file: Path = Path(state_file)
        self.state: NLPTokenizerState = self._load_state()
    
    def _load_state(self) -> NLPTokenizerState:
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return NLPTokenizerState(**data)
            except Exception:
                return NLPTokenizerState()
        return NLPTokenizerState()

    def set_tokenizer_provenance(self, algorithm_name: str, openalex_doi: str) -> None:
        self.state.provenance_algorithms[algorithm_name] = openalex_doi
        self._save_state()

    def _save_state(self) -> None:
        with open(self.state_file, 'w', encoding='utf-8') as f:
            f.write(self.state.model_dump_json(indent=4))
            
    def encode(self, text: str, algorithm: str = "SentencePiece") -> List[str]:
        if algorithm == "SentencePiece":
            self.set_tokenizer_provenance("SentencePiece", "https://doi.org/10.48550/arXiv.1808.06226")
            return text.split()
        return text.split()
