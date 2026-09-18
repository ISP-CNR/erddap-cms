var textArea = document.getElementById('editor');

// textArea is null when XML tab is not shown (user view)
if(textArea) {
  var myCodeMirror = CodeMirror.fromTextArea(textArea, {
    lineNumbers: true
  });
  
  // to fix code mirror not showing up until clicked
  var tabEl = document.querySelector('#nav-xml-tab')
  tabEl.addEventListener('shown.bs.tab', function (event) {
    myCodeMirror.refresh();
  })
}

// get the dataset metadata as a JS object
const datasetObj = dataset;

function save(id) {

  var tabEl = document.querySelector('button[data-bs-toggle="tab"].active');

  // tabEl is null in user view.
  if(tabEl == null || tabEl.id == 'nav-form-tab') {
    // check form validity
    var form = document.getElementById("datasetForm");
    if (form.checkValidity() === false){
        form.reportValidity();   
        return; 
    }
    let xml = generateXMLfromForm();

    fetch(`${URL_PATH}/api/dataset/xml/save?id=${id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text : xml })
    })
    .then(response => {
      original_xml = xml;
      location.reload(true);
    });
  }

  if(tabEl != null && tabEl.id == 'nav-xml-tab') {
    fetch(`${URL_PATH}/api/dataset/xml/save?id=${id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text : myCodeMirror.getValue() })
    })
    .then(response => {
      location.reload(true);
    });
  }
}

function check_pending_changes() {
  if (original_xml != generateXMLfromForm()){
    alert("There are unsaved changes, save or discard the changes before continuing");
    return true;
  }
  return false;
}

function validate(id) {
  if (check_pending_changes()){
    return
  }

  var myModal = new bootstrap.Modal(document.getElementById('staticBackdrop'));
  myModal.show();

  var spinner = document.getElementById("spinner");
  var modalRelevant = document.getElementById("modal-relevant");
  var modalText = document.getElementById("modal-text");
  var modalResult = document.getElementById("validation-result");
  var modalAccordion = document.getElementById("logsAccordion");
  modalRelevant.innerText = "";
  modalText.innerText = "";
  modalResult.innerText = "";
  modalAccordion.classList.add("visually-hidden");

  fetch(`${URL_PATH}/api/dataset/xml/validate?id=${id}`)
  .then(response => response.json())
  .then(data => {
    spinner.classList.add("visually-hidden");
    modalRelevant.innerText = data.relevant_error;
    modalText.innerText = data.output;
    modalResult.innerText = data.successfully ? "OK": "Fail";
    modalAccordion.classList.remove("visually-hidden");
    if (data.successfully){
      modalResult.classList.add("bg-success");
      modalResult.classList.remove("bg-danger");
    }else{
      modalResult.classList.remove("bg-success");
      modalResult.classList.add("bg-danger");
    }
  });
}

function reload(button,id) {
  if (check_pending_changes()){
    return
  }

  // disable button until dataset is published or reloaded
  button.disabled = true;
  
  document.getElementById('action-button-spinner').classList.remove('hide');
  document.getElementById('action-button-text').classList.add('hide');

  fetch(`${URL_PATH}/api/dataset/reload?id=${id}`)
  .then(response => response.json())
  .then(data => {
    document.getElementById('action-button-spinner').classList.add('hide');
    document.getElementById('action-button-text').classList.remove('hide');
    button.disabled = false;
    location.reload(true);
  });
}

function closeValidateModal(){
  var spinner = document.getElementById("spinner");
  var modalText = document.getElementById("modal-text");

  spinner.classList.remove("visually-hidden");
  modalText.innerText = "";
  location.reload(true);
}

