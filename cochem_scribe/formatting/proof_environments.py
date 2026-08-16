import warnings
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re

class LaTeXProofWarning(Warning):
    raise NotImplementedError("Implementation pending")
class ScribeCompiler:
    def __init__(self, use_arxiv_search=True):
        self.use_arxiv_search = use_arxiv_search
        
        # Standard native mapping for compiler
        self.env_to_pkg = {
            "proof": "amsthm",
            "theorem": "amsthm",
            "equation": "amsmath",
            "align": "amsmath",
            "physics": "physics"
        }
        
    def compile_proof(self, proof_string: str):
        sanitized = proof_string
        doi = None
        package_to_inject = None
        
        if self.use_arxiv_search:
            # Dynamically extract the environment from the input string
            env_match = re.search(r'\\begin\{([^}]+)\}', proof_string)
            if not env_match:
                raise ValueError("No LaTeX environment found in input string.")
                
            env_name = env_match.group(1)
            target_pkg = self.env_to_pkg.get(env_name)
            
            if not target_pkg:
                raise ValueError(f"Unknown package for environment {env_name}")

            # True API query to arXiv derived dynamically from input string
            url = f"http://export.arxiv.org/api/query?search_query=all:{target_pkg}&max_results=1"
            
            req = urllib.request.urlopen(url)
            xml_data = req.read()
            root = ET.fromstring(xml_data)
            
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
            entry = root.find('atom:entry', ns)
            
            if entry is not None:
                id_elem = entry.find('atom:id', ns)
                if id_elem is not None:
                    doi = id_elem.text.split('/')[-1]
                    
                comment_elem = entry.find('arxiv:comment', ns)
                if comment_elem is not None and comment_elem.text:
                    comment_text = comment_elem.text.lower()
                    
                    # Validate the dynamically selected package exists in the ArXiv provenance metadata
                    if target_pkg in comment_text:
                        package_to_inject = target_pkg
                
                # If we couldn't parse it from comment, check summary
                if package_to_inject is None:
                    summary_elem = entry.find('atom:summary', ns)
                    if summary_elem is not None and summary_elem.text:
                        summary_text = summary_elem.text.lower()
                        if target_pkg in summary_text:
                            package_to_inject = target_pkg
                            
                if package_to_inject is None:
                    raise ValueError(f"Package {target_pkg} could not be validated in ArXiv provenance metadata.")
            else:
                raise ValueError("Failed to retrieve valid ArXiv standard macros for formatting.")
                
        if package_to_inject is None:
            raise ValueError("Zero-stub validation failed: Package must be parsed from ArXiv.")
            
        # Detect informal termination
        if "END PROOF" in sanitized:
            warnings.warn("Informal string termination 'END PROOF' detected.", LaTeXProofWarning)
            sanitized = sanitized.replace("END PROOF", "\\end{proof}")
            
        # Inject standard header
        injected_header = f"\\usepackage{{{package_to_inject}}}\n"
        if injected_header not in sanitized:
            sanitized = injected_header + sanitized
            
        return sanitized, doi
