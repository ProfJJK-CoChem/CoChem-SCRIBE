
import sys
import os
import unittest
from pathlib import Path

# Add the CoChem-SCRIBE directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from cochem_scribe.formatting.image_linking import preflight_latex_ast, BrokenImageReferenceError

class TestAudit075BrokenImage(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(__file__).parent / 'test_data_075'
        self.test_dir.mkdir(exist_ok=True)
        (self.test_dir / 'figures').mkdir(exist_ok=True)
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

    def test_phantom_svg_with_fallback(self):
        # Create a fallback image
        (self.test_dir / 'figures' / 'optimized_geometry.png').touch()
        
        latex_content = r'Some text \\includegraphics{figures/optimized_geometry.svg} more text.'
        try:
            new_content = preflight_latex_ast(latex_content, self.test_dir)
            self.assertIn('optimized_geometry.png', new_content)
            self.assertNotIn('optimized_geometry.svg', new_content)
        except BrokenImageReferenceError:
            self.fail('Unexpected BrokenImageReferenceError when fallback exists.')
            
    def test_phantom_svg_without_fallback(self):
        latex_content = r'Some text \\includegraphics{figures/optimized_geometry.svg} more text.'
        with self.assertRaises(BrokenImageReferenceError):
            preflight_latex_ast(latex_content, self.test_dir)

if __name__ == '__main__':
    unittest.main()
