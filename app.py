import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Check Data Quality", layout="wide")

st.markdown(
    """
    <style>
    .page-header {
        margin-bottom: 0.25rem;
    }
    .page-description {
        margin-top: 0;
        margin-bottom: 1.5rem;
        color: #555;
        line-height: 1.6;
    }
    .dropzone {
        border: 2px dashed #aaa;
        border-radius: 16px;
        padding: 36px 24px;
        text-align: center;
        background: #fafafa;
        color: #333;
        transition: border-color 0.2s ease, background-color 0.2s ease;
        margin-bottom: 1.5rem;
    }
    .dropzone:hover {
        border-color: #777;
        background: #f4f4f4;
    }
    .button-row {
        display: flex;
        justify-content: start;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 0.5rem;
        width: 100%;
    }
    .button-row .stColumn {
        flex: 0 1 auto !important;
        width: auto !important;
    }
    .button-row button,
    .button-row .stButton > button {
        font-size: 0.9rem;
        padding: 0.65rem 1rem;
        border-radius: 999px;
        border: 1px solid #888;
        background: #fff;
        color: #222;
        cursor: pointer;
        transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.1s ease;
    }
    .count-badge {
        display: inline-block;
        margin-left: 8px;
        background: #eef2ff;
        color: #2b2b2b;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.8rem;
        vertical-align: middle;
    }
    .button-row button:hover,
    .button-row .stButton > button:hover {
        background: #f0f0f0;
        border-color: #666;
        transform: translateY(-1px);
    }
    .empty-table {
        color: #666;
        padding: 12px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Check Data Quality")
st.markdown(
    "<p class='page-description'>Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua ut enim.</p>",
    unsafe_allow_html=True,
)

uploaded_files = st.file_uploader(
    "",
    type=["geojson", "json", "gpkg", "zip", "shp", "csv"],
    accept_multiple_files=True,
)


def _read_first_upload(uploaded_list):
    if not uploaded_list:
        return None, None
    f = uploaded_list[0]
    name = f.name.lower()
    try:
        if name.endswith('.csv'):
            df = pd.read_csv(f)
            return df, f.name
        # treat as geospatial
        import geopandas as gpd
        import tempfile, os

        suffix = Path(name).suffix or '.geojson'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.getbuffer())
            tmp_path = tmp.name
        try:
            gdf = gpd.read_file(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        # convert geometry to WKT for table display
        if 'geometry' in gdf.columns:
            gdf2 = gdf.copy()
            try:
                gdf2['geometry'] = gdf2.geometry.apply(lambda x: x.wkt if x is not None else None)
            except Exception:
                gdf2['geometry'] = gdf2.geometry.astype(str)
            return gdf2, f.name
        return gdf, f.name
    except Exception as e:
        st.error(f"Failed to read uploaded file: {e}")
        return None, None


# read first uploaded file (if any) to compute preview and dataset size
display_df, display_name = _read_first_upload(uploaded_files)

# build button names from data_quality_checks folder
check_folder = Path("data_quality_checks")
check_files = sorted(check_folder.glob("*.py")) if check_folder.exists() else []
button_names = [path.stem for path in check_files]
if not button_names:
    button_names = ["overlaps", "slivers", "self-intersections"]

# compute per-check counts immediately so badges reflect dataset state
check_counts = {}
for name in button_names:
    check_counts[name] = 0
    if display_df is None:
        continue
    mod_path = check_folder / f"{name}.py"
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"checks.{name}", str(mod_path))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "run"):
                try:
                    res = mod.run(display_df)
                    if hasattr(res, "__len__"):
                        check_counts[name] = int(len(res))
                except Exception:
                    check_counts[name] = 0
    except Exception:
        check_counts[name] = 0

# initialize session state for selected check
if "selected_check" not in st.session_state:
    st.session_state.selected_check = None

with st.container(horizontal=True):
    if st.button("All", disabled=display_df is None):
        st.session_state.selected_check = None
    for name in button_names:
        cnt = check_counts.get(name, 0)
        label = f"{name} ({cnt})" if cnt > 0 else name
        if st.button(label, disabled=display_df is None):
            st.session_state.selected_check = name    

st.subheader("Data preview")
if display_df is None:
    st.write("No data quality checks have been executed yet. Upload a file and run a check to populate the table.")
    empty_df = pd.DataFrame(columns=["Column 1", "Column 2", "Column 3", "Status"])
    st.dataframe(empty_df, use_container_width=True)
else:
    selected = st.session_state.selected_check
    if selected is None:
        st.write(f"Showing preview of: {display_name}")
        st.dataframe(display_df, use_container_width=True)
    else:
        # Run the selected check and display matching rows from original data
        mod_path = check_folder / f"{selected}.py"
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(f"checks.{selected}", str(mod_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "run"):
                    try:
                        res = mod.run(display_df)
                        st.write(f"Showing results for: {selected}")
                        if res is None or (hasattr(res, "shape") and res.shape[0] == 0):
                            st.info("No issues found by this check.")
                        else:
                            # Extract row indices from check results and filter original data
                            if "orig_index" in res.columns:
                                indices = res["orig_index"].tolist()
                                filtered_df = display_df.iloc[indices]
                            else:
                                filtered_df = res
                            st.dataframe(filtered_df, use_container_width=True)
                    except Exception as e:
                        st.error(f"Check ran but failed: {e}")
                else:
                    st.error("Check module does not implement run(df)")
        except Exception as e:
            st.error(f"Failed to import check: {e}")
