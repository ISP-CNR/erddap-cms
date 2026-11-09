import os, xmltodict, subprocess, hashlib
from xml.sax.saxutils import quoteattr
from os import listdir
from os.path import isfile, join
from Dataset import Dataset, FORCE_LIST
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import csv
import shlex
import sys
import chardet
import urllib3
import io
import time
import netCDF4 as nc
import xarray as xr
import pandas as pd
import numpy as np
import re
from enum import Enum
from erddapy import ERDDAP
from flask_mail import Message
from logger_config import logger

class Protocol(Enum):
    opendap = "WWW:LINK-1.0-http--opendap"
    webaddress = "WWW:LINK-1.0-http--link"
    download = "WWW:DOWNLOAD-1.0-http--download"

# Constants
xmldir = '/datasets_xml_parts/active'
URL_PATH = os.environ['URL_PATH']
ERDDAP_BASE_URL = os.environ['ERDDAP_baseUrl']
datasets_data_dir='/datasets_data'
ERDDAP_INTERNAL_URL = 'http://localhost:8080'
DASHBOARD_URL = os.getenv('DASHBOARD_URL')

def get_dataset(id, user):
  try:
    d = Dataset(join(xmldir, id + ".xml"))
    if d.is_readable(user):
      return d
      
  except Exception as e:
    logger.exception(f"Error in parsing dataset with id: {id}")
    logger.exception(e)
  
  return None

def get_datasets_list(user):
    datasets_list = []

    for dataset_id in get_datasets_id_list():
        d = get_dataset(dataset_id, user)
        if d:
            datasets_list.append(d)
    
    return datasets_list

def get_datasets_id_list():
    return [f.removesuffix(".xml") for f in listdir(xmldir) if isfile(join(xmldir, f))]

def get_private_dataset_roles():
    # (role, dataset title) pairs collected from every private dataset's
    # accessibleTo, so the ERDDAP user "Roles" field can offer readable
    # options ("Snow height at ..." rather than a bare PRIVATE_<uuid> string).
    # Excludes ADMIN, which is offered separately as a standing option.
    roles = []
    for dataset_id in get_datasets_id_list():
        try:
            with open(join(xmldir, dataset_id + ".xml")) as f:
                d = xmltodict.parse(f.read(), force_list=FORCE_LIST)
            dataset = d['dataset']
            accessible_to = dataset.get('accessibleTo')
            if not accessible_to:
                continue
            title = dataset_id
            # dataset.get('addAttributes') can be None (an empty <addAttributes/>
            # tag, not a missing one) - "or {}" catches that case too, unlike
            # .get('addAttributes', {}) which only applies when the key is absent
            for att in (dataset.get('addAttributes') or {}).get('att') or []:
                if att.get('@name') == 'title' and att.get('#text'):
                    title = att['#text']
                    break
        except Exception:
            continue

        for role in accessible_to.split(','):
            role = role.strip()
            if role and role != 'ADMIN':
                roles.append({'role': role, 'dataset_id': dataset_id, 'title': title})
    return roles

def get_dataset_titles():
    # {dataset_id: title}, for pages that only have a bare dataset_id on hand
    # (e.g. a Permission row) and want something human-readable to show -
    # falls back to the id itself if the title can't be read for some reason.
    titles = {}
    for dataset_id in get_datasets_id_list():
        titles[dataset_id] = dataset_id
        try:
            with open(join(xmldir, dataset_id + ".xml")) as f:
                d = xmltodict.parse(f.read(), force_list=FORCE_LIST)
            for att in (d['dataset'].get('addAttributes') or {}).get('att') or []:
                if att.get('@name') == 'title' and att.get('#text'):
                    titles[dataset_id] = att['#text']
                    break
        except Exception:
            continue
    return titles

def compile_datasets_xml():
    env=os.environ 
    bash_command = "bash /datasets_xml_parts/compile_datasets_xml.sh"
    result = subprocess.run(["bash", "-c", bash_command], capture_output=True, text=True, env=env)

    output = result.stdout
    error = result.stderr

    return output, error

ERDDAP_USERS_XML = "/datasets_xml_parts/users.xml"

def erddap_password_hash(username, password):
    # matches ERDDAP's "UEPMD5" custom-authentication passwordEncoding
    # (ERDDAP_passwordEncoding=UEPMD5): MD5("username:ERDDAP:password")
    return hashlib.md5(f"{username}:ERDDAP:{password}".encode()).hexdigest()

def write_erddap_users_xml():
    # regenerates the <user> block ERDDAP reads for its "custom" authentication
    # (see setup.xml) from the CMS's own ErddapUser table. Included by
    # compile_datasets_xml.sh into the final datasets.xml.
    import multiauth  # local import: multiauth imports this module, so avoid a cycle at import time
    lines = []
    for user in multiauth.get_erddap_users():
        lines.append(
            f'<user username={quoteattr(user.username)} '
            f'password={quoteattr(user.password_hash)} '
            f'roles={quoteattr(user.roles or "")}/>'
        )
    with open(ERDDAP_USERS_XML, "w") as f:
        f.write("\n\n".join(lines))
        f.write("\n\n")

def reload_dataset(datasetID):
    env=os.environ 
    bash_command = f"cd /erddapData/flag && touch {clean_user_input(datasetID)}"
    result = subprocess.run(["bash", "-c", bash_command], capture_output=True, text=True, env=env)
    
    output = result.stdout
    error = result.stderr

    return output, error
  
def validate_dataset(datasetID):
    env=os.environ 
    bash_command = f"cd /usr/local/tomcat/webapps/erddap/WEB-INF && su tomcat -s /bin/bash -c \"export PATH=$PATH:/opt/java/openjdk/bin/ && bash DasDds.sh {clean_user_input(datasetID)}\""
    result = subprocess.run(["bash", "-c", bash_command], capture_output=True, text=True, env=env)

    output = result.stdout
    error = result.stderr

    return output, error


