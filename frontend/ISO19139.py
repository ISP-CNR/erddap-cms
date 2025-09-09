import xmltodict
import uuid
import datetime
from pathlib import Path
import os

filepath = '/var/www/html/frontend/static/xml/iso19139.xml'

class ISO19139:
  mydict = None
  id = None
  geonetwork_url = None
  link = None

  def __init__(self):
    iso8601timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
    self.id = str(uuid.uuid4())
    self.geonetwork_url = os.environ['GEONETWORK_URL']
    self.link = f"{self.geonetwork_url}/srv/api/records/{self.id}"
    with open(filepath, 'r') as f:
      text = f.read()
      self.mydict = xmltodict.parse(text)
      self.mydict["gmd:MD_Metadata"]["gmd:fileIdentifier"]["gco:CharacterString"] = self.id
      self.mydict["gmd:MD_Metadata"]["gmd:dateStamp"]["gco:DateTime"] = iso8601timestamp
      self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:citation"]["gmd:CI_Citation"]["gmd:identifier"]["gmd:MD_Identifier"]["gmd:code"]["gco:CharacterString"] = self.link
  
  def metadata_creator_name(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:contact"]["gmd:CI_ResponsibleParty"]["gmd:individualName"]["gco:CharacterString"] = value

  def metadata_organization_name(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:contact"]["gmd:CI_ResponsibleParty"]["gmd:organisationName"]["gco:CharacterString"] = value

  def metadata_creator_email(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:contact"]["gmd:CI_ResponsibleParty"]["gmd:contactInfo"]["gmd:CI_Contact"]["gmd:address"]["gmd:CI_Address"]["gmd:electronicMailAddress"]["gco:CharacterString"] = value

  def title(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:citation"]["gmd:CI_Citation"]["gmd:title"]["gco:CharacterString"] = value
  
  def dataset_creation_date(self,value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:citation"]["gmd:CI_Citation"]["gmd:date"][0]["gmd:CI_Date"]["gmd:date"]["gco:Date"] = value

  # needed for DOI request
  def dataset_publication_date(self,value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:citation"]["gmd:CI_Citation"]["gmd:date"][1]["gmd:CI_Date"]["gmd:date"]["gco:Date"] = value

  def abstract(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:abstract"]["gco:CharacterString"] = value

  def purpose(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:purpose"]["gco:CharacterString"] = value

  def PIfullname(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][0]["gmd:CI_ResponsibleParty"]["gmd:individualName"]["gco:CharacterString"] = value

  def PIorganisation(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][0]["gmd:CI_ResponsibleParty"]["gmd:organisationName"]["gco:CharacterString"] = value

  def PIemail(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][0]["gmd:CI_ResponsibleParty"]["gmd:contactInfo"]["gmd:CI_Contact"]["gmd:address"]["gmd:CI_Address"]["gmd:electronicMailAddress"]["gco:CharacterString"] = value

  def PoCfullname(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][1]["gmd:CI_ResponsibleParty"]["gmd:individualName"]["gco:CharacterString"] = value

  def PoCorganisation(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][1]["gmd:CI_ResponsibleParty"]["gmd:organisationName"]["gco:CharacterString"] = value

  def PoCemail(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:pointOfContact"][1]["gmd:CI_ResponsibleParty"]["gmd:contactInfo"]["gmd:CI_Contact"]["gmd:address"]["gmd:CI_Address"]["gmd:electronicMailAddress"]["gco:CharacterString"] = value

  def west_bound_longitude(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:geographicElement"]["gmd:EX_GeographicBoundingBox"]["gmd:westBoundLongitude"]["gco:Decimal"] = value

  def east_bound_longitude(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:geographicElement"]["gmd:EX_GeographicBoundingBox"]["gmd:eastBoundLongitude"]["gco:Decimal"] = value

  def north_bound_latitude(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:geographicElement"]["gmd:EX_GeographicBoundingBox"]["gmd:northBoundLatitude"]["gco:Decimal"] = value

  def south_bound_latitude(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:geographicElement"]["gmd:EX_GeographicBoundingBox"]["gmd:southBoundLatitude"]["gco:Decimal"] = value

  def distributionFormat(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"]["gmd:distributionFormat"]["gmd:MD_Format"]["gmd:name"]["gco:CharacterString"] = value

  def publisher_name(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"]["gmd:distributor"]["gmd:MD_Distributor"]["gmd:distributorContact"]["gmd:CI_ResponsibleParty"]["gmd:organisationName"]["gco:CharacterString"] = value

  def publisher_url(self, url, url_name):
    self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"]["gmd:distributor"]["gmd:MD_Distributor"]["gmd:distributorContact"]["gmd:CI_ResponsibleParty"]["gmd:contactInfo"]["gmd:CI_Contact"]["gmd:onlineResource"]["gmd:CI_OnlineResource"]["gmd:linkage"]["gmd:URL"] = url
    self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"]["gmd:distributor"]["gmd:MD_Distributor"]["gmd:distributorContact"]["gmd:CI_ResponsibleParty"]["gmd:contactInfo"]["gmd:CI_Contact"]["gmd:onlineResource"]["gmd:CI_OnlineResource"]["gmd:name"]["gco:CharacterString"] = url_name

  def lineage(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:dataQualityInfo"]["gmd:DQ_DataQuality"]["gmd:lineage"]["gmd:LI_Lineage"]["gmd:statement"]["gco:CharacterString"] = value

  def begin_time_period(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:temporalElement"]["gmd:EX_TemporalExtent"]["gmd:extent"]["gml:TimePeriod"]["gml:beginPosition"] = value
  
  def end_time_period(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:extent"]["gmd:EX_Extent"]["gmd:temporalElement"]["gmd:EX_TemporalExtent"]["gmd:extent"]["gml:TimePeriod"]["gml:endPosition"] = value

  def add_link(self, link=None, protocol=None, name=None, description=None):
    if "gmd:transferOptions" not in self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"].keys():
      self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"].update({"gmd:transferOptions": {"gmd:MD_DigitalTransferOptions" : [] }})
    
    self.mydict["gmd:MD_Metadata"]["gmd:distributionInfo"]["gmd:MD_Distribution"]["gmd:transferOptions"]["gmd:MD_DigitalTransferOptions"].append({
      "gmd:onLine" : {
        "gmd:CI_OnlineResource" : {
          "gmd:linkage" : { "gmd:URL" : link },
          "gmd:protocol" : { "gco:CharacterString" : protocol },
          "gmd:name" : { "gco:CharacterString" :  name },
          "gmd:description" : { "gco:CharacterString" :  description }
        }
      }
    })

  def keywords_freetext(self, value):
    self.mydict["gmd:MD_Metadata"]["gmd:identificationInfo"]["gmd:MD_DataIdentification"]["gmd:descriptiveKeywords"]["gmd:MD_Keywords"]["gmd:keyword"]["gco:CharacterString"] = value


  def generateXML(self, filename):
    text = xmltodict.unparse(self.mydict, pretty=True, full_document=False)
    Path('/var/www/html/frontend/metadata').mkdir(parents=False, exist_ok=True)
    f = open(f'/var/www/html/frontend/metadata/{filename}.xml', 'w')
    f.write(text)
    f.close()