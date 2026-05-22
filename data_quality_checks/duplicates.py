"""Duplicate detection checks.

Provides a `run(df)` function that accepts a pandas/geopandas DataFrame
and returns a DataFrame listing rows that are duplicates by `id` and/or
by `geometry` (WKT string). The first occurrence is kept and later
occurrences are flagged as duplicates.
"""
from typing import Optional
import pandas as pd


def _find_id_column(df: pd.DataFrame) -> Optional[str]:
	"""Return a column name to use as the identifier, or None if not found."""
	candidates = [c for c in df.columns if c.lower() == "id"]
	if candidates:
		return candidates[0]
	# common alternatives
	for alt in ("identifier", "uid", "fid"):
		for c in df.columns:
			if c.lower() == alt:
				return c
	return None


def _find_geometry_column(df: pd.DataFrame) -> Optional[str]:
	"""Return a column name to use as WKT geometry, or None if not found."""
	for c in df.columns:
		if c.lower() == "geometry" or c.lower().endswith("wkt") or "geom" in c.lower():
			return c
	return None


def run(df: pd.DataFrame) -> pd.DataFrame:
	"""Detect duplicate rows by id and geometry.

	Parameters
	- df: pandas.DataFrame or geopandas.GeoDataFrame where geometry column
	  (if present) is represented as WKT strings or a GeoSeries named
	  "geometry".

	Returns
	- pandas.DataFrame containing rows that are duplicates. Columns:
	  ['orig_index', 'dup_type', 'duplicate_of', <id_col?>, <geom_col?>]

	Behavior:
	- For id duplicates we keep the first occurrence (left-most) and mark
	  later rows as duplicates.
	- For geometry duplicates we compare the geometry column values (WKT
	  strings) and similarly keep the first occurrence.
	"""
	if not isinstance(df, pd.DataFrame):
		raise TypeError("df must be a pandas DataFrame or GeoDataFrame")

	id_col = _find_id_column(df)
	geom_col = _find_geometry_column(df)

	n = len(df)
	if n == 0:
		return pd.DataFrame(columns=["orig_index", "dup_type", "duplicate_of"] + ([id_col] if id_col else []) + ([geom_col] if geom_col else []))

	# compute duplicate masks
	dup_id = pd.Series(False, index=df.index)
	dup_geom = pd.Series(False, index=df.index)

	if id_col is not None:
		dup_id = df.duplicated(subset=[id_col], keep="first")

	if geom_col is not None:
		# If geometry is a shapely geometry, convert to string for comparison
		try:
			sample = df[geom_col].iloc[0]
			# if it's not a string, coerce
			if not isinstance(sample, str):
				geom_vals = df[geom_col].astype(str)
			else:
				geom_vals = df[geom_col]
		except Exception:
			geom_vals = df[geom_col].astype(str)
		dup_geom = geom_vals.duplicated(keep="first")

	rows = []
	for idx in df.index:
		is_id = bool(dup_id.loc[idx])
		is_geom = bool(dup_geom.loc[idx])
		if not (is_id or is_geom):
			continue
		dup_types = []
		duplicate_of = None
		if is_id and id_col is not None:
			dup_types.append("id")
			val = df.at[idx, id_col]
			# find first index with same id
			first_idx = df.index[df[id_col] == val][0]
			duplicate_of = first_idx if duplicate_of is None else duplicate_of
		if is_geom and geom_col is not None:
			dup_types.append("geometry")
			gval = df.at[idx, geom_col]
			# coerce to string when matching
			first_idx_geom = df.index[(df[geom_col].astype(str) == str(gval))][0]
			duplicate_of = first_idx_geom if duplicate_of is None else duplicate_of

		rows.append({
			"orig_index": idx,
			"dup_type": ",".join(dup_types),
			"duplicate_of": duplicate_of,
		})

	if not rows:
		return pd.DataFrame(columns=["orig_index", "dup_type", "duplicate_of"] + ([id_col] if id_col else []) + ([geom_col] if geom_col else []))

	out = pd.DataFrame(rows)
	# attach id/geom values for convenience if available
	if id_col is not None:
		out[id_col] = out["orig_index"].map(lambda i: df.at[i, id_col])
	if geom_col is not None:
		out[geom_col] = out["orig_index"].map(lambda i: df.at[i, geom_col])

	return out


if __name__ == "__main__":
	# quick local test
	df = pd.DataFrame({
		"id": [1, 2, 2, 3, 4, 4],
		"geometry": ["POINT (0 0)", "POINT (1 1)", "POINT (1 1)", "POINT (2 2)", "POINT (3 3)", "POINT (3 3)"]
	})
	print(run(df))