def get_dataset_files(dataset):
    dataset_dir = dataset.files_dir

    # get the file list
    file_list = [f for f in listdir(dataset_dir) if isfile(join(dataset_dir, f))]

    return file_list

def get_low_cardinality_columns(filename, max_distinct=20):
    # GenerateDatasetsXml's own subsetVariables heuristic only picks columns that
    # are constant WITHIN the one sample file (it assumes a one-file-per-station
    # layout, where such a column would vary across files); it misses genuinely
    # useful low-cardinality categorical columns (e.g. a "Species" column with 2
    # values) that legitimately vary within a single file. This looks at the
    # actual data to find those, by real cardinality instead.
    with open(filename, "rb") as f:
        if f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']:
            return []  # NetCDF, not ascii/csv - not handled here
    try:
        delimiter = find_delimiter(filename)
        df = pd.read_csv(filename, sep=delimiter)
    except Exception:
        return []

    candidates = []
    n_rows = len(df)
    for col in df.columns:
        n_unique = df[col].nunique(dropna=True)
        # >1 (a constant column isn't a useful filter) and < n_rows (excludes
        # effectively-unique columns like an id or a timestamp)
        if 1 < n_unique <= max_distinct and n_unique < n_rows:
            candidates.append(col.strip())
    return candidates

def find_delimiter(filename):
    sniffer = csv.Sniffer()
    with open(filename) as fp:
        delimiter = sniffer.sniff(fp.read(8000)).delimiter
    return delimiter

UTF8_BOM = b'\xef\xbb\xbf'

def strip_utf8_bom(filename):
    # a UTF-8 BOM (e.g. from "CSV UTF-8" exports in Excel) is invisible and harmless to
    # pandas, but GenerateDatasetsXml's charset auto-detection reports it as "UTF-8-SIG",
    # which Java doesn't recognize as a valid encoding name - strip it before either the
    # preview or the real GenerateDatasetsXml run ever sees the file
    with open(filename, 'rb') as f:
        content = f.read()
    if content.startswith(UTF8_BOM):
        with open(filename, 'wb') as f:
            f.write(content[len(UTF8_BOM):])

def human_readable_size(num_bytes):
    size = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024

DECIMAL_COMMA_RE = re.compile(r'^-?\d+,\d+$')
# ERDDAP's own ISO 8601 time parser accepts truncating the full
# yyyy-MM-ddTHH:mm:ssZ string from the end - you can drop Z, then :ss, then
# :mm, then :HH, then T, in that order - down to a bare yyyy-MM-dd for
# date-only data (see ERDDAP's advancedSearchTimeTooltip). Match the same
# rule here instead of only accepting the full form.
DATE_TIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}(:\d{2}(:\d{2}Z?)?)?)?$')
WARNING_SCAN_ROWS = 100

def check_decimal_separator(df):
    warnings = []
    for col in df.columns:
        values = df[col].dropna().astype(str).head(WARNING_SCAN_ROWS)
        bad_value = next((v for v in values if DECIMAL_COMMA_RE.match(v.strip())), None)
        if bad_value is not None:
            warnings.append({
                "column": str(col),
                "message": f"Column '{col}' looks like it uses ',' as the decimal separator (e.g. '{bad_value}'). ERDDAP expects '.' (e.g. '{bad_value.replace(',', '.')}')."
            })
    return warnings

def check_duplicate_columns(filename, delimiter):
    # pandas silently dedupes repeated header names itself (temperature, temperature.1)
    # before we ever see df.columns, so this has to look at the raw header line - a
    # duplicate reaches GenerateDatasetsXml as a hard failure ("Duplicate column names")
    with open(filename, newline='') as f:
        header_line = f.readline()
    raw_columns = next(csv.reader([header_line], delimiter=delimiter))
    counts = {}
    for name in raw_columns:
        counts[name] = counts.get(name, 0) + 1
    duplicates = [name for name, count in counts.items() if count > 1]
    if duplicates:
        return [{
            "column": ", ".join(duplicates),
            "message": f"Duplicate column name(s): {', '.join(duplicates)}. Each column needs a unique name."
        }]
    return []

def find_time_columns(df):
    return [col for col in df.columns if 'time' in str(col).lower() or 'date' in str(col).lower()]

def check_date_format(df, time_columns):
    warnings = []
    for col in time_columns:
        values = df[col].dropna().astype(str).head(WARNING_SCAN_ROWS)
        bad_value = next((v for v in values if not DATE_TIME_RE.match(v.strip())), None)
        if bad_value is not None:
            warnings.append({
                "column": str(col),
                "message": f"Column '{col}' should use the ISO 8601 format yyyy-MM-ddTHH:mm:ssZ (or a truncation of it, down to yyyy-MM-dd for date-only data), but found a value like '{bad_value}'."
            })
    return warnings

def check_time_column_presence(time_columns):
    if len(time_columns) == 0:
        return [{
            "column": None,
            "message": "No column looks like a time/date column (its name should contain 'time' or 'date'). ERDDAP datasets need a recognizable time column."
        }]
    if len(time_columns) > 1:
        return [{
            "column": ", ".join(str(c) for c in time_columns),
            "message": f"Multiple columns look like a time/date column: {', '.join(str(c) for c in time_columns)}. It should be clear which one is the actual time variable."
        }]
    return []

MIN_DATA_ROWS = 3

def check_minimum_rows(row_count):
    # check_header_csv (called for real, unprotected, by _build_args_for_ascii when the
    # dataset is actually created) needs at least this many data rows or it raises an
    # IndexError - catch it here first so the preview can say so plainly
    if row_count < MIN_DATA_ROWS:
        return [{
            "column": None,
            "message": f"The file has only {row_count} data row{'s' if row_count != 1 else ''}. At least {MIN_DATA_ROWS} are needed to generate the dataset."
        }]
    return []

