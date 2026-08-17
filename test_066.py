import logging
logging.basicConfig(level=logging.INFO)
import sys
from cochem_scribe.nlp.semantic_checker import BiomedicalTextGenerator, SemanticOntologyViolation

generator = BiomedicalTextGenerator()
prompt = "Imatinib primarily acts as a direct agonist of the G-protein coupled serotonin receptor."

try:
    generator.generate_summary(prompt)
    logging.info("FAIL: Exception not thrown")
except SemanticOntologyViolation as e:
    logging.info("SUCCESS")
    logging.info(f"Exception message: {str(e)}")


