import logging
logging.basicConfig(level=logging.INFO)

import sys
import os

sys.path.append(os.path.abspath('CoChem-SCRIBE'))

from cochem_scribe.formatting.image_linking import BrokenImageReferenceError, preflight_latex_ast
from pathlib import Path
import tempfile
import shutil

def run_notebook_simulation():
    logging.info('Starting Jupyter Notebook Execution Simulation...')
    
    # Setup temp directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        figs_dir = temp_path / 'figures'
        figs_dir.mkdir()
        
        # Scenario 1: No fallback exists
        latex_content_no_fallback = r'\includegraphics{figures/optimized_geometry.svg}'
        
        logging.info('\nScenario 1: Phantom SVG with NO fallback (expecting crash)')
        try:
            preflight_latex_ast(latex_content_no_fallback, temp_path)
            logging.info('FAIL: Did not crash as expected.')
        except BrokenImageReferenceError as e:
            logging.info(f'SUCCESS: Trapped BrokenImageReferenceError: {e}')
            
        # Scenario 2: Fallback exists
        logging.info('\nScenario 2: Phantom SVG WITH fallback (expecting dynamic resolution)')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        fig.savefig(figs_dir / 'optimized_geometry.png')
        plt.close(fig)
        
        try:
            new_latex = preflight_latex_ast(latex_content_no_fallback, temp_path)
            logging.info(f'Resolved LaTeX: {new_latex}')
            
            if 'optimized_geometry.png' in new_latex and 'optimized_geometry.svg' not in new_latex:
                logging.info('SUCCESS: Path dynamically resolved.')
            else:
                logging.info('FAIL: Path not dynamically resolved correctly.')
        except Exception as e:
            logging.info(f'FAIL: Unexpected error during resolution: {e}')

if __name__ == '__main__':
    run_notebook_simulation()