def build_checks(*named_warning_lists):
    # each entry is (id, label, warnings) or (id, label, warnings, applicable) - one
    # checklist item per check, "passed" when that check found nothing to warn about.
    # applicable=False (e.g. no time column to check the date format of) means the
    # check had nothing to run against - shown as neutral rather than a false "passed"
    checks = []
    for entry in named_warning_lists:
        check_id, label, warnings = entry[0], entry[1], entry[2]
        applicable = entry[3] if len(entry) > 3 else True
        checks.append({
            "id": check_id, "label": label, "warnings": warnings,
            "applicable": applicable, "passed": applicable and len(warnings) == 0,
        })
    all_passed = all(c["passed"] or not c["applicable"] for c in checks)
    all_warnings = [w for c in checks for w in c["warnings"]]
    return checks, all_passed, all_warnings

def normalize_text_encoding(filename):
    # the real upload path (_build_args_for_ascii) detects the file's charset
    # with chardet and passes it straight to GenerateDatasetsXml, so a
    # non-UTF-8 file (e.g. Windows-1252/Latin-1 from an Excel export) is
    # handled correctly there - but every preview helper below (find_delimiter,
    # check_header_csv, pandas.read_csv, ...) opens the file with the default
    # encoding and would hard-crash on it. Re-write the preview's temp copy as
    # UTF-8 upfront so the rest of the preview code doesn't need to care; this
    # never touches the real uploaded file, only the preview's own temp copy.
    with open(filename, 'rb') as f:
        raw = f.read()
    detected = chardet.detect(raw)['encoding'] or 'utf-8'
    try:
        text = raw.decode(detected)
    except (UnicodeDecodeError, LookupError):
        return
    if detected.lower().replace('-', '') not in ('utf8', 'ascii'):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)

def preview_csv(filename, file_size):
    normalize_text_encoding(filename)
    delimiter = find_delimiter(filename)

    try:
        # same detection GenerateDatasetsXml itself relies on (see check_header_csv):
        # a second row that's all units (e.g. "degrees_north") reads with a different
        # dtype per column than the row below it - too few data rows to compare falls
        # back to "no units row" rather than erroring the whole preview
        has_units_row = check_header_csv(filename, delimiter) == 3
    except Exception:
        has_units_row = False

    # count logical CSV records, not physical lines - a quoted field with an
    # embedded newline (e.g. a free-text notes column) spans multiple physical
    # lines but is still a single row
    with open(filename, newline='') as f:
        total_rows = sum(1 for _ in csv.reader(f, delimiter=delimiter))
    row_count = total_rows - (2 if has_units_row else 1)  # exclude header (+units row)

    sample_df = pd.read_csv(filename, sep=delimiter, skiprows=[1] if has_units_row else None, nrows=WARNING_SCAN_ROWS)

    time_columns = find_time_columns(sample_df)
    checks, all_passed, warnings = build_checks(
        ("minimum_rows", f"At least {MIN_DATA_ROWS} data rows", check_minimum_rows(row_count)),
        ("duplicate_columns", "No duplicate column names", check_duplicate_columns(filename, delimiter)),
        ("time_column", "Exactly one recognizable time/date column", check_time_column_presence(time_columns)),
        ("decimal_separator", "Decimal separator uses '.'", check_decimal_separator(sample_df)),
        ("date_format", "Date/time columns use ISO 8601 (yyyy-MM-ddTHH:mm:ssZ, or a truncation of it)", check_date_format(sample_df, time_columns), len(time_columns) > 0),
    )

    preview_df = sample_df.head(5)
    return {
        "filename": os.path.basename(filename),
        "row_count": max(row_count, 0),
        "column_count": len(preview_df.columns),
        "file_size": human_readable_size(file_size),
        "columns": [str(c) for c in preview_df.columns],
        # astype(str) alone leaves NaN as a bare float (not the string "nan"),
        # which json.dumps then emits as the non-standard, unparseable token
        # `NaN` - blank it out first so every cell serializes as a plain string
        "rows": preview_df.astype(object).where(preview_df.notnull(), "").astype(str).values.tolist(),
        "warnings": warnings,
        "checks": checks,
        "all_checks_passed": all_passed,
    }

def preview_netcdf(filename, file_size):
    # xarray's to_dataframe() broadcasts scalar/fixed-value variables (e.g.
    # latitude/longitude on a single-station dataset) across every row,
    # instead of netCDF4's raw indexing which only has a value for row 0 and
    # leaves every other row blank for anything not shaped like the main
    # dimension - also handles plain HDF5 (.h5) files the same way as NetCDF,
    # picking whichever backend engine actually reads the file.
    ds = xr.open_dataset(filename)
    try:
        df = ds.to_dataframe().reset_index()
        row_count = len(df)
        preview_df = df.head(5)
        # stringifying a float32 column (via astype(object)) widens each value
        # to a Python float first, showing the full float64 expansion of
        # whatever the float32 actually is (e.g. 14.100000381469727 or, for
        # larger magnitudes where float32's precision step is coarser,
        # 79.099998) - a fixed-decimals round() doesn't work for every
        # magnitude (6 decimals cleans up 14.1 but not 79.1). Format each
        # value with numpy's own shortest round-trip repr for its actual
        # float32 precision instead, same as plain str(numpy.float32(x)) uses.
        float_cols = preview_df.select_dtypes(include="float32").columns
        for col in float_cols:
            preview_df[col] = preview_df[col].apply(
                lambda v: np.format_float_positional(np.float32(v), unique=True, fractional=False, trim="-")
                if pd.notnull(v) else v
            )

        return {
            "filename": os.path.basename(filename),
            "row_count": row_count,
            "column_count": len(preview_df.columns),
            "file_size": human_readable_size(file_size),
            "columns": [str(c) for c in preview_df.columns],
            "rows": preview_df.astype(object).where(preview_df.notnull(), "").astype(str).values.tolist(),
            "warnings": [],
            "checks": [],
            "all_checks_passed": True,
        }
    finally:
        ds.close()