// returns an Object where each key-value pairs are the common attribute and an array of the elements which have the attribute.
function groupElementsByCommonAttribute(elements, attribute) {
 
  const groupedElements = {};

  elements.forEach(el => {
    if(el.hasAttribute(attribute)) {
      const attr = el.getAttribute(attribute);

      // check if an array for this attribute value already exists
      if(!groupedElements[attr]) {
        groupedElements[attr] = [];
      }

      groupedElements[attr].push(el)
    }
  });

  return groupedElements;
}


function getDataVariablesForXML(dataVariables) { //dataVariables is an object

  let newDataVariables = {};
  
  Object.keys(dataVariables).forEach(key => {
    
    let tempArray = dataVariables[key];
    let tempObject = {};

    tempArray.forEach(x => {
      tempObject[x.name] = x.value;
    });

    newDataVariables[key] = tempObject;
  });

  return newDataVariables;
}


function getDataVarAttrObjectForXML(dataVarAttributes) { //dataVarAttributes is an object
  let newDataVarAttributes = {};

  Object.keys(dataVarAttributes).forEach(key => {
    
    let tempArray = dataVarAttributes[key];
    //skip empty field before save
    tempArray = tempArray.filter(x =>  x.value !== "").map(x => { return { "att": { "@name" : x.name , "#" : x.value }}}); //.filter(x =>  x.name !== "")
    let tempObject = { '#' : tempArray }

    newDataVarAttributes[key] = tempObject;
  });

  return newDataVarAttributes;
}

