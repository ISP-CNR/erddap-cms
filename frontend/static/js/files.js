
let spinner = new Block(document.getElementById('upload-modal-spinner'));
let message = new Text(document.getElementById('upload-modal-message'));
let btnFileCloseModal = document.getElementById('btn-file-close-modal');
let btnCloseModal = document.getElementById('btn-close-modal');
let btnFileUpload = document.getElementById('btn-file-upload');
let fileUploadAlert = new Alert(document.getElementById('file-upload-alert'));
let fileField = document.querySelector('input[type="file"]');
let fileUploadProgressBar = new Progress(document.getElementById('upload-file-progress-bar'));
const uploadButton =  document.getElementById('btn-file-upload');

// a fresh controller per upload attempt - reusing one across attempts meant that
// closing the modal once (calling .abort() on it) permanently poisoned every
// later upload in the page's lifetime, since an already-aborted signal makes
// axios reject instantly and silently (see the empty catch in uploadFile below)
let controller = new AbortController();

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

    // two selected files sharing a name would silently overwrite one another
    // during the upload loop (the second save clobbers the first, with no
    // indication anything was lost) - catch that here, before upload starts.
    // Flag every file with a repeated name, not just the later occurrences,
    // so the error list doesn't look like only one specific file is at fault.
    let nameCounts = new Map();
    for(const file of [...files]) {
      nameCounts.set(file.name, (nameCounts.get(file.name) || 0) + 1);
    }
    for(const file of [...files]) {
      if (nameCounts.get(file.name) > 1) {
        filesValidationResults.push({ file: file, isValid: false, message: "Duplicate filename in this selection." });
      }
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

  // this attempt gets its own controller so a previous abort() (from closing the
  // modal on an earlier attempt) can never affect it
  controller = new AbortController();

  let failures = [];
  let warnings = [];

  // overall progress across the whole batch, not just the file in flight -
  // otherwise the bar restarted at 0% for every file, reading as if each one
  // reset the upload instead of being one step of it
  let filesToUpload = [...fileField.files];
  let totalBytes = filesToUpload.reduce((sum, f) => sum + f.size, 0);
  let bytesDoneBeforeCurrent = 0;

  for(const fileToUpload of filesToUpload) {

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
          const { loaded } = progressEvent;
          let percentage = totalBytes > 0
            ? Math.floor(((bytesDoneBeforeCurrent + loaded) * 100) / totalBytes)
            : 0;
          fileUploadProgressBar.setPercentage(percentage);
        }
      })
      console.log(response);
      if (response?.data?.warning) {
        warnings.push(`${fileToUpload.name}: ${response.data.warning}`);
      }
    } catch (error){
      console.error(error);
      let serverMessage = error?.response?.data?.message;
      failures.push(`${fileToUpload.name}: ${serverMessage || error.message || 'upload failed'}`);
    }

    bytesDoneBeforeCurrent += fileToUpload.size;
  }

  exitUploadingState(failures, warnings);
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

function exitUploadingState(failures, warnings){
  spinner.hide();
  message.hide();
  fileUploadProgressBar.hide();
  fileField.value = "";
  fileField.disabled = false;
  uploadButton.disabled = true;
  btnCloseModal.disabled = false;
  btnFileCloseModal.disabled = false;

  fileUploadAlert.element.classList.remove('alert-danger', 'alert-warning');

  if (failures && failures.length > 0) {
    // keep the modal open so the error is actually visible - a silent
    // reload here is what let failed uploads look like they'd succeeded
    fileUploadAlert.element.classList.add('alert-danger');
    fileUploadAlert.setMessage('Some files failed to upload:\n- ' + failures.join('\n- '));
    fileUploadAlert.show();
    return;
  }

  if (warnings && warnings.length > 0) {
    // the upload itself succeeded, so the file list should still refresh to
    // show it - stash the warning across the reload instead of leaving the
    // modal open (which silently left the file missing from the list behind
    // it until the user thought to refresh manually)
    sessionStorage.setItem('fileUploadWarning', 'Uploaded, but:\n- ' + warnings.join('\n- '));
  }

  btnFileCloseModal.click();
  location.reload();
}

// show a warning stashed by exitUploadingState just before it reloaded the
// page, then clear it so it doesn't resurface on a later, unrelated reload
(function showPendingUploadWarning(){
  const pending = sessionStorage.getItem('fileUploadWarning');
  if (!pending) return;
  sessionStorage.removeItem('fileUploadWarning');
  const el = document.getElementById('page-upload-warning');
  if (!el) return;
  el.textContent = pending;
  el.classList.remove('d-none');
})();

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