def generate_dataset_preview(filename, file_size):
    with open(filename, "rb") as f:
        is_nc = f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']
    if is_nc:
        return preview_netcdf(filename, file_size)
    return preview_csv(filename, file_size)

def check_new_file_matches_dataset_schema(filename, expected_source_names):
    # EDDTableFromAsciiFiles aggregates every file under fileDir together at read
    # time (see the guide's "how does ERDDAP handle multi files" note) - a file
    # with none of the expected column names doesn't error, it just silently
    # contributes zero rows, which looks like a successful upload to the user
    if not expected_source_names or not filename.lower().endswith('.csv'):
        return None
    try:
        delimiter = find_delimiter(filename)
        with open(filename) as f:
            header_line = f.readline()
        header_columns = set(next(csv.reader([header_line], delimiter=delimiter)))
    except Exception:
        return None

    if not (header_columns & set(expected_source_names)):
        return (
            f"This file's columns ({', '.join(sorted(header_columns))}) don't match "
            f"this dataset's expected columns ({', '.join(sorted(expected_source_names))}). "
            "The file was uploaded, but ERDDAP will treat it as having no data rows."
        )
    return None

def clean_user_input(value):
    return secure_filename(value)

def validate_file_extension(filename, allowed_extension) :
    file_ext = os.path.splitext(filename)[1]
    if file_ext not in allowed_extension:
        return False
    return True

def check_header_csv(filename,separator) :
    firstDataRow=2
    df1 = pd.read_csv(filename,nrows=5,sep=separator)
    df2 = pd.read_csv(filename,nrows=5,skiprows=[1],sep=separator)
    first_row = df1.iloc[0]
    second_row = df2.iloc[1]

    #Check if there is a change in data types between the first and second rows
    dtype_changes_per_element = {}

    for col in df1.columns:
        element_type_change = type(first_row[col]) != type(second_row[col])
        dtype_changes_per_element[col] = element_type_change
    
    at_least_one_true = any(value for value in dtype_changes_per_element.values())    
    if at_least_one_true:
        firstDataRow=3   
   
    return firstDataRow   

def fix_header(header):
    header_lowercase = header.lower()

    replaces = {}

    def add_replaces(short, extended):
        short_len = len(short)
        extended_len = len(extended)
        start = 0
        while True:
            try:
                index = header_lowercase.index(short, start)
            except ValueError:
                break
            if header_lowercase[index:index+extended_len] != extended:
                occurrence = header[index:index+short_len]
                result = bytearray(b"")
                for b in occurrence:
                    result.append(b)
                    result.append(b)
                replaces[occurrence] = bytes(result)

            start = index + short_len

    add_replaces(b"lat", b"latitude")
    add_replaces(b"lon", b"longitude")
    for k, v in replaces.items():
        header = header.replace(k, v)
    return header, replaces

def rollback_replaces(content, replaces):
    for k, v in replaces.items():
        content = content.replace(v.decode(), k.decode())
    return content

GENERATE_DATASETS_XML_LOG = "/erddapData/logs/GenerateDatasetsXml.out"
GENERATE_DATASETS_XML_RELOAD_MINUTES = 10080

# only the featureType values whose cdm_data_type has dedicated handling in
# fix_generated_xml (cf_role injection, cdm_timeseries_variables, depth/profile_id
# handling, ...) - Profile/Trajectory/TrajectoryProfile/Point have none, so a NetCDF
# declaring one of those is left to the user's own choice in the upload form instead
FEATURETYPE_TO_CDM_DATA_TYPE = {
    'timeseries': 'TimeSeries',
    'timeseriesprofile': 'TimeSeriesProfile',
}

def detect_cdm_data_type_from_netcdf(filename):
    # if the uploaded NetCDF already declares a supported CF featureType, use it
    # instead of asking the user to redeclare (in the upload form) what the file
    # already states - returns None if the file isn't NetCDF, has no featureType,
    # or has one we don't have dedicated handling for
    try:
        with open(filename, "rb") as f:
            if f.read(4) not in [b'\x89HDF', b'CDF\x01', b'CDF\x02']:
                return None
        feature_type = getattr(nc.Dataset(filename), 'featureType', None)
    except Exception:
        return None
    if feature_type is None:
        return None
    return FEATURETYPE_TO_CDM_DATA_TYPE.get(str(feature_type).lower())

def _detect_eddtype(filename, cdm_data_type):
    # sniff the file's magic bytes to tell an HDF/NetCDF file from ASCII/CSV
    with open(filename, "rb") as f:
        is_nc = f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']
    if not is_nc:
        return "EDDTableFromAsciiFiles"
    return "EDDGridFromNcFiles" if cdm_data_type == "Grid" else "EDDTableFromMultidimNcFiles"

def _build_args_for_ascii(filename, infoUrl, institution, summary, title):
    # find_delimiter/check_header_csv below open the file with the default
    # (UTF-8) encoding and hard-crash on anything else (e.g. a Windows-1252
    # CSV with a '‰' in the units row) - normalize to UTF-8 first, same fix
    # as the preview uses. Safe to do before the chardet detection a few
    # lines down: that now correctly detects "utf-8", matching what's
    # actually on disk, including in the copy that ends up saved as the
    # dataset's permanent file.
    normalize_text_encoding(filename)
    delimiter = find_delimiter(filename)
    first_data_row = check_header_csv(filename, delimiter)

    replaces = None
    with open(filename, "rb") as f:
        # fix lon and lat in header names
        header, replaces = fix_header(f.readline())
        if replaces or first_data_row != 2:
            if first_data_row != 2:
                f.readline()
            data_lines = f.read()
            with open(filename, "wb") as out:
                out.write(header)
                if first_data_row != 2:
                    out.write("\n".encode())
                out.write(data_lines)

    with open(filename, 'rb') as f:
        charset = chardet.detect(f.read(5000))['encoding']

    # order matches EDDTableFromAsciiFiles' interactive prompts, one arg per prompt
    args = [
        charset,
        "1",                            # column names row
        str(first_data_row),
        delimiter,                      # column separator
        str(GENERATE_DATASETS_XML_RELOAD_MINUTES),
        "", "", "", "",                 # pre/post/extract regex, column name for extract
        "",                              # sorted column source name
        "",                              # sort files by sourceNames
        infoUrl, institution, summary, title,
        "",                              # standardizeWhat
        "",                              # cacheFromUrl
    ]
    return args, replaces

