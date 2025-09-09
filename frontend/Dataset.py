import xmltodict
import utils
import datetime
import os
import stat
import subprocess
from xml.parsers.expat import ParserCreate, ExpatError, errors
from logger_config import logger

FORCE_LIST = ('axisVariable', 'dataVariable', 'att')

class Dataset:
    id = None
    title = None
    active = None
    filename = None
    type = None
    validated = None
    published = None
    created_at=None
    last_modify=None
    summary=None
    mydict=None
    latitude=None
    longitude=None
    creator_name=None
    creator_url=None
    creator_email=None
    creator_institution=None
    contributor_name=None
    contributor_email=None
    contributor_institution=None
    publisher_name=None
    publisher_url=None
    link=None
    history=None
    files_dir=None
    
    def __init__(self, filepath):
      with open(filepath, 'r') as f:
        try:
          text = f.read()
          stat = os.stat(filepath)
          create_time = stat.st_ctime
          modify_time = os.path.getmtime(filepath)
          self.mydict = xmltodict.parse(text, force_list=FORCE_LIST)

          self.id = self.mydict['dataset']['@datasetID']
          bash_command=f"stat {filepath}  -c %W"
          create_time=subprocess.check_output(["bash", "-c", bash_command], text=True)
          ts = int(create_time)
          self.created_at=datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
          self.last_modify= datetime.datetime.fromtimestamp(modify_time).strftime("%Y-%m-%d %H:%M")   
          self.filename = filepath.split("/")[-1]  

          self.type = self.mydict['dataset']['@type']
          
          if (self.mydict['dataset']['@active'] == 'true'):
            self.active = True
          
          if (self.mydict['dataset']['@active'] == 'false'):
            self.active = False

          self.link = f"{utils.ERDDAP_BASE_URL}/erddap/{self.get_dap_type()}/{self.id}"

    
          self.published = self.id in utils.get_published_erddap_datasets()
          #if (self.validated==False):
            #to DO, write on
            #self.disactive_dataset(filepath)   
        except ExpatError as err: # fail in xml parsing 
          raise

        except ConnectionError:
          self.published = "Unknown"

        if self.type.__contains__("FromErddap"):
          self.title = self.id
          self.summary = ""
          return

        # TODO
        # get latitude and longitude from variables
        #variables =  self.mydict['dataset']['dataVariable']
        #latitude_var = list(filter(lambda x: x['destinationName'] == 'latitude', variables))[0]
        #self.latitude = latitude_var['sourceName']
        if "fileDir" in self.mydict['dataset']:    
            self.files_dir = self.mydict['dataset']['fileDir']
            assert (self.files_dir.removeprefix("/datasets_data/").removesuffix("/") == self.id), f"Security hazard in {self.id} dataset: fileDir = {self.files_dir}"
        
        self.title = self._get_global_attribute('title')
        self.summary = self._get_global_attribute('summary')
        self.creator_name = self._get_global_attribute('creator_name')
        self.creator_url = self._get_global_attribute('creator_url')
        self.creator_institution = self._get_global_attribute('institution')
        self.creator_email = self._get_global_attribute('creator_email')
        self.history = self._get_global_attribute('history')
        self.cdm_data_type = self._get_global_attribute('cdm_data_type')

        self.contributor_name = self._get_global_attribute('contributor_name')
        self.contributor_email = self._get_global_attribute('contributor_email')
        self.contributor_institution = self._get_global_attribute('contributor_institution')
        
        self.publisher_name = self._get_global_attribute('publisher_name')
        self.publisher_url = self._get_global_attribute('publisher_url')
 
    def is_readable(self, user):
      return user.can_read(self.id)


    def disactive_dataset(self, filepath):
      self.mydict['dataset']['@active'] = 'false'
      self.active = False

    def get_dap_type(self):
      if self.type.__contains__("EDDTable"): 
        return "tabledap"
      if self.type.__contains__("EDDGrid"):
        return "griddap"
    
    def _get_global_attribute(self, attribute):
      dataset_attributes = self.mydict['dataset']['addAttributes']['att']
      filtered = list(filter((lambda el: "@name" in el and el['@name'] == attribute), dataset_attributes))
      if len(filtered) == 0 or "#text" not in filtered[0]:
        return ""
      
      return filtered[0]['#text']

