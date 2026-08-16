class IUPACNomenclatureError(Exception):
    def __init__(self, message, canonical_name=None):
        super().__init__(message)
        self.canonical_name = canonical_name

def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

class IUPACGenerator:
    def __init__(self):
        self.pubchem_endpoint = "/pubchem-database"

    def _query_pubchem(self, smiles: str) -> str:
        try:
            import requests
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles}/property/IUPACName/JSON"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('PropertyTable', {}).get('Properties', [{}])[0].get('IUPACName', '[MISSING DATA]')
        except Exception:
            raise NotImplementedError("Implementation pending")
        return "[MISSING DATA]"

    def validate_and_inject(self, smiles: str, generated_name: str, template: dict) -> dict:
        pubchem_name = self._query_pubchem(smiles)
        
        dist = levenshtein_distance(generated_name, pubchem_name)
        divergence = dist / max(len(generated_name), len(pubchem_name))
        
        if divergence > 0.30:
            template["chemical_name"] = pubchem_name
            raise IUPACNomenclatureError(
                f"Generated name '{generated_name}' divergence {divergence*100:.1f}% > 30% from PubChem standard '{pubchem_name}'.",
                canonical_name=pubchem_name
            )
            
        template["chemical_name"] = generated_name
        return template
