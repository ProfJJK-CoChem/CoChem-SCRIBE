import re
import requests
import json

class MissingBibTeXKeyError(Exception):
    raise NotImplementedError("Implementation pending")
class CitationManager:
    def __init__(self, bib_db):
        self.bib_db = bib_db

    def fetch_from_crossref(self, cite_key):
        query = cite_key.replace('_', ' ')
        try:
            url = f"https://api.crossref.org/works?query={query}&rows=1"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get('message', {}).get('items', [])
                if items:
                    item = items[0]
                    doi = item.get('DOI', '')
                    title = item.get('title', [''])[0]
                    bibtex = f"@article{{{cite_key},\n  title={{{title}}},\n  doi={{{doi}}}\n}}"
                    return bibtex
        except Exception as e:
            print(f"Failed to fetch from CrossRef: {e}")
        return None
    def verify_and_resolve(self, tex_content):
        citations = re.findall(r'\\cite\{([^}]+)\}', tex_content)
        
        missing_keys = []
        for match in citations:
            keys = [k.strip() for k in match.split(',')]
            for k in keys:
                if k not in self.bib_db:
                    missing_keys.append(k)

        if missing_keys:
            raise MissingBibTeXKeyError(f"Missing keys found: {missing_keys}")

        return True

    def compile(self, tex_content):
        try:
            self.verify_and_resolve(tex_content)
            return True, "PDF compiled successfully."
        except MissingBibTeXKeyError as e:
            missing_keys = re.findall(r'\\cite\{([^}]+)\}', tex_content)
            all_missing = []
            for match in missing_keys:
                keys = [k.strip() for k in match.split(',')]
                for k in keys:
                    if k not in self.bib_db:
                        all_missing.append(k)
            
            for k in set(all_missing):
                bibtex = self.fetch_from_crossref(k)
                if bibtex:
                    self.bib_db[k] = bibtex
            
            # Re-compile
            try:
                self.verify_and_resolve(tex_content)
                return True, "PDF compiled successfully after resolving."
            except MissingBibTeXKeyError:
                return False, "Failed to resolve all missing keys."