def _build_args_for_multidim_nc(filename, infoUrl, institution, summary, title):
    ds = nc.Dataset(filename)
    # size-1 dimensions (e.g. a LATITUDE/LONGITUDE/DEPTH dim used only to hold a
    # single station-level value) aren't real "row" dimensions of the data: passing
    # them to GenerateDatasetsXml alongside the real one (e.g. TIME) makes it try to
    # build a multi-dimensional index across incompatible sizes and fail with
    # "NDimensionalIndex constructor: shape=[...] has a value less than 1"
    dimensions_csv = ",".join(name for name, dim in ds.dimensions.items() if dim.size > 1)

    # order matches EDDTableFromMultidimNcFiles' interactive prompts
    args = [
        dimensions_csv,
        str(GENERATE_DATASETS_XML_RELOAD_MINUTES),
        "", "", "", "",                 # pre/post/extract regex, column name for extract
        "",                              # remove missing value rows
        "",                              # sort files by sourceNames
        infoUrl, institution, summary, title,
        "",                              # standardizeWhat
        "",                              # treatDimensionsAs
        "",                              # cacheFromUrl
    ]
    return args, None

NC_DTYPE_TO_ERDDAP_TYPE = {
    'float64': 'double', 'float32': 'float',
    'int64': 'long', 'int32': 'int', 'int16': 'short', 'int8': 'byte',
    'uint64': 'long', 'uint32': 'int', 'uint16': 'short', 'uint8': 'byte',
}

def _dropped_scalar_dataVariables(filename, existing_names):
    # any variable whose only dimension is a size-1 dimension got excluded from
    # dimensionsCSV (see _build_args_for_multidim_nc) and so is missing from the
    # generated XML entirely; rebuild it here as a scalar dataVariable (sourceName
    # baked in as a literal value, like the synthetic station_id below), carrying
    # over its real NetCDF attributes - this covers any such variable (not just a
    # known set of names like latitude/longitude/depth)
    try:
        ds = nc.Dataset(filename)
    except Exception:
        return []

    size1_dims = {name for name, dim in ds.dimensions.items() if dim.size == 1}
    result = []
    for name, var in ds.variables.items():
        if name in existing_names:
            continue
        if len(var.dimensions) > 1 or (len(var.dimensions) == 1 and var.dimensions[0] not in size1_dims):
            continue
        try:
            value = var[...].reshape(-1)[0].item()
        except Exception:
            continue

        atts = [{'#text': str(getattr(var, att_name)), '@name': att_name}
                for att_name in var.ncattrs() if att_name not in ('_FillValue', 'missing_value')]

        result.append({
            'dataType': NC_DTYPE_TO_ERDDAP_TYPE.get(str(var.dtype), 'String'),
            'sourceName': f'="{value}"',
            'destinationName': name.lower(),
            'addAttributes': {'att': atts} if atts else None,
        })
    return result

def _build_args_for_grid_nc(filename):
    # order matches EDDGridFromNcFiles' interactive prompts
    args = [
        "",                              # group
        "",                              # dimensionsCSV
        str(GENERATE_DATASETS_XML_RELOAD_MINUTES),
        "",                              # cacheFromUrl
    ]
    return args, None

EDDTYPE_ARG_BUILDERS = {
    "EDDTableFromAsciiFiles": lambda filename, infoUrl, institution, summary, title:
        _build_args_for_ascii(filename, infoUrl, institution, summary, title),
    "EDDTableFromMultidimNcFiles": lambda filename, infoUrl, institution, summary, title:
        _build_args_for_multidim_nc(filename, infoUrl, institution, summary, title),
    "EDDGridFromNcFiles": lambda filename, infoUrl, institution, summary, title:
        _build_args_for_grid_nc(filename),
}

def generate_dataset_xml(filename, title, summary, institution, infoUrl, cdm_data_type, latitude=None, longitude=None, quiet=False):
    EDDType = _detect_eddtype(filename, cdm_data_type)
    type_args, replaces = EDDTYPE_ARG_BUILDERS[EDDType](filename, infoUrl, institution, summary, title)

    # GenerateDatasetsXml accepts every interactive answer as a positional command-line
    # argument (in prompt order); passing them all makes it run fully non-interactively,
    # so no pty/expect driver (pexpect) is needed - a plain subprocess call is enough.
    args = [EDDType, os.path.dirname(filename), ""] + [filename] + type_args
    quoted_args = " ".join(shlex.quote(str(a)) for a in args)
    command = (
        'cd /usr/local/tomcat/webapps/erddap/WEB-INF/; '
        'java -cp classes:../../../lib/servlet-api.jar:lib/* -Xms4000M -Xmx4000M '
        f'gov.noaa.pfel.erddap.GenerateDatasetsXml {quoted_args}'
    )

    result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)

    if not quiet:
        print(result.stdout)
        print(result.stderr)

    if "generateDatasetsXml finished successfully" not in result.stdout:
        raise Exception(f"generateDatasetsXml unknown error: {result.stdout or result.stderr}")

    with open(GENERATE_DATASETS_XML_LOG, "r") as f:
        xml_content = f.read()
    if replaces:
        # rollback column name replaces
        xml_content = rollback_replaces(xml_content, replaces)
    return xml_content
