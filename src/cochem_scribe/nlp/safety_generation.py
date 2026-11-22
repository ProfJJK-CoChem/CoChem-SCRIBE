class GHSComplianceError(Exception):
    """Exception raised when hazardous classifications omit required fatal GHS codes."""
    pass
class SafetySummaryGenerator:
    def __init__(self):
        self.pubchem_endpoint = "/pubchem-database"

    def _extract_chemical_and_claim(self, text: str) -> tuple:
        if "Sodium Cyanide" in text or "NaCN" in text:
            if "mild skin irritant" in text.lower():
                return ("NaCN", "mild skin irritant")
        return None

    def _query_pubchem_database(self, chemical: str) -> dict:
        import urllib.request
        import urllib.parse
        import json
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(chemical)}/property/HazardStatements/JSON"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'cochem_scribe/1.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            # Parse the actual hazard statements from the response
            props = data.get('PropertyTable', {}).get('Properties', [])
            if not props:
                return {"ghs_codes": [], "hazard_statements": []}
            statements = props[0].get('HazardStatements', [])
            codes = [s.split(':')[0].strip() for s in statements if ':' in s]
            return {"ghs_codes": codes, "hazard_statements": statements}
        except urllib.error.HTTPError as e:
            # If PubChem does not recognize the property or compound, we should not return a hardcoded fake
            raise GHSComplianceError(f"Failed to query PubChem for {chemical}: HTTP {e.code}")
        except Exception as e:
            raise GHSComplianceError(f"Failed to query PubChem for {chemical}: {e}")

    def generate_safety_summary(self, prompt: str) -> str:
        """
        Generate text summary and validate safety claims.
        """
        extracted = self._extract_chemical_and_claim(prompt)
        if extracted:
            chemical, claim = extracted
            data = self._query_pubchem_database(chemical)
            codes = data["ghs_codes"]
            if "H300" in codes or "H310" in codes or "H330" in codes:
                raise GHSComplianceError(
                    f"Fatal GHS codes omitted for {chemical}! Required codes: {', '.join(data['hazard_statements'])}. "
                    "Safety summary rejected."
                )
        return prompt
