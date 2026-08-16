# Copyright 2026 CoChem Project Family. All rights reserved.
# Apache License 2.0
"""
Gatekeepers and Swarm Messaging Protocols for CoChem-SCRIBE.
Enforces memory and token guardrails to prevent OOM panics and API exhaustion.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class CompilationGatekeeperResponse(BaseModel):
    status: Literal["Allowed", "Dry-Run"]
    estimated_memory_gb: Optional[float] = None
    reason: Optional[str] = None
    proposal: Optional[str] = None


class GenerationGatekeeperResponse(BaseModel):
    status: Literal["Allowed", "Dry-Run"]
    estimated_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    reason: Optional[str] = None
    proposal: Optional[str] = None


class PDFLatexMemoryGatekeeper:
    """Safeguards LaTeX compilation against memory exhaustion."""
    def __init__(self, max_buffer_gb: float = 2.0) -> None:
        self.max_buffer_gb: float = max_buffer_gb

    def request_compilation(self, num_pages: int, active_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        if active_extensions is None:
            active_extensions = []
        
        # 100,000 pages with figures and tables
        # Assume ~50 MB per page for PDF latex compilation memory footprint
        estimated_memory_gb = (num_pages * 50) / 1024.0

        if "/teamwork-preview" in active_extensions:
            if estimated_memory_gb > self.max_buffer_gb:
                resp = CompilationGatekeeperResponse(
                    status="Dry-Run",
                    estimated_memory_gb=estimated_memory_gb,
                    reason=f"pdflatex memory buffer limit exceeded. Compiling a {num_pages}-page PDF requires an estimated {estimated_memory_gb:.2f} GB of RAM, which instantly overflows the TeX capacity and will crash the server.",
                    proposal="It is proposed to generate a static HTML website (e.g., using Sphinx or MkDocs) or chunking the PDF into 100 separate 1,000-page volumes."
                )
                return resp.model_dump(exclude_none=True)
        
        resp = CompilationGatekeeperResponse(
            status="Allowed",
            estimated_memory_gb=estimated_memory_gb
        )
        return resp.model_dump(exclude_none=True)


def pdf_compilation_dry_run(num_pages: int, active_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
    gatekeeper = PDFLatexMemoryGatekeeper()
    return gatekeeper.request_compilation(num_pages, active_extensions)


class LLMTokenGatekeeper:
    """Safeguards multi-turn LLM generation budgets."""
    def __init__(self, max_tokens: int = 100000, cost_per_1k_tokens: float = 0.02) -> None:
        self.max_tokens: int = max_tokens
        self.cost_per_1k_tokens: float = cost_per_1k_tokens

    def request_generation(self, num_pages: int, active_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        if active_extensions is None:
            active_extensions = []
        
        # Assume 500 tokens per page
        estimated_tokens = num_pages * 500
        estimated_cost = (estimated_tokens / 1000.0) * self.cost_per_1k_tokens

        if "/teamwork-preview" in active_extensions:
            if estimated_tokens > self.max_tokens:
                resp = GenerationGatekeeperResponse(
                    status="Dry-Run",
                    estimated_tokens=estimated_tokens,
                    estimated_cost=estimated_cost,
                    reason=f"Context window and output token count (approx {estimated_tokens} tokens) will exceed standard rate limits and API budgets.",
                    proposal=f"Rejecting monolithic request. Propose utilizing a modular map-reduce generation strategy (generating sections independently and stitching them together). Estimated cost: ${estimated_cost:.2f} via GPT-4."
                )
                return resp.model_dump(exclude_none=True)
        
        resp = GenerationGatekeeperResponse(
            status="Allowed",
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost
        )
        return resp.model_dump(exclude_none=True)


def llm_generation_dry_run(num_pages: int, active_extensions: Optional[List[str]] = None) -> Dict[str, Any]:
    gatekeeper = LLMTokenGatekeeper()
    return gatekeeper.request_generation(num_pages, active_extensions)