def edit_or_add_att(xml, value):
    if xml == None:
        xml = {'att': []}
    if type(xml['att']) == list:
        for j in xml['att']:
            if(j["@name"]==value["@name"]):
                j["#text"]=value["#text"]
                break
        else:
            xml['att'].append(value)
    else:
        raise Exception("unknown xml node type")
    return xml

def get_att_value(atts_node, name):
    # atts_node is a dict like {'att': [...]} (or {'att': {...}} for a single attribute), or None
    if not atts_node or "att" not in atts_node or not atts_node["att"]:
        return None
    atts = atts_node["att"]
    if type(atts) != list:
        atts = [atts]
    for att in atts:
        if att.get("@name") == name:
            return att.get("#text")
    return None

def has_cf_role(dataVariable, value="timeseries_id"):
    # a variable can carry cf_role either natively (sourceAttributes, straight from the NetCDF)
    # or because we (or a previous run) already injected it (addAttributes)
    for key in ("sourceAttributes", "addAttributes"):
        if get_att_value(dataVariable.get(key), "cf_role") == value:
            return True
    return False

def fix_generated_xml(xml, datasetID, dataset_name, cdm_data_type, creator_name,creator_email, latitude, longitude, dataset_dir, institution, infoUrl, temp_filename):
    # uncomment sourceAttributes nodes
    xml = xml.replace('<!-- sourceAttributes>', '<sourceAttributes>').replace('</sourceAttributes -->', '</sourceAttributes>')

    mydict = xmltodict.parse(xml, force_list=FORCE_LIST)

    # re-add any NetCDF variable that GenerateDatasetsXml dropped because its only
    # dimension was excluded as a size-1 "container" dim (see _build_args_for_multidim_nc)
    if mydict['dataset'].get('@type') == 'EDDTableFromMultidimNcFiles':
        existing_names = {v['destinationName'] for v in mydict['dataset']['dataVariable']}
        for dropped in _dropped_scalar_dataVariables(temp_filename, existing_names):
            mydict['dataset']['dataVariable'].append(dropped)

    mydict['dataset']['@datasetID'] = datasetID
    mydict['dataset']['fileDir'] = dataset_dir
    mydict['dataset']['@active'] = 'false'
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': cdm_data_type, '@name': 'cdm_data_type'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': creator_name, '@name': 'creator_name'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': creator_email, '@name': 'creator_email'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': "", '@name': 'creator_url'})


    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': institution, '@name': 'institution'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': infoUrl, '@name': 'infoUrl'})
    
    # set default publisher
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': os.environ['PUBLISHER_NAME'], '@name': 'publisher_name'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': "group", '@name': 'publisher_type'})
    mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': os.environ['PUBLISHER_URL'], '@name': 'publisher_url'})

    # fix sortFilesBySourceNames by column containing space, warning it breaks sorting for multiple column
    if 'sortFilesBySourceNames' in mydict['dataset'] and mydict['dataset']['sortFilesBySourceNames'] and " " in mydict['dataset']['sortFilesBySourceNames']:
        mydict['dataset']['sortFilesBySourceNames'] = f"\"{mydict['dataset']['sortFilesBySourceNames']}\""

    # with open(filename, "rb") as f:
    #     if f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']:
    #         if "latitude" not in request.form or "longitude" not in request.form:
    #             ds = nc.Dataset(filename)
    #             app.logger.info(ds.variables.keys())
    #             for variable in ["latitude", "longitude"]:
    #                 if variable not in request.form:
    #                     # qui apro l'nc e trovo la colonna che assomiglia di più a latitude che verrà usata
    #                     # nel template solo se generate_dataset_xml non è stato in grado di trovarla da solo

    #                     for column in ds.variables.keys():
    #                         if variable in column.lower():
    #                             request.form[variable] = column
    #                             break
    if cdm_data_type in ["TimeSeries", "TimeSeriesProfile"]:
        if latitude == longitude:
            if "." in latitude:
                latitude = latitude[:-1] + "0\""
            else:
                latitude = latitude[:-1] + ".0\""

        templates = {
            "station":
                {'dataType': 'String',
                'destinationName': 'station_id',
                'sourceName': f'="{dataset_name}"',
                'addAttributes': {'att': [{'#text': 'timeseries_id',
                    '@name': 'cf_role'},
                {'#text': 'Id of the station in the TimeSeries',
                '@name': 'long_name'}]}},
            "latitude":
                {'dataType': 'float',
                'destinationName': 'latitude',
                'sourceName': latitude,
                'addAttributes': 
                 {'att': [{'#text': 'latitude position of the station','@name': 'long_name'},{'#text': 'latitude',
                '@name': 'standard_name'},{'#text': 'degrees_north',
                '@name': 'units'}]             
                }},
            "longitude":
                {'dataType': 'float',
                'destinationName': 'longitude',
                'sourceName': longitude,
                'addAttributes': 
                 {'att': [{'#text': 'longitude position of the station','@name': 'long_name'},{'#text': 'longitude',
                '@name': 'standard_name'},{'#text': 'degrees_east',
                '@name': 'units'}]             
                }},
            }

        # a variable with cf_role=timeseries_id might already be present in the NetCDF
        # (e.g. a platform_id variable), regardless of its name: check by attribute, not by name,
        # to avoid injecting a second (synthetic) cf_role=timeseries_id, which ERDDAP rejects
        existing_timeseries_id_variable = None
        for dataVariable in mydict['dataset']['dataVariable']:
            if has_cf_role(dataVariable, "timeseries_id"):
                existing_timeseries_id_variable = dataVariable['destinationName']
                break

        timeseries_variables = []
        # se una di queste assomiglia a station, latitude, longitude allora mettila, altrimenti template con placeholder
        for required_column in ["station", "latitude", "longitude"]:
            if required_column == "station" and existing_timeseries_id_variable:
                timeseries_variables.append(existing_timeseries_id_variable)
                continue

            for dataVariable in mydict['dataset']['dataVariable']:
                variable = dataVariable['destinationName']

                if required_column in variable.lower():
                    if required_column == "station":
                        dataVariable['addAttributes'] = edit_or_add_att(dataVariable['addAttributes'], {'#text': 'timeseries_id', '@name': 'cf_role'})
                    timeseries_variables.append(variable)
                    break
            else:
                template = templates[required_column]
                mydict['dataset']['dataVariable'].append(template)
                timeseries_variables.append(template['destinationName'])

        timeseries_variables = ",".join(timeseries_variables)
        mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': timeseries_variables, '@name': 'cdm_timeseries_variables'})

        #aggiungere dataVariable DATETIME
        #For cdm_data_type=TimeSeriesProfile, when there is no altitude or depth variable, you MUST define the global attribute cdm_altitude_proxy.
        if cdm_data_type == "TimeSeriesProfile":
            #station_code or time as profile_id
            for dataVariable in mydict['dataset']['dataVariable']:
                if "time" in dataVariable['destinationName'].lower():
                    dataVariable['addAttributes'] = edit_or_add_att(dataVariable['addAttributes'], {'#text': "profile_id", '@name': 'cf_role'})
                    profile_variable = "time"
                    dataVariable['destinationName'] = profile_variable
                    #aggiungere se UNIX EPOCH
                    dataVariable['addAttributes'] = edit_or_add_att(dataVariable['addAttributes'], {'#text': "yyyy-MM-dd'T'HH:mm:ss", '@name': 'units'})
                    break
            else:
                raise Exception("No time column found")
            mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': profile_variable, '@name': 'cdm_profile_variables'})
            for dataVariable in mydict['dataset']['dataVariable']:
                if dataVariable['destinationName'] == "depth":
                    break
            else:
                for dataVariable in mydict['dataset']['dataVariable']:
                    if "depth" in dataVariable['destinationName'].lower():
                        if dataVariable['destinationName'] != "depth":
                            mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'@name': 'cdm_altitude_proxy','#text': dataVariable['destinationName']})
                        break
                else:
                        raise Exception("No depth column found: are you sure this is a TimeSeriesProfile dataset?")

    def filter_unique_att(atts):
        results = []
        founded = set()
        for att in atts:
            if not att["@name"] in founded:
                founded.add(att["@name"])
                results.append(att)
        return results

    def merge_source_and_add_attributes(node):
        if "sourceAttributes" in node:
            if node["sourceAttributes"] and "att" in node["sourceAttributes"]:
                if not node['addAttributes']:
                    node['addAttributes'] = {}
                node['addAttributes']["att"] = filter_unique_att(node.pop('sourceAttributes').get("att", []) + node['addAttributes'].get("att", []))
            else:
                node.pop("sourceAttributes")


    # merge sourceAttributes and addAttributes
    merge_source_and_add_attributes(mydict["dataset"])
    for dataVariable in mydict["dataset"]["dataVariable"]:
        merge_source_and_add_attributes(dataVariable)

    if "axisVariable" in mydict["dataset"]:
        for axisVariable in mydict["dataset"]["axisVariable"]:
            merge_source_and_add_attributes(axisVariable)

    if cdm_data_type == "Grid":
        with open(temp_filename, "rb") as f:
            if f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']:
                #ds.dimensions.keys() in dimensionsCSV
                if cdm_data_type=="Grid":
                    EDDType = "EDDGridFromNcFiles"
                else:        
                    EDDType = "EDDTableFromMultidimNcFiles"
                
                ds = nc.Dataset(temp_filename)
                for key, dimension in ds.dimensions.items():
                    if dimension.size == 1:
                        mydict["dataset"]["axisVariable"].append({'sourceName': key, 'destinationName': key.lower()})

    # add real low-cardinality columns (see get_low_cardinality_columns) to
    # subsetVariables, on top of whatever GenerateDatasetsXml already put there
    low_cardinality_columns = get_low_cardinality_columns(temp_filename)
    if low_cardinality_columns:
        existing_destination_names = {v['destinationName'] for v in mydict['dataset']['dataVariable']}
        current_subset = get_att_value(mydict['dataset']['addAttributes'], 'subsetVariables')
        subset_variables = [v.strip() for v in current_subset.split(',')] if current_subset else []
        for column in low_cardinality_columns:
            if column in existing_destination_names and column not in subset_variables:
                subset_variables.append(column)
        if subset_variables:
            mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': ", ".join(subset_variables), '@name': 'subsetVariables'})

    return xmltodict.unparse(mydict, pretty=True, full_document=False)
 


