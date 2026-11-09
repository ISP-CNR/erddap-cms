
$(document).ready( function () {
  $('#datasets_table')
    .DataTable({
      language: {
        info: 'Showing _START_ to _END_ of _TOTAL_ datasets',
        lengthMenu: '_MENU_ datasets per page',
        infoEmpty: 'No datasets available',
        infoFiltered: '(filtered from _MAX_ total datasets)',
        zeroRecords: 'No dataset found - sorry'
      },
      scrollCollapse: true,
      scrollY: '70vh',  
      pageLength : 10,
      lengthMenu: [10, 20, 50],
      fixedHeader: {
        footer: true,
        headerOffset: 0
      },
      autoWidth: false,
      columnDefs: [
        { 
          width: "30%", 
          targets: 1
        }, 
        {
          searchable: false,
          targets: [0,2,6]
        },
        { 
          orderable: false, 
          targets: [0,2,6] 
        },
        {
          targets: 3,
          render: DataTable.render.ellipsis(70),
          width: "70%"
        },
        { 
          width: "10%", 
          targets: 6 
        }
      ],
      order: [[4, 'desc']]
    });
  });
  

let loadingBlock = new Spinner(document.getElementById('loading-block'));
let btnCloseModal = document.getElementById('btn-close-modal');
let btnFileCloseModal = document.getElementById('btn-file-close-modal');
let btnFileUpload = document.getElementById('btn-add-new-datasetfromfile');
let fileUploadAlert = new Alert(document.getElementById('file-upload-alert'));
let fileField = document.querySelector('input[type="file"]');
function datasetNameInputOnChange(input) {
  document.getElementById('btn-add-new-dataset').disabled = !(input.value != "");   
}

