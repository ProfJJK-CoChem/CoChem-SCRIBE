# **CoChem-SCRIBE: Automated FAIR Publication & LaTeX Engine**

## **Overview**

**CoChem-SCRIBE** is the final mile of the pipeline. It eliminates the tedious, error-prone process of manually copying energies, rotational constants, and thermal corrections from terminal outputs into research papers.

SCRIBE ingests the finalized landscape.h5 database and the fit\_provenance.json registry. It aggregates the data and uses strict templating algorithms to generate compile-ready .tex documents (utilizing siunitx for physical constants, booktabs for tables, and chemfig for 2D structures).

## **Scientific & Technical Trade-offs**

* **Template Rigidity vs. Flexibility:** LaTeX compilation is notoriously fragile. SCRIBE heavily restricts custom user formatting during the initial generation to mathematically guarantee that the resulting .tex file compiles without fatal math-mode or escaping errors (e.g., automatically sanitizing underscores in molecule names). You trade formatting freedom for guaranteed compilation.  
* **The RESOURCE\_GUARD Bypass:** SCRIBE contains a localized LLM summarization tool to write "Methods" boilerplate text. However, on constrained laptops, downloading a 4GB .gguf weights file is prohibitive. SCRIBE implements a strict RESOURCE\_GUARD; if the system lacks a dedicated GPU, it completely bypasses the LLM inference and defaults to rigid, programmatic string-replacement for the methods section.

## **Installation & Setup**

SCRIBE assumes your operating system has a LaTeX compiler installed (e.g., texlive-full on Linux).

git clone \[https://github.com/CoChem/CoChem-SCRIBE.git\](https://github.com/CoChem/CoChem-SCRIBE.git)  
cd CoChem-SCRIBE

## **How to Run**

SCRIBE should only be run after all calculations (TOPOS, TORQ, etc.) are marked STAGE\_COMPLETE in the registry.

1. **Initialize the Master Orchestrator:**  
   python cochem\_scribe\_master.py  
2. **Execution Flow:**  
   * \[1/5\] Sweeps the landscape.h5 for converged anchors.  
   * \[2/5\] Formats the thermodynamic and spectroscopic tables.  
   * \[3/5\] (Optional) Triggers the local LLM for boilerplate text generation.  
   * \[4/5\] Injects data into the siunitx LaTeX template.  
   * \[5/5\] Dispatches a silent pdflatex subprocess call to verify compilation.

## **Output**

Check the Publication\_Outputs/ directory for Manuscript\_Draft.tex, Supporting\_Information.tex, and the compiled .pdf documents.