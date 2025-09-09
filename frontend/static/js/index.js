
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
      pageLength : 20,
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

function checkNewDatasetfromFile(){
var file = document.getElementById('file');

fileUploadAlert.hide();
btnCloseModal.disabled = true;
btnFileUpload.disabled = true;
btnFileCloseModal.disabled = true;
loadingBlock.setMessage("Checking file...");
loadingBlock.show();

// Check file validity
isFileValid(file.files[0]).then(result => {
  if(!result.isValid){
    // the file is not valid, show the alert
    fileUploadAlert.setMessage(result.message);
    fileUploadAlert.show();
  } else {
    // the file is valid, can be uploaded.
    btnFileUpload.disabled = false;
    fileUploadAlert.hide();
  }
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
    if (mimeType == "application/x-netcdf"){

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