function escapeHtml(text){
  var div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// file validity and the preview's checks are decided by two independent async
// calls - the submit button only unlocks once both have reported a green result
var fileIsValid = false;
var previewChecksPassed = false;

function updateSubmitButtonState(){
  var ready = fileIsValid && previewChecksPassed;
  btnFileUpload.disabled = !ready;
  document.getElementById('dataset-form-rest').classList.toggle('d-none', !ready);
}

function loadFilePreview(file){
  var previewBlock = document.getElementById('file-preview-block');
  var previewLoading = document.getElementById('file-preview-loading');
  var errorBlock = document.getElementById('file-preview-error');
  var contentBlock = document.getElementById('file-preview-content');

  previewChecksPassed = false;
  updateSubmitButtonState();

  previewBlock.classList.remove('d-none');
  previewLoading.classList.remove('d-none');
  errorBlock.classList.add('d-none');
  contentBlock.classList.add('d-none');
  document.getElementById('file-preview-success').classList.add('d-none');

  var formData = new FormData();
  formData.append('file', file);

  // the request is often near-instant on a local file, which makes the spinner
  // flash by too fast to register as "checks are running" - hold it for a
  // minimum stretch so the preliminary-checks step reads as a real step
  var MIN_LOADING_MS = 1200;
  var minDelay = new Promise(function(resolve){ setTimeout(resolve, MIN_LOADING_MS); });

  Promise.all([
    fetch(`${URL_PATH}/api/dataset/preview`, { method: 'POST', body: formData })
      .then(function(response){
        return response.json().then(function(data){ return { ok: response.ok, data: data }; });
      }),
    minDelay
  ]).then(function(results){
    var result = results[0];
    previewLoading.classList.add('d-none');

    if(!result.ok || result.data.result !== 'ok'){
      errorBlock.textContent = result.data.message || 'Could not preview this file.';
      errorBlock.classList.remove('d-none');
      previewChecksPassed = false;
      updateSubmitButtonState();
      return;
    }

    var data = result.data;
    document.getElementById('file-preview-summary').textContent =
      data.filename + ' · ' + data.row_count + ' rows · ' + data.column_count + ' columns · ' + data.file_size;

    var checksBlock = document.getElementById('file-preview-checks');
    checksBlock.innerHTML = '';
    (data.checks || []).filter(function(c){ return c.applicable !== false; }).forEach(function(c){
      var item = document.createElement('span');
      item.className = c.passed ? 'text-success' : 'text-danger';
      item.innerHTML = (c.passed ? '✓ ' : '✗ ') + escapeHtml(c.label);
      checksBlock.appendChild(item);
    });

    var warningsBlock = document.getElementById('file-preview-warnings');
    warningsBlock.innerHTML = '';
    (data.warnings || []).forEach(function(w){
      var alertDiv = document.createElement('div');
      alertDiv.className = 'alert alert-danger py-1 px-2';
      alertDiv.textContent = w.message;
      warningsBlock.appendChild(alertDiv);
    });

    var head = document.getElementById('file-preview-table-head');
    head.innerHTML = data.columns.map(function(c){ return '<th>' + escapeHtml(c) + '</th>'; }).join('');

    var body = document.getElementById('file-preview-table-body');
    body.innerHTML = data.rows.map(function(row){
      return '<tr>' + row.map(function(cell){ return '<td>' + escapeHtml(String(cell)) + '</td>'; }).join('') + '</tr>';
    }).join('');

    contentBlock.classList.remove('d-none');
    previewChecksPassed = !!data.all_checks_passed;
    document.getElementById('file-preview-success').classList.toggle('d-none', !previewChecksPassed);
    updateSubmitButtonState();
  }).catch(function(){
    previewLoading.classList.add('d-none');
    errorBlock.textContent = 'Could not preview this file.';
    errorBlock.classList.remove('d-none');
    previewChecksPassed = false;
    updateSubmitButtonState();
  });
}

function checkNewDatasetfromFile(){
var file = document.getElementById('file');

fileUploadAlert.hide();
btnCloseModal.disabled = true;
fileIsValid = false;
previewChecksPassed = false;
updateSubmitButtonState();
btnFileCloseModal.disabled = true;
loadingBlock.setMessage("Checking file...");
loadingBlock.show();

if(file.files.length){
  loadFilePreview(file.files[0]);
} else {
  document.getElementById('file-preview-block').classList.add('d-none');
}

// Check file validity
isFileValid(file.files[0]).then(result => {
  if(!result.isValid){
    // the file is not valid, show the alert
    fileUploadAlert.setMessage(result.message);
    fileUploadAlert.show();
    fileIsValid = false;
  } else {
    // the file is valid, can be uploaded.
    fileIsValid = true;
    fileUploadAlert.hide();
  }
  updateSubmitButtonState();
  loadingBlock.hide();
  btnFileCloseModal.disabled = false;
  btnCloseModal.disabled = false;
});

if(file.files.length){
  var reader = new FileReader();
  reader.onload = async function (progressEvent) {
    content = this.result.toLowerCase();
    //title_summary = document.getElementById('title_summary');
     
    //summary_form=document.getElementById('summary_form');
    let mimeType = await getMimeType(file.files[0]);

    if (mimeType == "text/csv"|| mimeType == "application/vnd.ms-excel") {
      title_summary = document.getElementById('title_summary');
      title_summary.style.display = '';
      title_form=document.getElementById('title_form');
      title_form.setAttribute('required', 'true');
      summary_form.setAttribute('required','true');
      cdm_data_type=document.getElementById("cdm_data_type");
      option=cdm_data_type.options[cdm_data_type.selectedIndex].value;
      if (option=="Grid"){
        cdm_data_type.selectedIndex=0;
      }
      document.getElementById("grid_option").disabled = true; 
    }
    if (mimeType == "application/x-netcdf" || mimeType == "application/x-hdf5"){

      title_summary.style.display = 'none';
      title_form.removeAttribute('required');
      summary_form.removeAttribute('required');
      document.getElementById("grid_option").disabled = false; 
    }
    //console.log(file.files[0].type)
    if (mimeType == "text/csv" || mimeType == "application/x-netcdf" || mimeType == "application/vnd.ms-excel") {
      latitude = document.getElementById('latitude');
      longitde = document.getElementById('longitude');

      if (content.includes("latitude")){
        latitude.style.display = 'none';
        latitude.querySelector('input').setAttribute("disabled", "disabled");
      }else{
        latitude.style.display = '';
        latitude.querySelector('input').removeAttribute("disabled");
      }
      if (content.includes("longitude")){
        longitude.style.display = 'none';
        longitude.querySelector('input').setAttribute("disabled", "disabled");
      }else{
        longitude.style.display = '';
        longitude.querySelector('input').removeAttribute("disabled");
      }
    }
  };
  reader.readAsText(file.files[0].slice(0,10240));
}
}

function addNewDatasetfromFile(){

/*   var datasetNameInput = document.getElementById("datasetNameInput");
if(datasetNameInput.validity.patternMismatch){
  datasetNameInput.setCustomValidity("Only alphanumeric characters and underscores are allowed.");
  datasetNameInput.reportValidity();
  return
}else{
  datasetNameInput.setCustomValidity("");
} */

const formElement = document.getElementById("addNewDatasetfromfileForm");
if (!formElement.checkValidity()){
  formElement.reportValidity();
  return;
}
formElement.reportValidity();

const formData = new FormData(formElement);

// create the datasetID from the dataset name
let datasetNameInput = formData.get('title').trim().toLowerCase().replace(/ /g, '_').replace(/[^a-zA-Z0-9_]/g,'');
//formData.set("datasetNameInput", `${datasetNameInput}_${generateRandomId(6)}`);
formData.set("datasetNameInput", datasetNameInput);

var file = document.getElementById('file');

if(file.files.length){
  document.getElementById('btn-add-new-datasetfromfile').disabled = true;
  document.getElementById('progressbar-add-new-datasetfromfile').parentElement.style.display = '';
  document.getElementById('progressbar-add-new-datasetfromfile').setAttribute("aria-valuenow", 5);
  document.getElementById('progressbar-add-new-datasetfromfile').style.width = 5+"%";
  document.getElementById('progressbar-add-new-datasetfromfile').innerHTML = 5+"%";

  var reader = new FileReader();
  fileUploadAlert.hide();
  
  reader.onload = function(e){
    let request = new XMLHttpRequest();
    request.open('POST', `${URL_PATH}/api/dataset/newfromfile`); 
    request.responseType = 'json';
    
    request.upload.addEventListener('progress', function(e) {
      progress = Math.round(5 + (e.loaded / e.total)*90);
      document.getElementById('progressbar-add-new-datasetfromfile').setAttribute("aria-valuenow", progress);
      document.getElementById('progressbar-add-new-datasetfromfile').style.width = progress+"%";
      document.getElementById('progressbar-add-new-datasetfromfile').innerHTML = progress+"%";
    });
    
    request.addEventListener('load', function(e) {
      document.getElementById('btn-add-new-datasetfromfile').disabled = false;
      document.getElementById('progressbar-add-new-datasetfromfile').parentElement.style.display = 'none';
      if (request.status === 200 && request.response['result'] === "ok") {
        window.open(`${URL_PATH}`,'_self');
      } else {
        if(request.response['message']){
          fileUploadAlert.setMessage(request.response['message']);
        } else {
          fileUploadAlert.setMessage(JSON.stringify(request.response));
        }
        fileUploadAlert.show();
      }
    });
    
    request.send(formData);
  };
 
  reader.readAsDataURL(file.files[0]);
}

}

function closeModalHandler(){
fileField.value = "";
loadingBlock.hide();
fileUploadAlert.hide();
btnCloseModal.disabled = false;
btnFileUpload.disabled = true;
btnFileCloseModal.disabled = false;
}

function addNewDatasetFromERDDAP() {
let url = document.getElementById('erddap-url').value;

// the request to the server
let data = { "datasetURL": url }

fetch(`${URL_PATH}/api/dataset/newfromerddap`, {
  method: 'POST',
  headers: {
  'Content-Type': 'application/json'
  },
  body: JSON.stringify(data)
})
.then(response => response.json()) //convert response from json to js object
.then(data => {
  if(data.result == "ok"){
    window.open(`${URL_PATH}`,'_self');
  }
  if(data.result == "error"){
    alert(`Error: ${data.message}`)
  }
})
.catch(error => {
  console.error(error);
});

}

function validateURL(input){
  let isInputValid = input.checkValidity() && input.value != "";
  let btn = document.getElementById('btn-add-dataset-from-erddap');
  btn.disabled = !isInputValid;

  //TODO: check that is a real ERDDAP instance
  setValidity(input, isInputValid);
}

function downloadISOMetadata(button){

let datasetFilename = button.getAttribute('data-bs-dataset-filename');

const data = {"datasetFilename": datasetFilename};

console.log(datasetFilename);

fetch(`${URL_PATH}/api/dataset/iso19139`, {
  method: 'POST',
  headers: {
  'Content-Type': 'application/json'
  },
  body: JSON.stringify(data)
})
.then(response => response.blob()) //convert response from json to js object
.then(blob => {
  var url = window.URL.createObjectURL(blob);
  var link = document.createElement('a');
  document.body.appendChild(link);
  link.style = "display: none";
  link.href = url;
  link.download = `${datasetFilename}`;
  link.click();

  setTimeout(() => {
  window.URL.revokeObjectURL(url);
  link.remove(); } , 100);
})
.catch(error => {
  console.error('Error:', error);
});
}

// to change the style of the table
function rowStyle(row, index) {
return {
  css: {
    "text-wrap" : "nowrap"
  }
}
}