def split_asterisks_blocks(lines):
    results = []
    last = None
    for i, line in enumerate(lines):
        if "***" in line:
            if last != None:
                results.append("\n".join(lines[last:i]))
            last = i
    if lines and last != len(lines) - 1:
        results.append("\n".join(lines[last:]))
    return results

DASDDS_START_MARKER = "*** Starting DasDds"
# ERDDAP encodes a fixed-value sourceName into a safe column name when it logs
# it, e.g. ="45" becomes x3dx2245x22
ENCODED_FIXED_VALUE_RE = re.compile(r'"(x3d[^"]*)"')
ENCODED_CHAR_RE = re.compile(r'x([0-9a-f]{2})')
DASDDS_LOAD_FAILED_MARKER = "An error occurred while trying to load"
DUPLICATE_SOURCE_NAME_RE = re.compile(r'Duplicate column names: .* are both "(.*)"')
FIXED_VALUE_HINT = " If these are latitude and longitude, they have the same value: check the coordinates."
# (regex on a log line, title, hint): the failures a CMS user can act on, as
# observed running DasDds on broken datasets (ERDDAP 2.31.1). A {} in the title
# is the regex's first group.
KNOWN_VALIDATION_ERRORS = [
    (DUPLICATE_SOURCE_NAME_RE,
     "Two variables have the same sourceName: {}",
     "ERDDAP needs every sourceName to be different."),
    (re.compile(r'Duplicate dataVariableDestinationNames: .* are both "(.*)"'),
     "Two variables have the same destinationName: {}",
     "ERDDAP needs every destinationName to be different."),
    (re.compile(r'^(0) files found in '),
     "No data files found",
     "Upload at least one data file for this dataset."),
    (re.compile(r'No valid data files were found'),
     "No valid data files",
     "ERDDAP couldn't read any data from the files: check they aren't empty, and check columnNamesRow and firstDataRow."),
    (re.compile(r"dataVariable\[timeIndex=\d+\] isn't an EDVTime"),
     "The time variable has invalid units",
     "Check the units of the time variable: they must describe the format of the times in the file, e.g. yyyy-MM-dd'T'HH:mm:ssZ."),
    (re.compile(r'Unknown <sortFilesBySourceNames> name#\d+="(.*)"'),
     "sortFilesBySourceNames names an unknown variable: {}",
     "Use the sourceName of one of the dataset's variables."),
    (re.compile(r'"units" MUST be "m"'),
     "The altitude variable must be in meters",
     "Set its units to m, using scale_factor to convert the values if needed, or use a different destinationName."),
    (re.compile(r'SAXParseException'),
     "The XML isn't well formed",
     "The line number refers to datasets.xml, which is compiled from all datasets, so the broken XML could also be in another dataset."),
]

