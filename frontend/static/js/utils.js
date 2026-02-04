// this file is included in layout.html header so the other js files can see its content

const URL_PATH = "/erddap-cms"

function showMessageModal(label, message){
  
  document.getElementById("messageModalLabel").innerText = label;
  document.getElementById("messageModalText").innerText = message;
 
  const messageModal = new bootstrap.Modal('#messageModal');
  messageModal.show();
}

function selectCDM(obj) {

  if(obj.value=="EDDTable") {
    document.getElementById('cdm_data_type').style.display='block'; 
  } else {
    document.getElementById('cdm_data_type').style.display='none';
  }
}

async function isFileValid(file) {

  const allowedMimeTypes = ["text/csv", "application/x-netcdf", "application/vnd.ms-excel", "application/x-hdf5" ];

  // check file type is csv or netcdf
  let mimeType = await getMimeType(file);

  if (!allowedMimeTypes.includes(mimeType)) {
    return { file: file, isValid: false, message: "Only csv, netcdf and h5 files are allowed."};
  }

  // check file size is under 2 GB
  if (file.size > 2147483648) {
    return { file: file, isValid: false, message: "File must be under 2048 MB (2 GB)"};
  } 

  return  { file: file, isValid: true, message: "File is valid"};
}

function getMimeType(file) {
  return new Promise((resolve, reject) => {
    const fileReader = new FileReader();

    fileReader.onloadend = function (event) {
      let mimeType = '';

      const arr = new Uint8Array(event.target.result).subarray(0, 8);
      let header = '';

      for (let i = 0; i < arr.length; i++) {
        header += arr[i].toString(16).padStart(2, '0');
      }

      switch (header) {
        case '43444601': // NetCDF (CDF)
          mimeType = 'application/x-netcdf';
          break;

        case '894844460d0a1a0a': // HDF5
          mimeType = 'application/x-hdf5';
          break;

        default:
          mimeType = file.type;
          break;
      }

      resolve(mimeType);
    };

    fileReader.readAsArrayBuffer(file);
  });
}


// UI Classes

class Block {
  constructor(element) {
    this.element = element;
  }

  show(){
    // if is hidden remove d-none class, if is already visibile, do nothing.
    if(this.element.classList.contains('d-none')){
      this.element.classList.toggle('d-none');
    }
  }

  hide(){
    // if is visible, add the d-none class, otherwise nothing.
    if(!this.element.classList.contains('d-none')){
      this.element.classList.toggle('d-none');
    }
  }
}

class Alert extends Block {
  constructor(element) {
    super(element);
  }

  setMessage(message){
    this.element.querySelector("span").innerText = message;
  }
}

class Spinner extends Block {
  constructor(element) {
    super(element);
  }

  hideSpinner(){
    if(!this.element.querySelector('div').classList.contains('d-none')){
      this.element.querySelector('div').classList.toggle('d-none');
    }
  }

  setMessage(message){
    this.element.querySelector("p").innerText = message;
  }
}

class Text extends Block {
  constructor(element) {
    super(element);
  }

  setMessage(message){
    this.element.innerText = message;
    this.show();
  }
}

class Progress extends Block {
  constructor(element) {
    super(element);
  }

  setPercentage(percentage){
    this.element.querySelector("div").ariaValueNow = percentage;
    this.element.querySelector("div").style.width = `${percentage}%`;
    this.element.querySelector("div").innerText = `${percentage}%`;
  }
}

function setTooltipMessage(elementId, message) {
  let seeMoreUrl = `<a href='https://coastwatch.pfeg.noaa.gov/erddap/download/setupDatasetsXml.html#${elementId}' target='_blank'>See more</a>`;
  
  let element = document.getElementById(`global_${elementId}_info`);
  if(element) {
    element.setAttribute('data-bs-content', `${message} ${seeMoreUrl}`);
  }
}

function generateRandomId(length) {
  const characters = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let randomId = '';

  for (let i = 0; i < length; i++) {
    const randomIndex = Math.floor(Math.random() * characters.length);
    randomId += characters.charAt(randomIndex);
  }

  return randomId;
}

function setValidity(el, validity){
  if(el.value == ""){
    el.classList.remove('is-invalid', 'is-valid');
  } else {
    if(validity) {
      el.classList.remove('is-invalid');
      el.classList.add('is-valid');
    } else {
      el.classList.remove('is-valid');
      el.classList.add('is-invalid');
    } 
  }
}