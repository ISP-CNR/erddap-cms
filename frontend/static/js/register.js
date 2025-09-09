let captchaImg = document.getElementById('captcha-container').firstElementChild;
captchaImg.classList.add('col-md-3','ps-5');

let captchaText = document.querySelector('input[name=captcha-text]');
captchaText.classList.add('col-md-9','w-25','form-control', 'ms-2');
captchaText.placeholder = "Type the text in the image";
captchaText.setAttribute('required', '');


var password = document.querySelector('[name="password"]')
var confirm_password = document.querySelector('[name="confirm_password"]')

function validatePassword(event){
  var status = confirm_password.validity.customError
  if(password.value != confirm_password.value) {
    confirm_password.setCustomValidity("Passwords Don't Match");
  } else {
    confirm_password.setCustomValidity('');
  }
  if (status != confirm_password.validity.customError) {
    
    event.target.reportValidity();
  }
}

password.addEventListener('change', validatePassword);
confirm_password.addEventListener('change', validatePassword);