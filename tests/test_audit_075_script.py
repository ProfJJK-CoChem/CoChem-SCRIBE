
import sys
import os

sys.path.append(os.path.abspath('CoChem-SCRIBE'))

from cochem_scribe.formatting.image_linking import BrokenImageReferenceError, preflight_latex_ast
from pathlib import Path
import tempfile
import shutil

def run_notebook_simulation():
    print('Starting Jupyter Notebook Execution Simulation...')
    
    # Setup temp directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        figs_dir = temp_path / 'figures'
        figs_dir.mkdir()
        
        # Scenario 1: No fallback exists
        latex_content_no_fallback = r'\includegraphics{figures/optimized_geometry.svg}'
        
        print('\nScenario 1: Phantom SVG with NO fallback (expecting crash)')
        try:
            preflight_latex_ast(latex_content_no_fallback, temp_path)
            print('FAIL: Did not crash as expected.')
        except BrokenImageReferenceError as e:
            print(f'SUCCESS: Trapped BrokenImageReferenceError: {e}')
            
        # Scenario 2: Fallback exists
        print('\nScenario 2: Phantom SVG WITH fallback (expecting dynamic resolution)')
        (figs_dir / 'optimized_geometry.png').touch()
        
        try:
            new_latex = preflight_latex_ast(latex_content_no_fallback, temp_path)
            print(f'Resolved LaTeX: {new_latex}')
            
            if 'optimized_geometry.png' in new_latex and 'optimized_geometry.svg' not in new_latex:
                print('SUCCESS: Path dynamically resolved.')
            else:
                print('FAIL: Path not dynamically resolved correctly.')
        except Exception as e:
            print(f'FAIL: Unexpected error during resolution: {e}')

if __name__ == '__main__':
    run_notebook_simulation()
