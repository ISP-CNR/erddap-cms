const confirmModal = document.getElementById('confirmModal')
if (confirmModal) {
  confirmModal.addEventListener('show.bs.modal', event => {
    const button = event.relatedTarget
    // Extract info from data-bs-* attributes
    const title = button.getAttribute('data-bs-title')
    const body = button.getAttribute('data-bs-body')
    const url = button.getAttribute('data-bs-url')
    const json = button.getAttribute('data-bs-json')

    // Update the modal's content.
    const modalTitle = confirmModal.querySelector('.modal-title')
    modalTitle.innerHTML = title
    const modalBody = confirmModal.querySelector('.modal-body')
    modalBody.innerHTML = body


    var old_element = confirmModal.querySelector('#confirmButtonModal')
    var new_element = old_element.cloneNode(true);
    old_element.parentNode.replaceChild(new_element, old_element);
    new_element.addEventListener('click', function() {
        // Call API for dataset deletion
        fetch(`${URL_PATH}/${url}`, {
            method: 'POST',
            headers: {
            'Content-Type': 'application/json'
            },
            body: json
        })
        .then(response => response.json()) //convert response from json to js object
        .then(data => {
            if(data.result == 'ok') {
            //reload page
            location.reload();
            }

            if(data.result == "error") {
            showMessageModal("error", data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });

     }, false);



  })


}