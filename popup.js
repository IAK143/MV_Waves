document.addEventListener('DOMContentLoaded', () => {
    const enableToggle = document.getElementById('enabled');
    const styleSelect = document.getElementById('style');
    const symmetricToggle = document.getElementById('symmetric');
    const maxHeightSlider = document.getElementById('maxHeight');
    const maxHeightValue = document.getElementById('maxHeightValue');
    const barCountSlider = document.getElementById('barCount');
    const barCountValue = document.getElementById('barCountValue');
    const glowSlider = document.getElementById('glow');
    const glowValue = document.getElementById('glowValue');


    // Load saved settings
    chrome.storage.local.get(['enabled', 'style', 'symmetric', 'maxHeight', 'barCount', 'glow'], (data) => {
        enableToggle.checked = data.enabled !== false; // Default to true
        styleSelect.value = data.style || 'bars';
        symmetricToggle.checked = data.symmetric === true; // Default to false
        
        const mHeight = data.maxHeight || 40;
        maxHeightSlider.value = mHeight;
        maxHeightValue.innerText = mHeight + '%';

        const bCount = data.barCount || 64;
        barCountSlider.value = bCount;
        barCountValue.innerText = bCount;

        const glow = data.glow || 15;
        glowSlider.value = glow;
        glowValue.innerText = glow;
    });


    // Save settings and notify content script
    enableToggle.addEventListener('change', () => {
        const enabled = enableToggle.checked;
        chrome.storage.local.set({ enabled: enabled });
        sendMessageToActiveTab({ type: 'UPDATE_STATE', enabled: enabled });
    });

    styleSelect.addEventListener('change', () => {
        const style = styleSelect.value;
        chrome.storage.local.set({ style: style });
        sendMessageToActiveTab({ type: 'UPDATE_STYLE', style: style });
    });

    symmetricToggle.addEventListener('change', () => {
        const symmetric = symmetricToggle.checked;
        chrome.storage.local.set({ symmetric: symmetric });
        sendMessageToActiveTab({ type: 'UPDATE_SYMMETRIC', symmetric: symmetric });
    });

    maxHeightSlider.addEventListener('input', () => {
        const val = parseInt(maxHeightSlider.value);
        maxHeightValue.innerText = val + '%';
        sendMessageToActiveTab({ type: 'UPDATE_MAX_HEIGHT', maxHeight: val });
    });

    maxHeightSlider.addEventListener('change', () => {
        const val = parseInt(maxHeightSlider.value);
        chrome.storage.local.set({ maxHeight: val });
    });

    barCountSlider.addEventListener('input', () => {
        const val = parseInt(barCountSlider.value);
        barCountValue.innerText = val;
        sendMessageToActiveTab({ type: 'UPDATE_BAR_COUNT', barCount: val });
    });

    barCountSlider.addEventListener('change', () => {
        const val = parseInt(barCountSlider.value);
        chrome.storage.local.set({ barCount: val });
    });

    glowSlider.addEventListener('input', () => {
        const val = parseInt(glowSlider.value);
        glowValue.innerText = val;
        sendMessageToActiveTab({ type: 'UPDATE_GLOW', glow: val });
    });

    glowSlider.addEventListener('change', () => {
        const val = parseInt(glowSlider.value);
        chrome.storage.local.set({ glow: val });
    });


    function sendMessageToActiveTab(message) {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0] && tabs[0].id) {
                chrome.tabs.sendMessage(tabs[0].id, message).catch(err => {
                    console.log("Could not send message to content script:", err);
                });
            }
        });
    }
});
