
let spinner = new Block(document.getElementById('upload-modal-spinner'));
let message = new Text(document.getElementById('upload-modal-message'));
let btnFileCloseModal = document.getElementById('btn-file-close-modal');
let btnCloseModal = document.getElementById('btn-close-modal');
let btnFileUpload = document.getElementById('btn-file-upload');
let fileUploadAlert = new Alert(document.getElementById('file-upload-alert'));
let fileField = document.querySelector('input[type="file"]');
let fileUploadProgressBar = new Progress(document.getElementById('upload-file-progress-bar'));
const uploadButton =  document.getElementById('btn-file-upload');

const controller = new AbortController();

async function fileUploadOnChange(input){

  if(input.files){

    fileUploadNewState();

    var files = input.files;

    console.log(files);

    let filesValidationResults = [];

    for(const file of [...files]) {
      let result = await isFileValid(file);
      filesValidationResults.push(result);
    }

    let invalidFilesResults = filesValidationResults.filter(result => result.isValid == false );

    if(invalidFilesResults.length > 0){
      // some file are not valid
      let errorMessage = 'Error:';

      invalidFilesResults.forEach(result =>
        errorMessage += `\n- ${result.file.name}: ${result.message}`
      );
      
      fileUploadAlert.setMessage(errorMessage);
      fileUploadAlert.show();
    } else {
      // all files are valid, can be uploaded.
      btnFileUpload.disabled = false;
      fileUploadAlert.hide();
    }

    fileUploadOkState();
    return;
  }
}

async function uploadFile(id) {

  enterUploadingState();

  for(const fileToUpload of [...fileField.files]) {

    let formData = new FormData();
    formData.append("id", id);
    formData.append('file', fileToUpload);
  
    try {
      const response = await axios({ 
        method: 'put',
        url: `${URL_PATH}/api/dataset/file/upload`,
        data: formData,
        signal: controller.signal,
        onUploadProgress: (progressEvent) => {
          const { loaded, total } = progressEvent;
          let percentage = Math.floor((loaded * 100) / total);
          fileUploadProgressBar.setPercentage(percentage);
        }
      })
      console.log(response);
    } catch (error){
      console.error(error);
    }
  }

  exitUploadingState();
}

// Close button handler
function closeModalHandler(){
  fileField.value = "";
  spinner.hide();
  message.hide();
  fileUploadAlert.hide();
  fileUploadProgressBar.hide();
  btnCloseModal.disabled = false;
  btnFileUpload.disabled = true;
  btnFileCloseModal.disabled = false;
  controller.abort();
}

function enterUploadingState(){
  // View stuff
  uploadButton.disabled = true;
  fileField.disabled = true;
  message.setMessage("Uploading...");
  spinner.hide();
  fileUploadProgressBar.show();
  btnCloseModal.disabled = true;
}

function exitUploadingState(){
  btnFileCloseModal.click();
  spinner.hide();
  message.hide();
  fileUploadProgressBar.hide();
  fileField.value = "";
  location.reload();
}

function fileUploadNewState(){
  fileUploadAlert.hide();
  message.setMessage("Checking file...");
  spinner.show();
  btnFileCloseModal.disabled = true;
  btnCloseModal.disabled = true;
  btnFileUpload.disabled = true;
}

function fileUploadOkState() {
  spinner.hide();
  message.hide();
  btnFileCloseModal.disabled = false;
  btnCloseModal.disabled = false;
}