def trim_dasdds_startup(output):
    # everything before the marker is JVM/logback/EDStatic startup noise,
    # unrelated to the dataset being validated
    start = output.find(DASDDS_START_MARKER)
    return output[start:] if start != -1 else output

def decode_erddap_names(line):
    def decode_char(match):
        char = chr(int(match.group(1), 16))
        return char if char.isprintable() else match.group(0)

    return ENCODED_FIXED_VALUE_RE.sub(
        lambda match: f'"{ENCODED_CHAR_RE.sub(decode_char, match.group(1))}"',
        line
    )

def summarize_validation_error(output):
    # when a dataset fails to load, ERDDAP logs the cause and DasDds then
    # crashes with a NullPointerException on the missing dataset, so what
    # follows the "load failed" marker is only a consequence and the cause is
    # the last line before it. Only a failure while parsing datasets.xml reports
    # its cause after the marker. Most causes have no ERROR prefix.
    # Returns None if the log doesn't have this shape.
    lines = [l.strip() for l in output.splitlines() if l.strip()]
    marker = next((i for i, l in enumerate(lines) if DASDDS_LOAD_FAILED_MARKER in l), None)
    if marker is None:
        return None

    after = lines[marker + 1] if marker + 1 < len(lines) else ""
    if after and '"edd" is null' not in after:
        candidates = [after]
    else:
        candidates = lines[max(0, marker - 6):marker][::-1]
    if not candidates or candidates[0].startswith("at "):
        return None

    candidates = [decode_erddap_names(l) for l in candidates]
    summary = {"title": None, "line": candidates[0], "hint": None}

    for regex, title, hint in KNOWN_VALIDATION_ERRORS:
        for line in candidates:
            match = regex.search(line)
            if match:
                name = match.group(1) if regex.groups else ""
                summary.update(line=line, title=title.format(name), hint=hint)
                if regex is DUPLICATE_SOURCE_NAME_RE and name.startswith("="):
                    summary["hint"] += FIXED_VALUE_HINT
                return summary

    return summary

published_erddap_datasets_cache = None
def get_published_erddap_datasets():
    global published_erddap_datasets_cache
    if published_erddap_datasets_cache and time.time() - published_erddap_datasets_cache[0] < 2:
        return published_erddap_datasets_cache[1]
    try:
        response = urllib3.PoolManager().request('GET', f"{ERDDAP_INTERNAL_URL}/erddap/info/index.csv?page=1&itemsPerPage=1000")
        dict_reader = csv.DictReader(io.StringIO(response.data.decode()), delimiter=',')
        result = [row["Dataset ID"] for row in dict_reader]
        published_erddap_datasets_cache = (time.time(), result)
        return result
    except (KeyError, urllib3.exceptions.MaxRetryError):
        raise ConnectionError
    
# if the url is valid it returns the dataset type and id
def check_erddap_url(url):
  try:
    parsed = urllib3.util.parse_url(url)

    if parsed.scheme is None or parsed.path is None:
      return False
        
    result = re.search("^(https?://.+/erddap/(tabledap|griddap)/([\w\-]+))(?:\.html)?", parsed.url)
    if result is None:
      return False
    
    dataset_type = None

    if result.group(2) == "tabledap":
      dataset_type = "EDDTableFromErddap"
    elif result.group(2) == "griddap":
      dataset_type = "EDDGridFromErddap"

    return result.group(1), dataset_type, result.group(3)
  except ValueError:
    raise ValueError

# this function gets datasets attributes from compiled dataset directly in ERDDAP, not the XML 
def get_dataset_attribute_from_ERDDAP(datasetID, attribute):
  e = ERDDAP(server = f"{ERDDAP_INTERNAL_URL}/erddap")

  url = e.get_info_url(dataset_id=datasetID, response="csv")
  df = pd.read_csv(url)
  row = df.loc[df['Attribute Name'] == attribute ]
  
  # the attribute may not exists so try to find it the dataset, otherwise return None
  try:
      value = row['Value'].values[0]
  except:
      value = None
  
  return value


def get_dataset_standard_names_from_ERDDAP(datasetID):
  e = ERDDAP(server = f"{ERDDAP_INTERNAL_URL}/erddap")

  url = e.get_info_url(dataset_id=datasetID, response="csv") 
  df = pd.read_csv(url)
  row = df.loc[df['Attribute Name'] == 'standard_name']
  return ', '.join(row['Value'].values)

  
def send_mail(mailer, subject, message, sender, recipients):
  msg = Message(subject=subject,sender=sender,recipients=recipients)
  msg.body = message
  mailer.send(msg)