import os, xmltodict, subprocess
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
import pandas as pd
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

def compile_datasets_xml():
    env=os.environ 
    bash_command = "bash /datasets_xml_parts/compile_datasets_xml.sh"
    result = subprocess.run(["bash", "-c", bash_command], capture_output=True, text=True, env=env)

    output = result.stdout
    error = result.stderr

    return output, error

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