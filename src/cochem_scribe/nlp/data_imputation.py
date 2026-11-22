import pandas as pd
import warnings

class DataHallucinationWarning(Warning):
    """Warning raised when missing experimental data is detected and imputation is blocked."""
    pass
def generate_reporting_table(df, interpolate=False):
    """
    Generate a standardized reporting table.
    Ensures missing values in empirical/experimental columns are strictly marked as 'N/A'
    and throws DataHallucinationWarning, preventing any interpolation on those columns.
    """
    out_df = df.copy()
    
    # Identify empirical/experimental columns
    exp_cols = [col for col in out_df.columns if 'experiment' in col.lower() or 'empirical' in col.lower()]
    
    for col in exp_cols:
        if out_df[col].isna().any():
            warnings.warn("Missing experimental data detected. Hallucination prevention activated.", DataHallucinationWarning)
            # Forcefully inject 'N/A'
            out_df[col] = out_df[col].apply(lambda x: "N/A" if pd.isna(x) else x)
            
    # Apply interpolation to other columns if requested, but experimental columns with 'N/A' (string) 
    # will naturally be ignored by numeric interpolation.
    if interpolate:
        # We only interpolate numeric columns to avoid issues with our "N/A" strings
        numeric_cols = out_df.select_dtypes(include=['number']).columns
        out_df[numeric_cols] = out_df[numeric_cols].interpolate()
        
    return out_df
