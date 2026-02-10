// HindSite Quick Search Window
// Focus input, ESC closes window, and support voice input via Web Speech API.

let qsRecognition = null;
let qsRecognizing = false;
let qsSpeechBaseText = '';
let qsSpeechSupported = null;

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('quickSearchInput');
  const micBtn = document.getElementById('quickSearchMicBtn');
  const shell = document.querySelector('.shell');

  // Pop-in animation
  if (shell) {
    requestAnimationFrame(() => shell.classList.add('is-open'));
  }

  if (input) {
    input.focus();
    autoResizeQuickInput();

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        window.close();
      }
    });

    input.addEventListener('input', () => {
      autoResizeQuickInput();
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
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.add('listening');
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
      autoResizeQuickInput();
    };

    qsRecognition.onerror = () => {
      qsRecognizing = false;
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.remove('listening');
    };

    qsRecognition.onend = () => {
      qsRecognizing = false;
      const micBtn = document.getElementById('quickSearchMicBtn');
      if (micBtn) micBtn.classList.remove('listening');
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

function autoResizeQuickInput() {
  const input = document.getElementById('quickSearchInput');
  if (!input) return;

  input.style.height = 'auto';
  const maxHeight = 120;
  const nextHeight = Math.min(input.scrollHeight, maxHeight);
  input.style.height = `${nextHeight}px`;
  input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