function generateXMLfromForm() {

  let globalInputs = document.querySelectorAll("[id^='global_']:is(input, select):not(.deleted_field)")
  let dataVarInputs = document.querySelectorAll("[id^='var_']:not(.deleted_field)");
  let dataVarAttributesInputs = document.querySelectorAll("[id^='varattr_']:not(.deleted_field)");

  let axisVarInputs = document.querySelectorAll("[id^='axis_var_']:not(.deleted_field)");
  let dataxisVarAttributesInputs = document.querySelectorAll("[id^='axis_varattr_']:not(.deleted_field)");

  // get JSobject version of the dataset xml file and updated the values with the form
  let data = datasetObj;

  if(data.dataset['@type'].includes("FromErddap")) {
    data.dataset.sourceUrl = document.getElementById('global_sourceUrl').value;
    const datasetXML = toXML(data, null, 2);
    return datasetXML;
  }
  
  data.dataset.addAttributes = { "#": [] };
  data.dataset.dataVariable = [];
  data.dataset.axisVariable = [];

  // default roles used when the "Accessible to" field is left empty (it's
  // admin-only - see edit.html - so this is always what a non-admin gets):
  // a role unique to this dataset (so one person's access doesn't leak into
  // every other private dataset) plus the standing ADMIN role that can
  // always see every private dataset. An admin still has to assign the
  // per-dataset role (or ADMIN) to an ERDDAP user for it to grant access.
  const DEFAULT_PRIVATE_ROLES = `PRIVATE_${data.dataset['@datasetID']},ADMIN`;

  const privateSwitch = document.getElementById('privateDatasetSwitch');
  if (privateSwitch && privateSwitch.checked) {
    const rolesInput = document.getElementById('accessibleTo');
    const roles = rolesInput ? rolesInput.value.trim() : '';
    data.dataset.accessibleTo = roles || DEFAULT_PRIVATE_ROLES;

    // default: graphs/metadata stay public, only the raw data requires login
    // (matches how private datasets are normally set up - see IADC's own
    // datasets, e.g. graphsAccessibleTo=public alongside accessibleTo).
    // Admins can still opt out via the checkbox to lock down everything.
    const graphsCheckbox = document.getElementById('graphsAccessibleTo');
    if (graphsCheckbox && !graphsCheckbox.checked) {
      delete data.dataset.graphsAccessibleTo;
    } else {
      data.dataset.graphsAccessibleTo = "public";
    }
  } else {
    delete data.dataset.accessibleTo;
    delete data.dataset.graphsAccessibleTo;
  }

  // note the restriction in the ACDD "license" global attribute too (the
  // conventional NC_GLOBAL attribute for access/distribution constraints -
  // there's no separate standard attribute for this), so it's visible to
  // anyone reading the dataset's own metadata, not just via ERDDAP's
  // accessibleTo mechanism. Strip it first so toggling private on/off
  // repeatedly doesn't pile up duplicate notes.
  const LICENSE_EMBARGO_NOTE = " | Data access restricted (embargo) - contact the point of contact to request access.";
  const licenseInput = document.getElementById('global_license');
  if (licenseInput) {
    let license = licenseInput.value;
    if (license.endsWith(LICENSE_EMBARGO_NOTE)) {
      license = license.slice(0, -LICENSE_EMBARGO_NOTE.length);
    }
    if (privateSwitch && privateSwitch.checked) {
      license += LICENSE_EMBARGO_NOTE;
    }
    licenseInput.value = license;
  }

  const dataVariables = groupElementsByCommonAttribute(dataVarInputs, 'data-varnum');
  const dataVarAttributes = groupElementsByCommonAttribute(dataVarAttributesInputs, 'data-varnum');

  const axisVariables = groupElementsByCommonAttribute(axisVarInputs, 'data-varnum');
  const axisVarAttributes = groupElementsByCommonAttribute(dataxisVarAttributesInputs, 'data-varnum');

  const newDataVariables = getDataVariablesForXML(dataVariables);
  const newDataVarAttributes = getDataVarAttrObjectForXML(dataVarAttributes);

  const newAxisVariables = getDataVariablesForXML(axisVariables);
  const newAxisVarAttributes = getDataVarAttrObjectForXML(axisVarAttributes);

  globalInputs.forEach(el => {
    // global attributes
    if (el.value != "") {
      const value = el.multiple
        ? Array.from(el.selectedOptions)
            .map(option => option.value)
            .join(";")
        : el.value;
  
      const globalAttr = {
        "att": {
          "@name": el.name,
          "#": value
        }
      };
  
      data.dataset.addAttributes['#'].push(globalAttr);
    }
  });

  // compose the final newDataVariables JS object for XML transformation
  Object.keys(newDataVariables).forEach(key => {
    newDataVariables[key]['addAttributes'] = newDataVarAttributes[key];
  });

  // push everything into the data.dataVariable array
  Object.keys(newDataVariables).forEach(key => {
    data.dataset.dataVariable.push(newDataVariables[key]);
  });

  // compose the final newAxisVariables JS object for XML transformation
  Object.keys(newAxisVariables).forEach(key => {
    newAxisVariables[key]['addAttributes'] = newAxisVarAttributes[key];
  });

  // push everything into the data.axisVariable array
  Object.keys(newAxisVariables).forEach(key => {
    data.dataset.axisVariable.push(newAxisVariables[key]);
  });

  const datasetXML = toXML(data, null, 2);

  return datasetXML;
}


function resetIfInvalid(el,rowID){

  var options = el.list.options;
  var found=false;

  for (var i = 0; i< options.length; i++) {
    if (el.value == options[i].value){
      found=true;
      break;
    }
  }

  var prefix = el.id.startsWith("axis_varattr_") ? "axis_varattr_" : "varattr_";
  var unitsFieldId = prefix+rowID+"units";

  if (found==true){
    document.getElementById(unitsFieldId).value = document.getElementById('standard_name_Options').options.namedItem(el.value).getAttribute('data-name');
    add_field(unitsFieldId);
  }else{
    document.getElementById(unitsFieldId).value ="";
    document.getElementById(unitsFieldId).removeAttribute('readonly');
    delete_field(unitsFieldId);
  }
}

document.addEventListener("DOMContentLoaded", function() {
  original_xml = generateXMLfromForm();
});

window.onbeforeunload = function(){
  if (original_xml != generateXMLfromForm()){
    return 'There are unsaved changes, are you sure you want to leave?';
  }
};

