
import re
from pathlib import Path

class BrokenImageReferenceError(Exception):
    raise NotImplementedError("Implementation pending")
def preflight_latex_ast(latex_content: str, search_dir: str | Path) -> str:
    search_dir = Path(search_dir)
    pattern = re.compile(r'\\includegraphics(?:\[.*?\])?\{(.*?)\}')
    
    def replacer(match):
        img_path = match.group(1)
        # Assuming the path in latex is relative to search_dir or just a filename
        path_obj = Path(img_path)
        filename = path_obj.name
        stem = path_obj.stem
        
        full_path = search_dir / img_path
        
        if not full_path.exists() or full_path.suffix.lower() == '.svg':
            # Attempt fallback search
            fallback = None
            for p in search_dir.rglob(f'{stem}.*'):
                if p.suffix.lower() in ['.png', '.jpg', '.jpeg', '.pdf']:
                    fallback = p
                    break
            
            if fallback:
                # Rewrite to the fallback path
                # Ideally, this should be a relative path that LaTeX can handle
                new_path = fallback.relative_to(search_dir).as_posix()
                # We also need to construct the full tag with original options if any
                original_tag = match.group(0)
                return original_tag.replace('{' + img_path + '}', '{' + new_path + '}')
            else:
                raise BrokenImageReferenceError(f'Image reference broken and no fallback found for: {img_path}')
        
        return match.group(0)

    # Note: re.sub with a function will run the function for every match
    try:
        new_content = pattern.sub(replacer, latex_content)
    except BrokenImageReferenceError:
        raise
        
    return new_content
