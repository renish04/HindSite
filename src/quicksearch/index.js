// HindSite Quick Search Window
// Focus input, ESC closes window, and support voice input via Web Speech API.

let qsRecognition = null;
let qsRecognizing = false;
let qsSpeechBaseText = '';
let qsSpeechSupported = null;

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('quickSearchInput');
  const micBtn = document.getElementById('quickSearchMicBtn');

  if (input) {
    input.focus();

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        window.close();
      }
    });
  }

  if (micBtn) {
    micBtn.addEventListener('click', () => {
      toggleQuickSearchSpeech();
    });
  }

  // Auto-start voice input when window opens
  startQuickSearchSpeech();
});

function ensureQuickSearchSpeechSupport() {
  if (qsSpeechSupported !== null) return qsSpeechSupported;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  qsSpeechSupported = !!SpeechRecognition;
  if (qsSpeechSupported && !qsRecognition) {
    const SR = SpeechRecognition;
    qsRecognition = new SR();
    qsRecognition.lang = navigator.language || 'en-US';
    qsRecognition.continuous = false;
    qsRecognition.interimResults = true;

    qsRecognition.onstart = () => {
      qsRecognizing = true;
      const input = document.getElementById('quickSearchInput');
      qsSpeechBaseText = input && input.value ? input.value : '';
    };

    qsRecognition.onresult = (event) => {
      const input = document.getElementById('quickSearchInput');
      if (!input) return;

      let finalText = '';
      let interimText = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const res = event.results[i];
        if (res.isFinal) {
          finalText += res[0].transcript;
        } else {
          interimText += res[0].transcript;
        }
      }

      const base = qsSpeechBaseText ? qsSpeechBaseText + ' ' : '';
      const combined = (base + finalText + ' ' + interimText).trim();
      input.value = combined;
    };

    qsRecognition.onerror = () => {
      qsRecognizing = false;
    };

    qsRecognition.onend = () => {
      qsRecognizing = false;
    };
  }
  return qsSpeechSupported;
}

function startQuickSearchSpeech() {
  if (!ensureQuickSearchSpeechSupport()) return;
  if (!qsRecognition || qsRecognizing) return;
  try {
    qsRecognition.start();
  } catch (e) {
    // ignore repeated start errors
  }
}

function stopQuickSearchSpeech() {
  if (qsRecognition && qsRecognizing) {
    try {
      qsRecognition.stop();
    } catch (_) {}
  }
}

function toggleQuickSearchSpeech() {
  if (qsRecognizing) {
    stopQuickSearchSpeech();
  } else {
    startQuickSearchSpeech();
  }
}

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

