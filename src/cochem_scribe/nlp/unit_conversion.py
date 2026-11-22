class DimensionalAnalysisError(Exception):
    pass
class UnitConversionEngine:
    def __init__(self):
        self.hartree_to_kcal_mol = 627.509

    def parse_and_validate(self, llm_output: str, metadata_value: float, metadata_unit: str) -> str:
        """
        Parses the LLM output and compares the numerical value to the expected unit.
        If a mismatch is found, raises DimensionalAnalysisError and returns the corrected string.
        """
        if metadata_unit == "Hartree" and "kcal/mol" in llm_output:
            import re
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", llm_output)
            expected_converted = metadata_value * self.hartree_to_kcal_mol
            
            # Check if any extracted number is close to the raw uncoverted value instead of the converted value
            for num_str in numbers:
                try:
                    val = float(num_str)
                    if abs(val - metadata_value) < 1e-4:
                        raise DimensionalAnalysisError(f"Mismatch detected! Expected Hartree, got kcal/mol with uncorrected value.")
                except ValueError:
                    continue
        return llm_output

    def correct_text(self, llm_output: str, metadata_value: float, metadata_unit: str) -> str:
        if metadata_unit == "Hartree" and "kcal/mol" in llm_output:
            expected_converted = int(round(metadata_value * self.hartree_to_kcal_mol))
            return llm_output.replace(str(metadata_value), str(expected_converted))
        return llm_output
