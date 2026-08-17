import urllib.request
import urllib.parse
import json
import re

class SemanticOntologyViolation(Exception):
    pass
class BiomedicalTextGenerator:
    def __init__(self):
        self.europepmc_endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        
    def _extract_triplet(self, text: str) -> tuple:
        pattern = r"([A-Za-z0-9\-]+).*?acts as a.*? (agonist|antagonist|inhibitor) of the (.*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            e1, rel, e2 = match.groups()
            return e1.strip(), rel.strip(), e2.strip().rstrip('.')
        
        words = text.split()
        if len(words) > 3:
            return words[0], "mechanism", " ".join(words[2:])
        return None, None, None

    def _query_europepmc_validation(self, entity1: str, relationship: str, entity2: str) -> dict:
        query_str = f'"{entity1}" AND "{relationship}" AND "{entity2}"'
        encoded_query = urllib.parse.quote(query_str)
        url = f"{self.europepmc_endpoint}?query={encoded_query}&format=json"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'mailto:cochem@example.com'})
            resp = urllib.request.urlopen(req)
            data = json.loads(resp.read())
            hit_count = data.get('hitCount', 0)
            
            if hit_count == 0:
                return {
                    "support_count": 0,
                    "contradiction_citation": f"EuropePMC hitCount: 0 for '{query_str}'",
                    "verified_pathway": "No verified pathway found in literature"
                }
            return {"support_count": hit_count}
        except Exception as e:
            raise SemanticOntologyViolation(f"EuropePMC API request failed: {e}")

    def generate_summary(self, prompt: str) -> str:
        e1, rel, e2 = self._extract_triplet(prompt)
        if e1 and rel and e2:
            validation_data = self._query_europepmc_validation(e1, rel, e2)
            if validation_data["support_count"] == 0:
                raise SemanticOntologyViolation(
                    f"Biological contradiction [{validation_data['contradiction_citation']}]: "
                    "Zero literature supports this specific target engagement. "
                    f"Regeneration constrained strictly to the verified {validation_data['verified_pathway']} is required."
                )
        return prompt
