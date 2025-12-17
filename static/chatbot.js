// static/chatbot.js
(function() {
    // Get parameters from URL - FIXED: Properly extract from script src, not page URL
    let botId = null;
    let apiKey = null;
    let botName = 'AI Assistant';
    
    // Find the current script tag to get parameters from its src
    const scripts = document.getElementsByTagName('script');
    for (let i = 0; i < scripts.length; i++) {
        const script = scripts[i];
        if (script.src && script.src.includes('chatbot.js')) {
            const url = new URL(script.src);
            const params = new URLSearchParams(url.search);
            botId = params.get('bot_id');
            apiKey = params.get('api_key');
            botName = params.get('bot_name') || 'AI Assistant';
            break;
        }
    }
    
    // If still not found, try from page URL as fallback
    if (!botId) {
        const urlParams = new URLSearchParams(window.location.search);
        botId = urlParams.get('bot_id');
        apiKey = urlParams.get('api_key');
        botName = urlParams.get('bot_name') || 'AI Assistant';
    }
    
    // Debug logging
    console.log('Chatbot Config:', { botId, apiKey, botName });
    
    if (!botId || !apiKey) {
        console.error('Missing bot_id or api_key parameters');
        return;
    }

    console.log('=== CHATBOT DEBUG INFO ===');
    console.log('Bot ID:', botId);
    console.log('API Key present:', !!apiKey);
    console.log('API Key length:', apiKey ? apiKey.length : 'none');
    console.log('Bot Name:', botName);
    console.log('==========================');
    
    // Theme management
    const theme = {
        current: localStorage.getItem('chatbot-theme') || 'light',
        light: {
            primary: '#2563eb',
            primaryGradient: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            background: '#ffffff',
            surface: '#f8fafc',
            text: '#1e293b',
            textSecondary: '#64748b',
            border: '#e2e8f0',
            shadow: '0 8px 32px rgba(0,0,0,0.1)',
            userBubble: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
            botBubble: '#ffffff',
            inputBackground: '#f8fafc',
            headerBackground: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)'
        },
        dark: {
            primary: '#3b82f6',
            primaryGradient: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
            background: '#0f172a',
            surface: '#1e293b',
            text: '#f1f5f9',
            textSecondary: '#94a3b8',
            border: '#334155',
            shadow: '0 8px 32px rgba(0,0,0,0.3)',
            userBubble: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
            botBubble: '#1e293b',
            inputBackground: '#1e293b',
            headerBackground: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)'
        }
    };
    
    // Create chatbot widget
    const widgetHtml = `
        <div id="chatbot-widget" class="chatbot-widget" style="
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 380px;
            height: 600px;
            background: ${theme.light.background};
            border: 1px solid ${theme.light.border};
            border-radius: 20px;
            box-shadow: ${theme.light.shadow};
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
            z-index: 10000;
            display: none;
            flex-direction: column;
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        ">
            <!-- Header -->
            <div class="chatbot-header" style="
                background: ${theme.light.headerBackground};
                color: white;
                padding: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            ">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div class="chatbot-avatar" style="
                        width: 40px;
                        height: 40px;
                        background: rgba(255,255,255,0.2);
                        border-radius: 12px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 18px;
                        backdrop-filter: blur(10px);
                    ">🤖</div>
                    <div>
                        <h3 style="margin: 0; font-size: 16px; font-weight: 600; letter-spacing: -0.01em;">${botName}</h3>
                        <p style="margin: 2px 0 0 0; font-size: 12px; opacity: 0.8; font-weight: 400;">Online • Always available</p>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <!-- Theme Toggle -->
                    <button id="theme-toggle" class="theme-toggle" style="
                        background: rgba(255,255,255,0.15);
                        border: none;
                        color: white;
                        width: 32px;
                        height: 32px;
                        border-radius: 8px;
                        font-size: 14px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s ease;
                        backdrop-filter: blur(10px);
                    " title="Toggle theme">
                        <span class="theme-icon">🌙</span>
                    </button>
                    <!-- Close Button -->
                    <button id="close-chat" class="close-chat" style="
                        background: rgba(255,255,255,0.15);
                        border: none;
                        color: white;
                        width: 32px;
                        height: 32px;
                        border-radius: 8px;
                        font-size: 18px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s ease;
                        backdrop-filter: blur(10px);
                    ">×</button>
                </div>
            </div>
            
            <!-- Messages Container -->
            <div id="chat-messages" class="chat-messages" style="
                flex: 1;
                padding: 20px;
                overflow-y: auto;
                background: ${theme.light.surface};
                display: flex;
                flex-direction: column;
                gap: 16px;
            "></div>
            
            <!-- Typing Indicator -->
            <div id="typing-indicator" class="typing-indicator" style="
                display: none;
                padding: 0 20px 16px 20px;
                align-items: center;
                gap: 12px;
                color: ${theme.light.textSecondary};
                font-size: 13px;
                font-weight: 500;
            ">
                <div style="display: flex; gap: 4px;">
                    <div class="typing-dot" style="
                        width: 6px;
                        height: 6px;
                        background: ${theme.light.primary};
                        border-radius: 50%;
                        animation: typing 1.4s infinite ease-in-out;
                    "></div>
                    <div class="typing-dot" style="
                        width: 6px;
                        height: 6px;
                        background: ${theme.light.primary};
                        border-radius: 50%;
                        animation: typing 1.4s infinite ease-in-out 0.2s;
                    "></div>
                    <div class="typing-dot" style="
                        width: 6px;
                        height: 6px;
                        background: ${theme.light.primary};
                        border-radius: 50%;
                        animation: typing 1.4s infinite ease-in-out 0.4s;
                    "></div>
                </div>
                <span>${botName} is typing...</span>
            </div>
            
            <!-- Input Area -->
            <div class="chatbot-input-area" style="
                padding: 20px;
                border-top: 1px solid ${theme.light.border};
                background: ${theme.light.background};
            ">
                <div style="display: flex; gap: 12px; align-items: end;">
                    <input type="text" id="chat-input" class="chat-input" placeholder="Type your message..." style="
                        flex: 1;
                        padding: 14px 18px;
                        border: 1.5px solid ${theme.light.border};
                        border-radius: 16px;
                        outline: none;
                        font-size: 14px;
                        background: ${theme.light.inputBackground};
                        color: ${theme.light.text};
                        transition: all 0.2s ease;
                        font-family: inherit;
                    ">
                    <button id="send-btn" class="send-btn" style="
                        width: 46px;
                        height: 46px;
                        background: ${theme.light.primaryGradient};
                        color: white;
                        border: none;
                        border-radius: 14px;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 18px;
                        transition: all 0.2s ease;
                        font-weight: 600;
                    ">↑</button>
                </div>
                <p style="
                    margin: 12px 0 0 0;
                    font-size: 11px;
                    color: ${theme.light.textSecondary};
                    text-align: center;
                    font-weight: 500;
                    letter-spacing: 0.02em;
                ">Powered by AI Assistant • Secure & Private</p>
            </div>
        </div>
        
        <!-- Toggle Button -->
        <button id="chat-toggle" class="chat-toggle" style="
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 60px;
            height: 60px;
            background: ${theme.light.primaryGradient};
            color: white;
            border: none;
            border-radius: 18px;
            font-size: 24px;
            cursor: pointer;
            box-shadow: 0 8px 25px rgba(37, 99, 235, 0.3);
            z-index: 10001;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(10px);
        ">💬</button>
        
        <style>
            @keyframes typing {
                0%, 60%, 100% { transform: translateY(0); }
                30% { transform: translateY(-4px); }
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            
            @keyframes slideIn {
                from { transform: translateY(20px) scale(0.95); opacity: 0; }
                to { transform: translateY(0) scale(1); opacity: 1; }
            }
            
            .chat-toggle:hover {
                transform: translateY(-2px) scale(1.05);
                box-shadow: 0 12px 35px rgba(37, 99, 235, 0.4);
            }
            
            .chat-toggle:active {
                transform: translateY(0) scale(0.98);
            }
            
            .close-chat:hover, .theme-toggle:hover {
                background: rgba(255,255,255,0.25) !important;
                transform: scale(1.1);
            }
            
            .close-chat:active, .theme-toggle:active {
                transform: scale(0.95);
            }
            
            .chat-input:focus {
                background: white;
                border-color: ${theme.light.primary} !important;
                box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
                transform: translateY(-1px);
            }
            
            .send-btn:hover {
                transform: translateY(-1px) scale(1.05);
                box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3);
            }
            
            .send-btn:active {
                transform: translateY(0) scale(0.95);
            }
            
            /* Scrollbar styling */
            .chat-messages::-webkit-scrollbar {
                width: 6px;
            }
            
            .chat-messages::-webkit-scrollbar-track {
                background: transparent;
            }
            
            .chat-messages::-webkit-scrollbar-thumb {
                background: #cbd5e1;
                border-radius: 3px;
            }
            
            .chat-messages::-webkit-scrollbar-thumb:hover {
                background: #94a3b8;
            }
            
            /* Message animations */
            .message {
                animation: slideIn 0.3s ease-out;
            }
            
            /* Dark theme styles */
            .chatbot-widget.dark-theme .chat-input:focus {
                background: #334155;
                border-color: #3b82f6 !important;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
            }
            
            .dark-theme .chat-messages::-webkit-scrollbar-thumb {
                background: #475569;
            }
            
            .dark-theme .chat-messages::-webkit-scrollbar-thumb:hover {
                background: #64748b;
            }
        </style>
    `;
    
    // Inject widget into page
    document.body.insertAdjacentHTML('beforeend', widgetHtml);
    
    const widget = document.getElementById('chatbot-widget');
    const toggleBtn = document.getElementById('chat-toggle');
    const closeBtn = document.getElementById('close-chat');
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = themeToggle.querySelector('.theme-icon');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const typingIndicator = document.getElementById('typing-indicator');
    
    let isTyping = false;
    
    // Initialize theme
    function initTheme() {
        if (theme.current === 'dark') {
            applyDarkTheme();
        } else {
            applyLightTheme();
        }
    }
    
    // Apply light theme
    function applyLightTheme() {
        widget.classList.remove('dark-theme');
        const styles = theme.light;
        
        // Update widget styles
        widget.style.background = styles.background;
        widget.style.borderColor = styles.border;
        widget.style.boxShadow = styles.shadow;
        
        // Update header
        document.querySelector('.chatbot-header').style.background = styles.headerBackground;
        
        // Update messages area
        chatMessages.style.background = styles.surface;
        
        // Update input area
        document.querySelector('.chatbot-input-area').style.background = styles.background;
        document.querySelector('.chatbot-input-area').style.borderTopColor = styles.border;
        
        // Update input
        chatInput.style.background = styles.inputBackground;
        chatInput.style.borderColor = styles.border;
        chatInput.style.color = styles.text;
        
        // Update send button
        sendBtn.style.background = styles.primaryGradient;
        
        // Update toggle button
        toggleBtn.style.background = styles.primaryGradient;
        toggleBtn.style.boxShadow = `0 8px 25px rgba(37, 99, 235, 0.3)`;
        
        // Update theme icon
        themeIcon.textContent = '🌙';
        
        // Update existing messages if any
        updateExistingMessagesTheme('light');
        
        theme.current = 'light';
        localStorage.setItem('chatbot-theme', 'light');
    }
    
    // Apply dark theme
    function applyDarkTheme() {
        widget.classList.add('dark-theme');
        const styles = theme.dark;
        
        // Update widget styles
        widget.style.background = styles.background;
        widget.style.borderColor = styles.border;
        widget.style.boxShadow = styles.shadow;
        
        // Update header
        document.querySelector('.chatbot-header').style.background = styles.headerBackground;
        
        // Update messages area
        chatMessages.style.background = styles.surface;
        
        // Update input area
        document.querySelector('.chatbot-input-area').style.background = styles.background;
        document.querySelector('.chatbot-input-area').style.borderTopColor = styles.border;
        
        // Update input
        chatInput.style.background = styles.inputBackground;
        chatInput.style.borderColor = styles.border;
        chatInput.style.color = styles.text;
        
        // Update send button
        sendBtn.style.background = styles.primaryGradient;
        
        // Update toggle button
        toggleBtn.style.background = styles.primaryGradient;
        toggleBtn.style.boxShadow = `0 8px 25px rgba(37, 99, 235, 0.3)`;
        
        // Update theme icon
        themeIcon.textContent = '☀️';
        
        // Update existing messages if any
        updateExistingMessagesTheme('dark');
        
        theme.current = 'dark';
        localStorage.setItem('chatbot-theme', 'dark');
    }
    
    // Update existing messages for theme change
    function updateExistingMessagesTheme(themeMode) {
        const styles = themeMode === 'dark' ? theme.dark : theme.light;
        const messages = chatMessages.querySelectorAll('.message');
        
        messages.forEach(message => {
            const bubble = message.querySelector('.message-bubble');
            if (bubble) {
                if (bubble.classList.contains('user-message')) {
                    bubble.style.background = styles.userBubble;
                    bubble.style.color = 'white';
                } else {
                    bubble.style.background = styles.botBubble;
                    bubble.style.color = styles.text;
                    bubble.style.borderColor = styles.border;
                }
            }
        });
        
        // Update typing indicator
        const dots = typingIndicator.querySelectorAll('.typing-dot');
        dots.forEach(dot => {
            dot.style.background = styles.primary;
        });
    }
    
    // Toggle theme
    function toggleTheme() {
        if (theme.current === 'light') {
            applyDarkTheme();
        } else {
            applyLightTheme();
        }
    }
    
    // Initialize theme on load
    initTheme();
    
    // Toggle chat window
    toggleBtn.addEventListener('click', function() {
        const isVisible = widget.style.display === 'flex';
        widget.style.display = isVisible ? 'none' : 'flex';
        toggleBtn.style.display = isVisible ? 'flex' : 'none';
        
        if (!isVisible) {
            widget.style.animation = 'slideIn 0.3s ease-out';
            chatInput.focus();
        }
    });
    
    closeBtn.addEventListener('click', function() {
        widget.style.display = 'none';
        toggleBtn.style.display = 'flex';
    });
    
    themeToggle.addEventListener('click', toggleTheme);
    
    // Show typing indicator
    function showTyping() {
        if (!isTyping) {
            isTyping = true;
            typingIndicator.style.display = 'flex';
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
    
    // Hide typing indicator
    function hideTyping() {
        isTyping = false;
        typingIndicator.style.display = 'none';
    }
    
    // Add message with typing effect
    function addMessageWithTyping(text, sender, delay = 20) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message';
        messageDiv.style.cssText = `
            display: flex;
            margin-bottom: 8px;
            animation: fadeIn 0.3s ease-out;
            ${sender === 'user' ? 'justify-content: flex-end;' : 'justify-content: flex-start;'}
        `;
        
        const bubble = document.createElement('div');
        bubble.className = `message-bubble ${sender === 'user' ? 'user-message' : 'bot-message'}`;
        
        const styles = theme.current === 'dark' ? theme.dark : theme.light;
        
        bubble.style.cssText = `
            max-width: 85%;
            padding: 14px 18px;
            border-radius: 18px;
            word-wrap: break-word;
            font-size: 14px;
            line-height: 1.5;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: all 0.2s ease;
            ${sender === 'user' ? 
                `background: ${styles.userBubble}; 
                 color: white; 
                 border-bottom-right-radius: 6px;
                 font-weight: 500;` : 
                `background: ${styles.botBubble}; 
                 color: ${styles.text}; 
                 border: 1px solid ${styles.border};
                 border-bottom-left-radius: 6px;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.1);`
            }
        `;
        
        messageDiv.appendChild(bubble);
        chatMessages.appendChild(messageDiv);
        
        if (sender === 'bot' && text) {
            bubble.textContent = '';
            let i = 0;
            
            function typeWriter() {
                if (i < text.length) {
                    bubble.textContent += text.charAt(i);
                    i++;
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                    setTimeout(typeWriter, delay);
                }
            }
            
            typeWriter();
        } else {
            bubble.textContent = text;
        }
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Send message function
    async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || isTyping) return;
    
    // Add user message
    addMessageWithTyping(message, 'user');
    chatInput.value = '';
    
    // Show typing indicator
    showTyping();
    
    try {
        console.log('=== SENDING MESSAGE DEBUG ===');
        console.log('Bot ID:', botId);
        console.log('Message:', message);
        console.log('API Key:', apiKey);
        
        const requestBody = { message: message };
        console.log('Request body:', requestBody);
        console.log('Stringified body:', JSON.stringify(requestBody));
        
        const response = await fetch(`https://geminichatx.flourishdigital.in/bots/website/${botId}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-API-Key': apiKey
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log('Response status:', response.status);
        console.log('Response headers:', Object.fromEntries(response.headers.entries()));
        
        // Hide typing indicator
        hideTyping();
        
        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
                console.log('Error response JSON:', errorData);
            } catch (e) {
                const errorText = await response.text();
                console.log('Error response text:', errorText);
                errorData = { detail: errorText };
            }
            throw new Error(`HTTP ${response.status}: ${errorData.detail || 'Unknown error'}`);
        }
        
        const data = await response.json();
        console.log('Success response:', data);
        addMessageWithTyping(data.bot_response, 'bot');
        
    } catch (error) {
        hideTyping();
        console.error('Chat error details:', error);
        
        let errorMessage = 'Sorry, I encountered an error. Please try again.';
        if (error.message.includes('422')) {
            errorMessage = 'Invalid request format. Please check your configuration.';
        } else if (error.message.includes('404')) {
            errorMessage = 'Bot not found. Please check your bot ID.';
        } else if (error.message.includes('401')) {
            errorMessage = 'Authentication failed. Please check your API key.';
        } else if (error.message.includes('Failed to fetch')) {
            errorMessage = 'Network error. Please check your connection.';
        }
        
        addMessageWithTyping(errorMessage, 'bot');
    }
}
    
    // Event listeners
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Add welcome message
    setTimeout(() => {
        addMessageWithTyping(`Hello! I'm ${botName}, your AI assistant. I'm here to help answer your questions and provide information. How can I assist you today?`, 'bot', 15);
    }, 500);
    
    // Handle page visibility changes
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden && widget.style.display === 'flex') {
            chatInput.focus();
        }
    });
    
    // Add smooth hover effects
    toggleBtn.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-2px) scale(1.05)';
    });
    
    toggleBtn.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0) scale(1)';
    });
    
    // Debug: Log successful initialization
    console.log('Chatbot initialized successfully with bot:', botId);
    console.log('Current theme:', theme.current);
})();