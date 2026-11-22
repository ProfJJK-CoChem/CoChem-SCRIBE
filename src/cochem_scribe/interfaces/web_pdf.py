import warnings

class CSSBleedWarning(Warning):
    pass
def render_preview(canvas_html: str, canvas_width: int, parent_width: int = 1000) -> str:
    """
    Renders a WebGL canvas in the previewer. Intercepts DOM insertion to prevent CSS bleeding.
    """
    if canvas_width > parent_width:
        warnings.warn("Figure width exceeds parent viewport. Wrapping in responsive container.", CSSBleedWarning)
        return f'<div class="responsive-figure-container">\n  {canvas_html}\n</div>'
    
    return canvas_html
