// HindSite Quick Search Window
// For now this is purely visual: focus the input and allow ESC to close.

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('quickSearchInput');
  if (input) {
    input.focus();

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        window.close();
      }
    });
  }
});