function delete_field(field){
  document.getElementById(field+"_label").classList.add("deleted_field");
  document.getElementById(field).classList.add("deleted_field");
  document.getElementById(field).disabled = true;
  document.getElementById(field+"_delete").classList.add("d-none");
  document.getElementById(field+"_add").classList.remove("d-none");
}

function add_field(field){
  document.getElementById(field+"_label").classList.remove("deleted_field");
  document.getElementById(field).classList.remove("deleted_field");
  document.getElementById(field).disabled = false;
  document.getElementById(field+"_add").classList.add("d-none");
  document.getElementById(field+"_delete").classList.remove("d-none");
}

function add_custom_field(event){
  var form = document.getElementById("add_custom_field");
  if (form.checkValidity() === false){
      form.reportValidity();   
      return; 
  }
  var name = document.getElementById("add_custom_field_name").value;
  template = document.getElementById("global_field_template");
  let clone = document.createElement('span');
  clone.innerHTML = template.innerHTML.replaceAll("empty", name);
  template.before(clone);
  document.getElementById("add_custom_field_name").value = ""
  return false;
}

function enableDataset(input, id) {
  let data = datasetObj;
  
  data.dataset['@active'] = input.checked;

  const xml = toXML(data, null, 2);

  fetch(`${URL_PATH}/api/dataset/xml/save?id=${id}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ text : xml })
  })
  .then(response => {
    original_xml = xml;
    location.reload(true);
  });
}

function generateOpendapUrl(id, link) {
  // get the ERDDAP netcdf file
  nc_url = `${link}.nc`

  let anchor = document.getElementById('nc_url');
  let spinner = new Spinner(document.getElementById('nc_url_spinner'));
  
  // prepare UI
  spinner.show();
  anchor.href = null;
  anchor.innerHTML = null;

  // download it on the server
  fetch(`${URL_PATH}/api/dataset/downloadnc`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ 'id' : id ,
                           'link' : nc_url })
  })
  .then(response => response.json())
  .then(data => {
    spinner.hide();
    anchor.href = data.link;
    anchor.innerHTML = data.link;
  });
}



// tooltips
setTooltipMessage('cdm_data_type', 
  "cdm_data_type (from the <a href='https://wiki.esipfed.org/Attribute_Convention_for_Data_Discovery_1-3' target='_blank'>ACDD metadata standard</a>) is a global attribute that indicates the Unidata Common Data Model data type for the dataset.");

setTooltipMessage('Conventions',
  "Conventions is a comma-separated list of metadata standards that this dataset follows.",);

setTooltipMessage('creator_name',
  "creator_name (from the ACDD metadata standard) is the recommended way to identify the person, organization, or project (if not a specific person or organization), most responsible for the creation (or most recent reprocessing) of this data.");

setTooltipMessage('creator_url',
  "creator_url (from the ACDD metadata standard) is the recommended way to identify a URL for organization that created the dataset, or a URL with the creator's information about this dataset.");

setTooltipMessage('infoUrl',
  "infoUrl is a <b>required</b> global attribute with the URL of a web page with more information about this dataset (usually at the source institution's website).");

setTooltipMessage('institution',
  "institution (from the CF and ACDD metadata standards) is a <b>required</b> global attribute with the short version of the name of the institution which is the source of this data (usually an acronym, usually <20 characters).");

setTooltipMessage('keywords',
  "keywords (from the ACDD metadata standard) is a recommended comma-separated list of words and short phrases (for example, GCMD Science Keywords) that describe the dataset in a general way, and not assuming any other knowledge of the dataset (for example, for oceanographic data, include ocean).");

setTooltipMessage('summary',
  'summary (from the CF and ACDD metadata standards) is a <b>required</b> global attribute with a long description of the dataset (usually < 500 characters). Summary is very important because it allows clients to read a description of the dataset that has more information than the title and thus quickly understand what the dataset is.');

setTooltipMessage('title',
  'title (from the CF and ACDD metadata standards) is a <b>required</b> global attribute with the short description of the dataset (usually <=95 characters).');

setTooltipMessage('creator_email',
  'creator_email (from the ACDD metadata standard) is the <b>required</b> way to identify an email address (correctly formatted) that provides a way to contact the creator.');

setTooltipMessage('publisher_name',
"publisher_name (from the ACDD metadata standard) is the <b>required</b> way to identify the person, organization, or project which is publishing this dataset. Compared to creator_name, the publisher probably didn't significantly modify or reprocess the data; the publisher is just making the data available in a new venue.");

setTooltipMessage('publisher_email',
'publisher_email (from the ACDD metadata standard) is the <b>required</b> way to identify an email address (correctly formatted) that provides a way to contact the publisher.');

setTooltipMessage('publisher_institution',
'publisher_institution (from the ACDD metadata standard) is a <b>required</b> global attribute with the short version of the name of the publisher institution (usually an acronym, usually <20 characters).');

setTooltipMessage('history',
'history (from the ACDD metadata standard) is a <b>required</b> multi-line String global attribute with a line for every processing step that the data has undergone. Ideally, each line has an ISO 8601:2004(E) formatted date+timeZ (for example, 2011-08-05T08:55:02Z) followed by a description of the processing step.');

setTooltipMessage('contributor_name',
'contributor_name (from the ACDD metadata standard) is the <b>required</b> way to identify a person, organization, or project which contributed to this dataset (for example, the original creator of the data, before it was reprocessed by the creator of this dataset)');

setTooltipMessage('contributor_institution',
'contributor_institution (from the ACDD metadata standard) is a <b>required</b> global attribute with the short version of the name of the contributor institution.');

setTooltipMessage('contributor_email',
'contributor_email (from the ACDD metadata standard) is the <b>required</b> way to identify an email address (correctly formatted) that provides a way to contact the contributor.');

setTooltipMessage('license',
'license (from the ACDD metadata standard) is <b>required</b> global attribute with the license and/or usage restrictions.');

setTooltipMessage('cdm_timeseries_variables',
"cdm_timeseries_variables is <b>required</b> a comma-separated list generated by ERDDAP depending on the cdm_data_type, containing variables describing dataset features.");

$(document).ready(() => {
  const contributorEmail = document.getElementById('global_contributor_email');
  const contributorName = document.getElementById('global_contributor_name');
  const contributorInstitution = document.getElementById('global_contributor_institution');

  function validateContributorInstitutions() {
    const nameCount = contributorName.value
      .split(';')
      .filter(v => v.trim() !== '').length;

    const institutionCount = contributorInstitution.multiple
      ? Array.from(contributorInstitution.selectedOptions)
          .filter(option => option.value.trim() !== '').length
      : (contributorInstitution.value.trim() !== '' ? 1 : 0);

    const isValid = nameCount === institutionCount;

    contributorInstitution.setCustomValidity(
      isValid
        ? ''
        : 'The number of contributor institutions must match the number of contributor names.'
    );
  }

  contributorName.addEventListener('change', validateContributorInstitutions);
  contributorInstitution.addEventListener('change', validateContributorInstitutions);

  function validateContributorEmails() {
    const emailCount = contributorEmail.value
      .split(';')
      .filter(v => v.trim() !== '').length;

    const nameCount = contributorName.value
      .split(';')
      .filter(v => v.trim() !== '').length;

    const isValid = emailCount === nameCount;

    contributorEmail.setCustomValidity(
      isValid
        ? ''
        : 'The number of contributor emails must match the number of contributor names.'
    );

    contributorEmail.classList.toggle('is-valid', isValid);
    contributorEmail.classList.toggle('is-invalid', !isValid);
  }

  contributorEmail.addEventListener('change', validateContributorEmails);
  contributorName.addEventListener('change', validateContributorEmails);
});
