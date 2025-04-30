// Shared utility functions
function setLoading(buttonId, isLoading) {
  const button = $(`#${buttonId}`);
  const spinner = button.find('.spinner-border');
  const searchText = button.find('#search_text');
  
  if (isLoading) {
    spinner.removeClass('d-none');
    searchText.text('Searching...');
    button.prop('disabled', true);
  } else {
    spinner.addClass('d-none');
    searchText.text('Search');
    button.prop('disabled', false);
  }
} 