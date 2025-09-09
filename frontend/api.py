import os, xmltodict
from flask import request, send_from_directory, jsonify
from utils import *
from main import app
import multiauth
from Dataset import Dataset
from ISO19139 import ISO19139
import base64
import tempfile
import netCDF4 as nc
from datetime import datetime
import uuid
from erddapy import ERDDAP
import shutil
import requests
from pathlib import Path
from institutes import institutes_list
from logger_config import logger

@app.after_request
def after_request(response):
  if request.path == f"{URL_PATH}/api/dataset/iso19139":
    shutil.rmtree('/var/www/html/frontend/metadata')
    
  return response

## Site API

@app.route(f"{URL_PATH}/api/dataset/xml/validate")
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def validate(dataset):
    cd_output, cd_error = compile_datasets_xml()
    output, error = validate_dataset(dataset.id)

    last_error = split_asterisks_blocks(output.splitlines())[-1]
    successfully = os.stat("/erddapData/logs/DasDds.out").st_size != 0

    multiauth.set_dataset_validity(dataset.id, successfully)

    # Flask will automatically call Jsonify to trasform this dict into JSON response
    return { "output": output, "error": error, "successfully": successfully, "relevant_error": last_error} 

@app.route(f"{URL_PATH}/api/dataset/xml/save", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def save(dataset):
    filepath = xmldir+"/"+dataset.filename
    filecontent = request.json['text']

    # Append two new lines after the filecontent if not already present
    if (filecontent[-1] != '\n'):
        filecontent = filecontent + '\n\n'

    f = open(filepath, 'w')
    f.write(filecontent)
    f.close()

    multiauth.set_dataset_validity(dataset.id, False)

    return "ok"

@app.route(f"{URL_PATH}/api/dataset/reload")
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def reload(dataset):
  cd_output, cd_error = compile_datasets_xml()
  rd_output, rd_error = reload_dataset(dataset.id)

  # wait for the dataset to be actually reloaded
  time.sleep(5)

  # Flask will automatically call Jsonify to trasform this dict into JSON response
  return { 
    "compile_dataset_output": cd_output, 
    "compile_dataset_error": cd_error,
    "reload_dataset_output": rd_output,
    "reload_dataset_error": rd_error 
  } 


@app.route(f"{URL_PATH}/api/dataset/addvariable", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def addvariable(dataset):

    required=['cdm_data_type', 'title','Conventions','infoUrl','institution','summary','license']
  
    attribute_name=request.form["attribute_name"]
    attribute_value=request.form["attribute_value"]

    if attribute_name in required:
        return {"result": "error",
                    "message": "This attribute is required"
                }, 416
    else:            
        filepath = xmldir+"/"+dataset.filename  
        app.logger.info(filepath)
        with open(filepath, 'r') as f:
            text = f.read()
            mydict = dataset.mydict
            mydict['dataset']['addAttributes'] = edit_or_add_att(mydict['dataset']['addAttributes'], {'#text': attribute_value, '@name': attribute_name})
        
            text = xmltodict.unparse(mydict, pretty=True, full_document=False)

            f = open(filepath, 'w')
            f.write(text)
            f.close()     
    
        return{"result": "ok","message": "test"}

@app.route(f"{URL_PATH}/api/dataset/newfromfile", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
def dataset_create_newfromfile():
    dataset_name = clean_user_input(request.form['datasetNameInput'].strip())

    datasets_id_list = get_datasets_id_list()

    if dataset_name in datasets_id_list:
        return {"result": "error",
                 "message": "A dataset with the chosen name already exists, please choose another name."
               }, 416

    # if dataset_name == "":
    #     return {"result": "error",
    #              "message": "The dataset name cannot be empty."
    #            }, 416

    if not validate_file_extension(clean_user_input(request.files['file'].filename), app.config['UPLOAD_EXTENSIONS']):
        return { "result": "error",
                 "message": "File extension not allowed"
               }, 416


    title = request.form["title"]
    summary = request.form["summary"]
    institution = request.form["institution"]
    infoUrl = request.form["infoUrl"]
    cdm_data_type = request.form["cdm_data_type"]
    creator_email = request.form["creator_email"]
    #creator_email = multiauth.current_user.email
    creator_name = multiauth.current_user.name.title() or ""
    
    latitude = '="0.0"' if "latitude" not in request.form else f"=\"{request.form['latitude']}\"" if request.form['latitude'].replace('.','',1).replace('-','',1).isnumeric() else request.form['latitude']
    longitude = '="0.00"'if "longitude" not in request.form else f"=\"{request.form['longitude']}\"" if request.form['longitude'].replace('.','',1).replace('-','',1).isnumeric() else request.form['longitude']

    # create temp folder
    with tempfile.TemporaryDirectory() as tempdir:

        temp_filename = f"{tempdir}/{clean_user_input(request.files['file'].filename)}"
        request.files['file'].save(temp_filename)

        # generate the datasetID
        datasetID = str(uuid.uuid4())

        try:
            xml_content = generate_dataset_xml(temp_filename, title, summary, institution, infoUrl, cdm_data_type, quiet=False)
            dataset_dir = f"{datasets_data_dir}/{datasetID}/"
            xml_content = fix_generated_xml(xml_content, datasetID, dataset_name, cdm_data_type, creator_name, creator_email, latitude, longitude, dataset_dir, institution, infoUrl, temp_filename)
        except Exception as e:
          logger.exception(e)
          return {
                  "result": "error",
                  "message": str(e)
              }, 500
        

        if not os.path.exists(dataset_dir):
            os.mkdir(dataset_dir)

        filename = f"{dataset_dir}/{clean_user_input(request.files['file'].filename) }"
        
        # save the file in the dataset folder
        request.files['file'].seek(0)
        request.files['file'].save(filename)

        filepath = xmldir+"/"+datasetID+".xml"
        with open(filepath, 'w') as f:
            f.write(xml_content)
            f.write("\n\n")
                    
        if not multiauth.current_user.is_admin():
            multiauth.add_user_to_dataset(multiauth.current_user.id, datasetID)
            #send mail
            subject = 'Hello from ERDDAP CMS!'
            sender = os.environ['ERDDAP_emailSender']
            recipients = [os.environ['ERDDAP_emailEverythingTo']]
            message = f"Hey admin, user id {multiauth.current_user.id} ({multiauth.current_user.name or 'email not setted'}) just created a dataset {dataset_name} with id {datasetID}!"
            try:
              send_mail(app.mailer, subject, message, sender, recipients)
            except Exception as e:
              logger.exception(e)
        return { "result" : "ok" }

@app.route(f"{URL_PATH}/api/dataset/delete", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def dataset_delete(dataset):
    if dataset.id not in get_datasets_id_list():
        return { 
                 "result" : "error",
                 "message" : "This dataset does not exists."
               }

    if dataset.files_dir:
      # delete all files if any
      dataset_files_dir = dataset.files_dir
      if not os.path.exists(dataset_files_dir):
          return {
              "result": "error",
              "message": "The files directory does not exists on the server."
          }


      # remove all the files first
      files = get_dataset_files(dataset)
      for file in files:
          os.remove(f"{dataset_files_dir}/{file}")
      
      # remove the directory
      os.rmdir(dataset_files_dir)

    filepath = xmldir+"/"+dataset.filename

    # set dataset as inactive
    with open(filepath, 'r') as f:
        text = f.read()
        mydict = dataset.mydict
        mydict['dataset']['@active'] = "false"
        text = xmltodict.unparse(mydict, pretty=True, full_document=False)

    f = open(filepath, 'w')
    f.write(text)
    f.close()

    # flag the dataset
    compile_datasets_xml()
    reload_dataset(dataset.id)

    # remove the xml file
    os.remove(filepath)

    # recreate datasets.xml
    compile_datasets_xml()

    multiauth.delete_dataset_permissions(dataset.id)

    return {
        "result": "ok",
        "message": "dataset deleted."
    }


#TODO: Error handling
@app.route(f"{URL_PATH}/api/dataset/file/upload", methods=['PUT'])
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def dataset_file_upload(dataset):
    # the 'file' key is the HTML <input name="file"> name attibute. 
    if not validate_file_extension(clean_user_input(request.files['file'].filename), app.config['UPLOAD_EXTENSIONS']):
        return { "result": "error",
                 "message": "File extension not allowed"
               }, 416
    file = request.files['file']

    filename = clean_user_input(file.filename)
    app.logger.info(filename)
    file.save(os.path.join(dataset.files_dir, filename))
        
    return { "result": "ok" }

@app.route(f"{URL_PATH}/api/dataset/file/delete", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
@multiauth.load_and_authorize_dataset
def dataset_file_delete(dataset):
    filepath = clean_user_input(request.json['filename'])
    try:
        os.remove(os.path.join(dataset.files_dir, filepath))
    except FileNotFoundError:
        return { "result": "File not found" },404

    return { "result": "ok" }

@app.route(f"{URL_PATH}/api/users/delete", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
@multiauth.admin_required
def delete_user():
    multiauth.delete_user(request.json['id'])
    return { "result": "ok" }


@app.route(f"{URL_PATH}/api/dataset/iso19139", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
def dataset_generate_iso19139():

  filename = request.json['datasetFilename']

  # get the dataset info
  filepath = xmldir+"/"+filename
  dataset = Dataset(filepath)

  if dataset.published == False:
    return { "error" : "Dataset is not published" }, 403
  
  iso_metadata = ISO19139()

  iso_metadata.publisher_name(get_dataset_attribute_from_ERDDAP(dataset.id, 'publisher_name'))
  iso_metadata.publisher_url(get_dataset_attribute_from_ERDDAP(dataset.id, 'publisher_url'), get_dataset_attribute_from_ERDDAP(dataset.id, 'publisher_name'))

  iso_metadata.abstract(get_dataset_attribute_from_ERDDAP(dataset.id, 'summary'))
  iso_metadata.distributionFormat("ERDDAP")
  iso_metadata.dataset_creation_date(dataset.created_at)
  iso_metadata.dataset_publication_date(dataset.created_at)
  iso_metadata.title(get_dataset_attribute_from_ERDDAP(dataset.id, 'title'))
  iso_metadata.lineage(get_dataset_attribute_from_ERDDAP(dataset.id, 'history'))

  iso_metadata.metadata_creator_name(get_dataset_attribute_from_ERDDAP(dataset.id, 'creator_name'))
  iso_metadata.metadata_organization_name(get_dataset_attribute_from_ERDDAP(dataset.id, 'institution'))
  iso_metadata.metadata_creator_email(get_dataset_attribute_from_ERDDAP(dataset.id, 'creator_email'))

  iso_metadata.PIfullname(get_dataset_attribute_from_ERDDAP(dataset.id, 'creator_name'))
  iso_metadata.PIemail(get_dataset_attribute_from_ERDDAP(dataset.id, 'creator_email'))
  iso_metadata.PIorganisation(get_dataset_attribute_from_ERDDAP(dataset.id, 'institution'))

  iso_metadata.PoCfullname(get_dataset_attribute_from_ERDDAP(dataset.id, 'contributor_name'))
  iso_metadata.PoCemail(get_dataset_attribute_from_ERDDAP(dataset.id, 'contributor_email'))
  iso_metadata.PoCorganisation(get_dataset_attribute_from_ERDDAP(dataset.id, 'contributor_institution'))

  iso_metadata.add_link(iso_metadata.link, Protocol.webaddress.value, "Landing page", "Metadata landing page")
  iso_metadata.add_link(dataset.link, Protocol.opendap.value, "OPeNDAP URL", "Link to OPeNDAP URL")
  iso_metadata.add_link(dataset.link+".csv", Protocol.download.value, "Direct download", "Download a CSV version")
  iso_metadata.add_link(dataset.link+".nc", Protocol.download.value, "Direct download", "Download a NetCDF version")

  lat_max = get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lat_max')
  lat_min = get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lat_min')
  lon_max = get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lon_max')
  lon_min = get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lon_min')

  iso_metadata.north_bound_latitude(get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lat') if lat_max is None else lat_max) 
  iso_metadata.south_bound_latitude(get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lat') if lat_min is None else lat_min)
  iso_metadata.west_bound_longitude(get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lon') if lon_max is None else lon_max)
  iso_metadata.east_bound_longitude(get_dataset_attribute_from_ERDDAP(dataset.id, 'geospatial_lon') if lon_min is None else lon_min)

  iso_metadata.begin_time_period(get_dataset_attribute_from_ERDDAP(dataset.id, 'time_coverage_start'))
  iso_metadata.end_time_period(get_dataset_attribute_from_ERDDAP(dataset.id, 'time_coverage_end'))

  iso_metadata.keywords_freetext(get_dataset_standard_names_from_ERDDAP(dataset.id))
  
  iso_metadata.generateXML(dataset.id)

  return send_from_directory("/var/www/html/frontend/metadata", f"{dataset.id}.xml", as_attachment=True)

@app.route(f"{URL_PATH}/api/dataset/newfromerddap", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
def dataset_create_newfromerddap():

  # get the dataset url
  datasetURL = request.json['datasetURL']

  # check the url
  try:
    url, dataset_type, datasetID = check_erddap_url(datasetURL)
  except:
    return { "result": "error",
             "message": "The url provided is not a valid ERDDAP dataset url."}, 400

  filepath = '/var/www/html/frontend/static/xml/fromerddap_template.xml'
  datasetID = f"{datasetID}"

  with open(filepath, 'r') as f:
    text = f.read()
    xmldict = xmltodict.parse(text)
    xmldict["dataset"]["@datasetID"] = datasetID
    xmldict["dataset"]["sourceUrl"] = url
    xmldict["dataset"]["@type"] = dataset_type

    text = xmltodict.unparse(xmldict, pretty=True, full_document=False)
    f = open(f'{xmldir}/{datasetID}.xml', 'w')
    f.write(text)
    f.write("\n\n")
    f.close()

  return { "result": "ok" } 

@app.route(f"{URL_PATH}/api/dataset/downloadnc", methods=['POST'])
@multiauth.login_required
@multiauth.active_required
def dataset_downloadnc():

  nc_url = request.json['link']
  id = request.json['id']
  filename = f"{id}.nc"

  response = requests.get(nc_url)
  if response.status_code == 200:  # Check if the request was successful
    Path("/var/www/html/frontend/static/nc").mkdir(parents=True, exist_ok=True)
    with open(f'/var/www/html/frontend/static/nc/{filename}', 'wb') as file:
      file.write(response.content)
      print(f"Downloaded {filename} successfully.")
  else:
      print("Failed to download the file.")
    
  return { "link" : f"{request.host_url}{URL_PATH.strip('/')}/nc/{filename}" }

@app.route(f"{URL_PATH}/api/data/search")
def search_data():
    data=institutes_list
    query = request.args.get('q', '').lower()  # Get search query from URL parameters
    # Filter results based on query (searching in both keys and values)
    results = {key: value for key, value in data.items() if query in key.lower() or query in value.lower()}
    return jsonify(results) 

