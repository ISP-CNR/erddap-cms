import os, xmltodict, subprocess
from this import d
from os import listdir
from os.path import isfile, join
from Dataset import Dataset, FORCE_LIST
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import csv
import pexpect
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

def generate_dataset_xml(filename, title, summary, institution, infoUrl, cdm_data_type, latitude=None, longitude=None, quiet=False):
    replaces = None
    child = pexpect.spawn('bash -c "cd /usr/local/tomcat/webapps/erddap/WEB-INF/; java -cp classes:../../../lib/servlet-api.jar:lib/* -Xms1000M -Xmx1000M gov.noaa.pfel.erddap.GenerateDatasetsXml"')

    regexp = ""
    
    #csv
    columnNameRow = 1
    firstDataRow = 2
    #grid
    group = ""
    #NC
    dimensionsCSV = ""
    missing=""

    ReloadEveryNMinutes = 10080
    PreExtractRegex = ""
    PostExtractRegex = ""
    ExtractRegex = ""
    columnExtract = ""
    sortedColumnName = ""
    sortedFiles = ""
    standardizeWhat = ""
    cacheFromUrl = ""
    treatDimensionsAs = ""
    with open(filename, "rb") as f:
        if f.read(4) in [b'\x89HDF', b'CDF\x01', b'CDF\x02']:
            #ds.dimensions.keys() in dimensionsCSV
            if cdm_data_type=="Grid":
                EDDType = "EDDGridFromNcFiles"
            else:        
                EDDType = "EDDTableFromMultidimNcFiles"
            
            ds = nc.Dataset(filename)
            dimensionsCSV = ",".join(list(ds.dimensions.keys()))
        else:
            EDDType = "EDDTableFromAsciiFiles"
            delimiter=find_delimiter(filename)
            firstDataRow = check_header_csv(filename,delimiter)
            
            f.seek(0)
            # fix lon and lat in header names
            header, replaces = fix_header(f.readline())
            if replaces or firstDataRow != 2:
                if firstDataRow != 2:
                    skip_line = f.readline()
                data_lines = f.read()
                with open(filename, "wb") as out:
                    out.write(header)
                    if firstDataRow != 2:
                        out.write("\n".encode())
                    out.write(data_lines)
    
    if not quiet:
        child.logfile = sys.stdout.buffer

    child.expect('Which EDDType')
    child.sendline(EDDType)

    child.expect(' directory')
    child.sendline(os.path.dirname(filename))

    child.expect('File name regex')
    child.sendline(regexp)

    child.expect('Full file name of one file')
    child.sendline(filename)

    if EDDType == "EDDTableFromMultidimNcFiles" or EDDType=="EDDGridFromNcFiles":
        if EDDType=="EDDGridFromNcFiles":
            child.expect('Group')
            child.sendline(group)

        child.expect('DimensionsCSV')
        child.sendline("" if EDDType=="EDDGridFromNcFiles" else dimensionsCSV)

        child.expect('ReloadEveryNMinutes')
        child.sendline(str(ReloadEveryNMinutes))

        if EDDType == "EDDTableFromMultidimNcFiles":
            child.expect('PreExtractRegex')
            child.sendline(PreExtractRegex)

            child.expect('PostExtractRegex')
            child.sendline(PostExtractRegex)

            child.expect('ExtractRegex')
            child.sendline(ExtractRegex)

            child.expect('Column name for extract')
            child.sendline(columnExtract)

            #ONLY IF NC
            child.expect('Remove missing value rows')
            child.sendline(missing)
            #ONLY IF NC
            child.expect('Sort files by sourceNames')
            child.sendline(sortedFiles)

            #ONLY IF NC
            child.expect('infoUrl')
            child.sendline(infoUrl)
            #ONLY IF NC
            child.expect('institution')
            child.sendline(institution)
            #ONLY IF NC
            child.expect('summary')
            child.sendline(summary)
            #ONLY IF NC
            child.expect('title')
            child.sendline(title)
            #ONLY IF NC
            child.expect('standardizeWhat')
            child.sendline(standardizeWhat)
            #ONLY IF NC
            child.expect('treatDimensionsAs')
            child.sendline("")

        child.expect('cacheFromUrl')
        child.sendline(cacheFromUrl)

    else:

        child.expect('Charset')
        with open(filename, 'rb') as file:
            child.sendline(chardet.detect(file.read(5000))['encoding'])
            # child.sendline("")

        child.expect('Column names row')
        child.sendline(str(columnNameRow))

        child.expect('First data row')
        child.sendline(str(firstDataRow))
        
        child.expect('Column separator')
        child.sendline(delimiter)

        child.expect('ReloadEveryNMinutes')
        child.sendline(str(ReloadEveryNMinutes)) 

        child.expect('PreExtractRegex')
        child.sendline(PreExtractRegex)

        child.expect('PostExtractRegex')
        child.sendline(PostExtractRegex)

        child.expect('ExtractRegex')
        child.sendline(ExtractRegex)

        child.expect('Column name for extract')
        child.sendline(columnExtract)

        
        child.expect('Sorted column source name')
        child.sendline(sortedColumnName)

        child.expect('Sort files by sourceNames')
        child.sendline(sortedFiles)

        child.expect('infoUrl')
        child.sendline(infoUrl)

        child.expect('institution')
        child.sendline(institution)

        child.expect('summary')
        child.sendline(summary)

        child.expect('title')
        child.sendline(title)
        
        child.expect('standardizeWhat')
        child.sendline(standardizeWhat)

        child.expect('cacheFromUrl')
        child.sendline(cacheFromUrl)

    if child.expect(["/erddapData/logs/GenerateDatasetsXml.out", "generateDatasetsXml finished successfully"]):
        child.expect('/erddapData/logs/GenerateDatasetsXml.out')
        child.logfile = None
        child.close()
        with open("/erddapData/logs/GenerateDatasetsXml.out", "r") as f:
            xml_content = f.read()
            if replaces:
                # rollback column name replaces
                xml_content = rollback_replaces(xml_content, replaces)
            return xml_content
    else:
        child.logfile = None
        print(child.after.decode('utf-8', errors='ignore'))
        child.close()
        raise Exception("generateDatasetsXml unknown error")
    # child.interact()

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

def fix_generated_xml(xml, datasetID, dataset_name, cdm_data_type, creator_name,creator_email, latitude, longitude, dataset_dir, institution, infoUrl, temp_filename):
    # uncomment sourceAttributes nodes
    xml = xml.replace('<!-- sourceAttributes>', '<sourceAttributes>').replace('</sourceAttributes -->', '</sourceAttributes>')

    mydict = xmltodict.parse(xml, force_list=FORCE_LIST)
    
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

        timeseries_variables = []
        # se una di queste assomiglia a station, latitude, longitude allora mettila, altrimenti template con placeholder
        for required_column in ["station", "latitude", "longitude"]:
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

    return xmltodict.unparse(mydict, pretty=True, full_document=False)
 


def split_asterisks_blocks(lines):
    results = []
    last = None
    for i, line in enumerate(lines):
        if "***" in line:
            if last != None:
                results.append("\n".join(lines[last:i]))
            last = i
    if last != i:
        results.append("\n".join(lines[last:i]))
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