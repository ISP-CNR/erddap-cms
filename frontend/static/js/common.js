// This file is included id layout.html which is used in all the pages so its loaded for the entire website.

$(document).ready(() => {
  $('.select-institute').each(function(index){

    new TomSelect($(this), {
      valueField: 'name', // the key of JSON response to take as value
      labelField: 'name', // the key of the JSON response to take as label
      maxItems: 1,
      searchField: [],
      load: function(query, callback) {
        if (!query.length) return callback();
        this.clearOptions();
  
        var url =  `${URL_PATH}/api/data/search?q=` + encodeURIComponent(query);
        fetch(url)
            .then(response => response.json())
            .then(json => {
              callback(Object.entries(json).map(([key, name]) => ({ key, name })));
          })
          .catch(() => {
              callback([]);
          });
  
        var url =  `https://api.ror.org/v2/organizations?query.advanced=` + encodeURIComponent(query);
        fetch(url)
            .then(response => response.json())
            .then(json => {
               callback(json.items.map(x => ({ 
                   name: x.names.find(n => n.types.includes('ror_display'))?.value
               })));
          })
          .catch(() => {
              callback([]);
          });
        }
    });
  })
});
